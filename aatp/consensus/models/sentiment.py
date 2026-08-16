"""Sentiment consensus model.

Scores an asset -2 to +2 based on forum sentiment, news coverage,
and presence of negative catalysts.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from aatp.core.logging import get_logger

logger = get_logger("consensus.sentiment")

# Sentiment score thresholds (sentiment values range from -1.0 to +1.0)
VERY_POSITIVE_SENTIMENT = Decimal("0.6")
POSITIVE_SENTIMENT = Decimal("0.2")
NEGATIVE_SENTIMENT = Decimal("-0.2")
VERY_NEGATIVE_SENTIMENT = Decimal("-0.6")

# Mention volume change thresholds
RISING_INTEREST_PCT = Decimal("30")   # 30% increase in mentions
FALLING_INTEREST_PCT = Decimal("-30")  # 30% decrease in mentions


def score_sentiment(
    avg_sentiment: Optional[Decimal],
    mention_volume_change_pct: Optional[Decimal],
    news_sentiment_avg: Optional[Decimal],
    has_negative_catalyst: bool,
) -> tuple[int, str, dict]:
    """Score sentiment from -2 to +2.

    Parameters
    ----------
    avg_sentiment : Average forum sentiment score (-1.0 to +1.0).
    mention_volume_change_pct : Percentage change in mention volume (e.g. 30.0 = +30%).
    news_sentiment_avg : Average news article sentiment score (-1.0 to +1.0).
    has_negative_catalyst : Whether a negative catalyst (recall, scandal, etc.) is active.

    Returns
    -------
    tuple of (score, rationale, supporting_data)
    """
    supporting_data: dict = {
        "avg_sentiment": str(avg_sentiment) if avg_sentiment is not None else None,
        "mention_volume_change_pct": str(mention_volume_change_pct) if mention_volume_change_pct is not None else None,
        "news_sentiment_avg": str(news_sentiment_avg) if news_sentiment_avg is not None else None,
        "has_negative_catalyst": has_negative_catalyst,
    }

    # Negative catalyst is an immediate strong negative signal
    if has_negative_catalyst:
        return -2, "Negative catalyst active (recall, scandal, or regulatory issue)", supporting_data

    # If no sentiment data available, score neutral
    if avg_sentiment is None and news_sentiment_avg is None:
        return 0, "Insufficient sentiment data", supporting_data

    reasons: list[str] = []
    points = 0

    # Forum sentiment assessment
    if avg_sentiment is not None:
        if avg_sentiment >= VERY_POSITIVE_SENTIMENT:
            points += 2
            reasons.append(f"very positive forum sentiment ({avg_sentiment})")
        elif avg_sentiment >= POSITIVE_SENTIMENT:
            points += 1
            reasons.append(f"positive forum sentiment ({avg_sentiment})")
        elif avg_sentiment <= VERY_NEGATIVE_SENTIMENT:
            points -= 2
            reasons.append(f"very negative forum sentiment ({avg_sentiment})")
        elif avg_sentiment <= NEGATIVE_SENTIMENT:
            points -= 1
            reasons.append(f"negative forum sentiment ({avg_sentiment})")
        else:
            reasons.append(f"neutral forum sentiment ({avg_sentiment})")

    # News sentiment
    if news_sentiment_avg is not None:
        if news_sentiment_avg >= POSITIVE_SENTIMENT:
            points += 1
            reasons.append(f"positive news coverage ({news_sentiment_avg})")
        elif news_sentiment_avg <= NEGATIVE_SENTIMENT:
            points -= 1
            reasons.append(f"negative news coverage ({news_sentiment_avg})")

    # Mention volume change (interest momentum)
    if mention_volume_change_pct is not None:
        if mention_volume_change_pct >= RISING_INTEREST_PCT:
            # Rising interest amplifies existing sentiment
            if points > 0:
                points += 1
                reasons.append(f"rising interest ({mention_volume_change_pct}% volume change)")
            elif points == 0:
                reasons.append(f"rising interest ({mention_volume_change_pct}% volume change)")
        elif mention_volume_change_pct <= FALLING_INTEREST_PCT:
            if points < 0:
                points -= 1
                reasons.append(f"falling interest ({mention_volume_change_pct}% volume change)")

    # Clamp to -2..+2
    score = max(-2, min(2, points))
    rationale = "Sentiment: " + "; ".join(reasons) if reasons else "Sentiment: neutral"

    return score, rationale, supporting_data
