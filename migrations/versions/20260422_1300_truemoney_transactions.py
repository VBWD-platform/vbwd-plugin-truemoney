"""Create truemoney_transactions table.

Revision ID: 20260422_1300_truemoney
Revises: 20260422_1200_c2p2_tx
Create Date: 2026-04-22

Sprint 32 — TrueMoney Thailand direct plugin.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260422_1300_truemoney"
down_revision = "20260422_1200_c2p2_tx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "truemoney_transactions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("invoice_no", sa.String(length=64), nullable=False, unique=True),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("transaction_id", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="THB"),
        sa.Column("qr_payload", sa.String(length=512), nullable=True),
        sa.Column("deep_link", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("last_provider_status", sa.String(length=24), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_truemoney_transactions_transaction_id",
        "truemoney_transactions",
        ["transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_truemoney_transactions_transaction_id",
        table_name="truemoney_transactions",
    )
    op.drop_table("truemoney_transactions")
