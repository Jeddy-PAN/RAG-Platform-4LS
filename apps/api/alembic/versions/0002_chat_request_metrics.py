"""add chat request metrics

Revision ID: 0002_chat_request_metrics
Revises: 0001_initial_schema
Create Date: 2026-06-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_chat_request_metrics"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def uuid_fk(name: str, target: str) -> sa.Column:
    """Build a required UUID foreign key column."""

    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(target, ondelete="CASCADE"),
        nullable=False,
    )


def timestamps() -> tuple[sa.Column, sa.Column]:
    """Build standard timestamp columns."""

    return (
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


def upgrade() -> None:
    op.create_table(
        "chat_request_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        uuid_fk("project_id", "projects.id"),
        uuid_fk("conversation_id", "conversations.id"),
        uuid_fk("retrieval_log_id", "retrieval_logs.id"),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
        sa.Column("generation_latency_ms", sa.Integer(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *timestamps(),
    )
    op.create_index("ix_chat_request_metrics_project_id", "chat_request_metrics", ["project_id"])
    op.create_index(
        "ix_chat_request_metrics_conversation_id",
        "chat_request_metrics",
        ["conversation_id"],
    )
    op.create_index(
        "ix_chat_request_metrics_retrieval_log_id",
        "chat_request_metrics",
        ["retrieval_log_id"],
    )
    op.create_index(
        "ix_chat_request_metrics_project_created",
        "chat_request_metrics",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_chat_request_metrics_project_model",
        "chat_request_metrics",
        ["project_id", "model"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_request_metrics_project_model", table_name="chat_request_metrics")
    op.drop_index("ix_chat_request_metrics_project_created", table_name="chat_request_metrics")
    op.drop_index("ix_chat_request_metrics_retrieval_log_id", table_name="chat_request_metrics")
    op.drop_index("ix_chat_request_metrics_conversation_id", table_name="chat_request_metrics")
    op.drop_index("ix_chat_request_metrics_project_id", table_name="chat_request_metrics")
    op.drop_table("chat_request_metrics")
