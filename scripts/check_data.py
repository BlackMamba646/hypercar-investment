import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from aatp.core.config import settings

async def check():
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT COUNT(*) FROM transactions"))
        print(f"Transactions: {r.scalar()}")

        r = await conn.execute(text("SELECT COUNT(*) FROM data_provenance"))
        print(f"Data provenance records: {r.scalar()}")

        r = await conn.execute(text("SELECT COUNT(*) FROM scraper_runs"))
        print(f"Scraper runs: {r.scalar()}")

        r = await conn.execute(text("""
            SELECT am.name, COUNT(t.id) as cnt,
                   MIN(t.total_price_usd)::int as min_price,
                   MAX(t.total_price_usd)::int as max_price
            FROM transactions t
            JOIN asset_models am ON t.asset_model_id = am.id
            GROUP BY am.name ORDER BY cnt DESC
        """))
        print("\nTransactions by model:")
        for row in r.fetchall():
            lo = f"${row[2]:,}" if row[2] is not None else "N/A"
            hi = f"${row[3]:,}" if row[3] is not None else "N/A"
            print(f"  {row[0]}: {row[1]} txns ({lo} - {hi})")
    await engine.dispose()

asyncio.run(check())
