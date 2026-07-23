"""add chunk is_active flag for soft delete

Revision ID: 0003_add_chunk_is_active
Revises: 0002_chat_request_metrics
Create Date: 2026-07-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_chunk_is_active"
down_revision = "0002_chat_request_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index("ix_chunks_is_active", "chunks", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_chunks_is_active", table_name="chunks")
    op.drop_column("chunks", "is_active")
