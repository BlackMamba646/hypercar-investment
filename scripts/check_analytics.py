import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from aatp.core.config import settings

async def check():
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        r = await conn.execute(text("""
            SELECT am.name, fv.fair_value_low::int, fv.fair_value_mid::int,
                   fv.fair_value_high::int, fv.confidence_score, fv.comparable_count
            FROM fair_values fv
            JOIN asset_models am ON fv.asset_model_id = am.id
            ORDER BY fv.valuation_date DESC
        """))
        rows = r.fetchall()
        print(f"Fair values: {len(rows)}")
        for row in rows:
            print(f"  {row[0]}: ${row[1]:,} / ${row[2]:,} / ${row[3]:,} (conf={row[4]}, comps={row[5]})")

        r = await conn.execute(text("SELECT COUNT(*) FROM signals"))
        print(f"\nSignals: {r.scalar()}")

        r = await conn.execute(text("SELECT COUNT(*) FROM opportunity_scores"))
        print(f"Opportunity scores: {r.scalar()}")

        r = await conn.execute(text("SELECT COUNT(*) FROM consensus_scores"))
        print(f"Consensus scores: {r.scalar()}")

        r = await conn.execute(text("SELECT COUNT(*) FROM consensus_model_scores"))
        print(f"Consensus model scores: {r.scalar()}")

        r = await conn.execute(text("""
            SELECT am.name, cs.aggregate_score, cs.status, cs.has_veto, cs.actionable
            FROM consensus_scores cs
            JOIN asset_models am ON cs.asset_model_id = am.id
            WHERE cs.aggregate_score > -2
            ORDER BY cs.aggregate_score DESC
        """))
        rows = r.fetchall()
        print(f"\nNon-vetoed consensus scores:")
        for row in rows:
            print(f"  {row[0]}: score={row[1]}, status={row[2]}, veto={row[3]}, actionable={row[4]}")

    await engine.dispose()

asyncio.run(check())
