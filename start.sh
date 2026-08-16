#!/bin/bash

echo "=== AATP Startup ==="

# Wait for database to be reachable (Render DB may still be provisioning)
echo "Waiting for database..."
for i in $(seq 1 30); do
    if python3 -c "
from sqlalchemy import create_engine, text
from aatp.core.config import settings
engine = create_engine(settings.database_url_sync, connect_args={'connect_timeout': 5})
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
engine.dispose()
" 2>/dev/null; then
        echo "Database is reachable."
        break
    fi
    echo "  Attempt $i/30 — database not ready, retrying in 5s..."
    sleep 5
done

# Clean orphaned state from any previous failed migrations
python3 -c "
import sys
from sqlalchemy import create_engine, text, inspect
from aatp.core.config import settings
engine = create_engine(settings.database_url_sync)
try:
    with engine.connect() as conn:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        has_alembic = 'alembic_version' in existing_tables
        has_manufacturers = 'manufacturers' in existing_tables
        if not has_manufacturers and not has_alembic:
            print('Fresh database — cleaning any orphaned types...')
            types = conn.execute(text(
                \"SELECT typname FROM pg_type WHERE typtype = 'e' \"
                \"AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')\"
            )).fetchall()
            for t in types:
                print(f'  Dropping: {t[0]}')
                conn.execute(text(f'DROP TYPE IF EXISTS \"{t[0]}\" CASCADE'))
            for tbl in reversed(existing_tables):
                print(f'  Dropping partial table: {tbl}')
                conn.execute(text(f'DROP TABLE IF EXISTS \"{tbl}\" CASCADE'))
            if types or existing_tables:
                conn.commit()
            print('Cleanup done.')
        else:
            print(f'Database has {len(existing_tables)} tables, skipping cleanup.')
except Exception as e:
    print(f'Warning: cleanup failed: {e}', file=sys.stderr)
finally:
    engine.dispose()
" || true

echo "Running database migrations..."
alembic upgrade head

echo "Checking asset catalog..."
python3 -c "
from sqlalchemy import create_engine, text
from aatp.core.config import settings
engine = create_engine(settings.database_url_sync)
with engine.connect() as conn:
    count = conn.execute(text('SELECT COUNT(*) FROM manufacturers')).scalar()
    print(f'Manufacturers: {count}')
engine.dispose()
if count == 0:
    print('Loading data fixture...')
    exit(0)
else:
    print('Data already loaded, skipping fixture.')
    exit(1)
" && python3 -c "
from sqlalchemy import create_engine, text
from pathlib import Path
from aatp.core.config import settings
engine = create_engine(settings.database_url_sync)
sql = Path('scripts/data_fixture.sql').read_text()
with engine.connect() as conn:
    for line in sql.strip().split('\n'):
        if line.strip() and line.strip().startswith('INSERT'):
            conn.execute(text(line))
    conn.commit()
    count = conn.execute(text('SELECT COUNT(*) FROM transactions')).scalar()
    print(f'Fixture loaded: {count} transactions')
engine.dispose()
"

echo "Starting AATP API on port ${PORT:-8000}..."
exec uvicorn aatp.api.app:app --host 0.0.0.0 --port "${PORT:-8000}"
