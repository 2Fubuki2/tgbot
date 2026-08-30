"""add fee_assessment_day to club_settings

Revision ID: a1b2c3d4e5f6
Revises: 4962cc6f13d2
Create Date: 2026-08-30 04:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '4962cc6f13d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('club_settings', sa.Column('fee_assessment_day', sa.Integer, nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('club_settings', 'fee_assessment_day')
