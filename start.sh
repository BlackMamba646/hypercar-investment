#!/bin/bash
set -e

echo "Cleaning up any orphaned types from failed migrations..."
python -c "
from sqlalchemy import create_engine, text
from aatp.core.config import settings
engine = create_engine(settings.database_url_sync)
with engine.connect() as conn:
    has_tables = conn.execute(text(
        \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'manufacturers')\"
    )).scalar()
    has_alembic = conn.execute(text(
        \"SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version')\"
    )).scalar()
    if not has_tables and not has_alembic:
        print('No tables and no alembic_version — dropping orphaned types if any...')
        for t in conn.execute(text(
            \"SELECT typname FROM pg_type WHERE typtype = 'e' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')\"
        )).fetchall():
            print(f'  Dropping orphaned type: {t[0]}')
            conn.execute(text(f'DROP TYPE IF EXISTS {t[0]} CASCADE'))
        conn.commit()
        print('Cleanup done.')
    else:
        print('Database has existing tables, skipping cleanup.')
engine.dispose()
"

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
