#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Checking asset catalog..."
python -c "
from sqlalchemy import create_engine, text
from aatp.core.config import settings

engine = create_engine(settings.database_url_sync)
with engine.connect() as conn:
    count = conn.execute(text('SELECT COUNT(*) FROM asset_models')).scalar()
    if count == 0:
        print('No asset models found — running seed...')
        from sqlalchemy.orm import Session as OrmSession
        with OrmSession(engine) as session:
            from scripts.seed_data import seed
            seed(session)
            session.commit()
        print('Seed complete.')
    else:
        print(f'Asset catalog already has {count} models, skipping seed.')
engine.dispose()
"

echo "Starting AATP API server..."
exec uvicorn aatp.api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
