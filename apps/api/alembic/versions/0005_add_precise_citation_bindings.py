"""add precise message citation bindings

Revision ID: 0005_add_precise_citation_bindings
Revises: 0004_add_search_representation
Create Date: 2026-08-17 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_precise_citation_bindings"
down_revision = "0004_add_search_representation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message_citations", sa.Column("claim_index", sa.Integer(), nullable=True))
    op.add_column("message_citations", sa.Column("source_number", sa.Integer(), nullable=True))
    op.add_column("message_citations", sa.Column("quote_start", sa.Integer(), nullable=True))
    op.add_column("message_citations", sa.Column("quote_end", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_message_citations_claim_index_positive", "message_citations", "claim_index IS NULL OR claim_index > 0")
    op.create_check_constraint("ck_message_citations_source_number_positive", "message_citations", "source_number IS NULL OR source_number > 0")
    op.create_check_constraint("ck_message_citations_quote_offsets_paired", "message_citations", "(quote_start IS NULL) = (quote_end IS NULL)")
    op.create_check_constraint("ck_message_citations_quote_start_nonnegative", "message_citations", "quote_start IS NULL OR quote_start >= 0")
    op.create_check_constraint("ck_message_citations_quote_end_nonnegative", "message_citations", "quote_end IS NULL OR quote_end >= 0")
    op.create_check_constraint("ck_message_citations_quote_offsets_ordered", "message_citations", "quote_end IS NULL OR quote_end >= quote_start")
    op.create_index("ix_message_citations_message_claim_citation", "message_citations", ["message_id", "claim_index", "citation_index"])


def downgrade() -> None:
    op.drop_index("ix_message_citations_message_claim_citation", table_name="message_citations")
    op.drop_constraint("ck_message_citations_quote_offsets_ordered", "message_citations", type_="check")
    op.drop_constraint("ck_message_citations_quote_end_nonnegative", "message_citations", type_="check")
    op.drop_constraint("ck_message_citations_quote_start_nonnegative", "message_citations", type_="check")
    op.drop_constraint("ck_message_citations_quote_offsets_paired", "message_citations", type_="check")
    op.drop_constraint("ck_message_citations_source_number_positive", "message_citations", type_="check")
    op.drop_constraint("ck_message_citations_claim_index_positive", "message_citations", type_="check")
    op.drop_column("message_citations", "quote_end")
    op.drop_column("message_citations", "quote_start")
    op.drop_column("message_citations", "source_number")
    op.drop_column("message_citations", "claim_index")
