"""
Asset model matcher.

Maps scraped listing titles like "2019 Ferrari 488 Pista Spider" to
asset_models rows in the database. Uses a combination of exact matching,
token-based fuzzy matching, and manufacturer-aware parsing.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aatp.core.logging import get_logger
from aatp.db.models import AssetModel, Manufacturer

logger = get_logger("collectors.model_matcher")

_NOISE_WORDS = frozenset({
    "the", "a", "an", "with", "and", "or", "for", "in", "by",
    "edition", "limited", "special", "series", "model", "type",
})

_VARIANT_INDICATORS = frozenset({
    "spider", "spyder", "aperta", "gts", "gt", "gt3", "gt2",
    "competizione", "speciale", "pista", "scuderia",
    "super sport", "supersport", "pur sport", "sport",
    "roadster", "cabriolet", "convertible", "targa",
    "rs", "lm", "sv", "svj", "performante",
    "stradale",
})


@dataclass
class MatchResult:
    asset_model_id: uuid.UUID
    manufacturer_name: str
    model_name: str
    variant: str | None
    confidence: float
    match_method: str


@dataclass
class _CachedModel:
    id: uuid.UUID
    manufacturer_name: str
    name: str
    variant: str | None
    name_lower: str
    variant_lower: str | None
    tokens: set[str]
    production_year_start: int | None
    production_year_end: int | None


class AssetModelMatcher:
    """Matches scraped titles to known asset models."""

    def __init__(self, session: AsyncSession):
        self.db = session
        self._cache: list[_CachedModel] | None = None

    async def _load_cache(self) -> list[_CachedModel]:
        if self._cache is not None:
            return self._cache

        result = await self.db.execute(
            select(AssetModel).options(selectinload(AssetModel.manufacturer))
        )
        models = result.scalars().all()

        self._cache = []
        for m in models:
            name_lower = m.name.lower().strip()
            variant_lower = m.variant.lower().strip() if m.variant else None

            tokens = set(name_lower.split())
            if variant_lower:
                tokens.update(variant_lower.split())
            tokens.add(m.manufacturer.name.lower())
            tokens -= _NOISE_WORDS

            self._cache.append(_CachedModel(
                id=m.id,
                manufacturer_name=m.manufacturer.name,
                name=m.name,
                variant=m.variant,
                name_lower=name_lower,
                variant_lower=variant_lower,
                tokens=tokens,
                production_year_start=m.production_year_start,
                production_year_end=m.production_year_end,
            ))

        logger.info("model_cache_loaded", count=len(self._cache))
        return self._cache

    def invalidate_cache(self) -> None:
        self._cache = None

    @staticmethod
    def _extract_year(title: str) -> int | None:
        match = re.search(r'\b(19[5-9]\d|20[0-4]\d)\b', title)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_manufacturer(title: str, known_manufacturers: set[str]) -> str | None:
        title_lower = title.lower()
        for mfr in known_manufacturers:
            if mfr.lower() in title_lower:
                return mfr
        return None

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        return {t for t in text.split() if t not in _NOISE_WORDS and len(t) > 1}

    @staticmethod
    def _token_similarity(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        intersection = a & b
        return len(intersection) / min(len(a), len(b))

    def _year_matches(self, year: int | None, model: _CachedModel) -> bool:
        if year is None:
            return True
        if model.production_year_start is None:
            return True
        start = model.production_year_start
        end = model.production_year_end or start + 10
        return start <= year <= end

    async def match(self, title: str, manufacturer_hint: str | None = None) -> MatchResult | None:
        """
        Match a listing title to a known asset model.

        Returns MatchResult with confidence score, or None if no match found
        above the minimum threshold (0.4).
        """
        cache = await self._load_cache()
        if not cache:
            return None

        title_tokens = self._tokenize(title)
        year = self._extract_year(title)

        known_mfrs = {m.manufacturer_name for m in cache}
        detected_mfr = manufacturer_hint or self._extract_manufacturer(title, known_mfrs)

        candidates: list[tuple[_CachedModel, float, str]] = []

        for model in cache:
            if detected_mfr and model.manufacturer_name.lower() != detected_mfr.lower():
                continue

            if not self._year_matches(year, model):
                continue

            title_lower = title.lower()

            # Exact name match
            if model.name_lower in title_lower:
                score = 0.7
                method = "exact_name"

                # Check variant match
                if model.variant_lower:
                    if model.variant_lower in title_lower:
                        score = 0.95
                        method = "exact_name_variant"
                    else:
                        # Has variant in DB but title doesn't mention it —
                        # could be the base model or just missing the variant
                        any_variant_mentioned = False
                        for vi in _VARIANT_INDICATORS:
                            if vi in title_lower and vi != model.name_lower:
                                any_variant_mentioned = True
                                break
                        if any_variant_mentioned:
                            score = 0.3
                            method = "exact_name_wrong_variant"
                        else:
                            score = 0.6
                            method = "exact_name_no_variant"
                elif model.variant is None:
                    for vi in _VARIANT_INDICATORS:
                        if vi in title_lower:
                            score = 0.5
                            method = "exact_name_unexpected_variant"
                            break

                candidates.append((model, score, method))
                continue

            # Token-based fuzzy match
            sim = self._token_similarity(title_tokens, model.tokens)
            if sim >= 0.5:
                candidates.append((model, sim * 0.8, "token_fuzzy"))

        if not candidates:
            logger.debug("no_match", title=title)
            return None

        candidates.sort(key=lambda c: c[1], reverse=True)
        best_model, best_score, best_method = candidates[0]

        if best_score < 0.4:
            logger.debug("low_confidence_match", title=title, score=best_score)
            return None

        result = MatchResult(
            asset_model_id=best_model.id,
            manufacturer_name=best_model.manufacturer_name,
            model_name=best_model.name,
            variant=best_model.variant,
            confidence=round(best_score, 3),
            match_method=best_method,
        )
        logger.debug(
            "matched",
            title=title,
            model=f"{best_model.manufacturer_name} {best_model.name} {best_model.variant or ''}".strip(),
            confidence=result.confidence,
            method=best_method,
        )
        return result

    async def match_batch(self, titles: list[str]) -> list[MatchResult | None]:
        """Match a batch of titles. Returns list aligned with input."""
        return [await self.match(t) for t in titles]
