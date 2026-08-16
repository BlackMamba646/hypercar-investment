"""Add collecting_cars and classic_com to transactionsource enum

Revision ID: 002
Revises: 001
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transactionsource ADD VALUE IF NOT EXISTS 'collecting_cars'")
    op.execute("ALTER TYPE transactionsource ADD VALUE IF NOT EXISTS 'classic_com'")


def downgrade() -> None:
    pass
