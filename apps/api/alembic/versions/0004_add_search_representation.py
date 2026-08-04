"""add search representation fields and trigger

Revision ID: 0004_add_search_representation
Revises: 0003_add_chunk_is_active
Create Date: 2026-08-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_search_representation"
down_revision = "0003_add_chunk_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("search_text", sa.Text(), nullable=True))
    op.add_column(
        "chunks",
        sa.Column(
            "search_representation_version",
            sa.String(length=64),
            nullable=False,
            server_default="legacy-v0",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "search_representation_version",
            sa.String(length=64),
            nullable=True,
        ),
    )

    # Legacy chunks carry the payload as their search text.
    op.execute("UPDATE chunks SET search_text = text WHERE search_text IS NULL")

    # Existing indexed documents are legacy; never-indexed documents stay null.
    op.execute(
        "UPDATE documents SET search_representation_version = 'legacy-v0' "
        "WHERE status = 'indexed' AND search_representation_version IS NULL"
    )

    # Replace the trigger so search_vector follows search_text and falls back
    # to the original text, firing when either field changes.
    op.execute("DROP TRIGGER IF EXISTS chunks_search_vector_update ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_search_vector_update")
    op.execute(
        """
        CREATE FUNCTION chunks_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector = to_tsvector('simple', coalesce(NEW.search_text, NEW.text, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER chunks_search_vector_update
        BEFORE INSERT OR UPDATE OF text, search_text ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_search_vector_update()
        """
    )


def downgrade() -> None:
    # Restore the original text-based trigger.
    op.execute("DROP TRIGGER IF EXISTS chunks_search_vector_update ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_search_vector_update")
    op.execute(
        """
        CREATE FUNCTION chunks_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector = to_tsvector('simple', coalesce(NEW.text, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER chunks_search_vector_update
        BEFORE INSERT OR UPDATE OF text ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_search_vector_update()
        """
    )
    # Recompute existing search vectors from the payload before removing
    # search_text so the schema returns to the original text-only contract.
    op.execute(
        "UPDATE chunks SET search_vector = to_tsvector('simple', coalesce(text, ''))"
    )
    op.drop_column("documents", "search_representation_version")
    op.drop_column("chunks", "search_representation_version")
    op.drop_column("chunks", "search_text")
