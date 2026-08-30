"""add paid_amount to monthly_fees

Revision ID: 4962cc6f13d2
Revises: c9b9b2079b2e
Create Date: 2026-08-30 03:46:28.735239

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4962cc6f13d2'
down_revision: Union[str, None] = 'c9b9b2079b2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('monthly_fees', sa.Column('paid_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'))


def downgrade() -> None:
    op.drop_column('monthly_fees', 'paid_amount')
