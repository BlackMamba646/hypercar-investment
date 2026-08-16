#!/bin/bash
set -e

echo "=== AATP Startup ==="
echo "DATABASE_URL is set: $([ -n "$DATABASE_URL" ] && echo 'yes' || echo 'no')"

echo "Cleaning up any orphaned state from failed migrations..."
python3 -c "
import sys
from sqlalchemy import create_engine, text, inspect
from aatp.core.config import settings

print(f'Connecting to: {settings.database_url_sync[:40]}...')
engine = create_engine(settings.database_url_sync)
try:
    with engine.connect() as conn:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        print(f'Existing tables: {len(existing_tables)} ({existing_tables[:5]}...)')

        has_alembic = 'alembic_version' in existing_tables
        has_manufacturers = 'manufacturers' in existing_tables

        if not has_manufacturers and not has_alembic:
            print('No tables and no alembic_version — dropping orphaned types...')
            types = conn.execute(text(
                \"SELECT typname FROM pg_type WHERE typtype = 'e' \"
                \"AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')\"
            )).fetchall()
            if types:
                for t in types:
                    print(f'  Dropping: {t[0]}')
                    conn.execute(text(f'DROP TYPE IF EXISTS \"{t[0]}\" CASCADE'))
                conn.commit()
                print(f'Dropped {len(types)} orphaned types.')
            else:
                print('No orphaned types found.')

            # Also drop any partial tables
            if existing_tables:
                for tbl in reversed(existing_tables):
                    print(f'  Dropping partial table: {tbl}')
                    conn.execute(text(f'DROP TABLE IF EXISTS \"{tbl}\" CASCADE'))
                conn.commit()
        else:
            print('Database has existing schema, skipping cleanup.')
except Exception as e:
    print(f'Cleanup error (non-fatal): {e}', file=sys.stderr)
finally:
    engine.dispose()
"

echo "Running database migrations..."
alembic upgrade head

echo "Checking asset catalog..."
python3 -c "
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as OrmSession
from aatp.core.config import settings

engine = create_engine(settings.database_url_sync)
with engine.connect() as conn:
    count = conn.execute(text('SELECT COUNT(*) FROM asset_models')).scalar()
    if count == 0:
        print('No asset models found — running seed...')
        with OrmSession(engine) as session:
            from scripts.seed_data import seed
            seed(session)
            session.commit()
        print('Seed complete.')
    else:
        print(f'Asset catalog already has {count} models, skipping seed.')
engine.dispose()
"

echo "Starting AATP API server on port ${PORT:-8000}..."
exec uvicorn aatp.api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
