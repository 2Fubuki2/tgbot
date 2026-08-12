"""Add compatibility columns for payment_type and paid_amount.

Revision ID: 20260801_add_payment_and_fine_compat_columns
Revises: 
Create Date: 2026-08-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260801_add_payment_and_fine_compat_columns"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "fines" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("fines")}
        if "paid_amount" not in columns:
            op.add_column("fines", sa.Column("paid_amount", sa.Numeric(10, 2), nullable=False, server_default="0.00"))

    if "payments" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("payments")}
        if "payment_type" not in columns:
            op.add_column("payments", sa.Column("payment_type", sa.String(length=20), nullable=False, server_default="fee"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "payments" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("payments")}
        if "payment_type" in columns:
            op.drop_column("payments", "payment_type")

    if "fines" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("fines")}
        if "paid_amount" in columns:
            op.drop_column("fines", "paid_amount")
