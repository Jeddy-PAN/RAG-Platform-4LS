"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-24 00:00:00.000000
"""

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


document_status = sa.Enum(
    "uploaded", "processing", "indexed", "failed", name="document_status"
)
ingestion_job_status = sa.Enum(
    "queued", "running", "completed", "failed", name="ingestion_job_status"
)
message_role = sa.Enum("user", "assistant", "system", name="message_role")
retrieval_mode = sa.Enum("vector", "keyword", "hybrid", name="retrieval_mode")
feedback_rating = sa.Enum("useful", "not_useful", name="feedback_rating")
eval_run_status = sa.Enum(
    "queued", "running", "completed", "failed", name="eval_run_status"
)


def uuid_pk() -> sa.Column:
    """Build the standard UUID primary key column for schema tables."""

    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def timestamps() -> tuple[sa.Column, sa.Column]:
    """Build the standard created_at and updated_at columns."""

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


def project_fk() -> sa.Column:
    """Build the required project isolation foreign key column."""

    return sa.Column(
        "project_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    document_status.create(op.get_bind(), checkfirst=True)
    ingestion_job_status.create(op.get_bind(), checkfirst=True)
    message_role.create(op.get_bind(), checkfirst=True)
    retrieval_mode.create(op.get_bind(), checkfirst=True)
    feedback_rating.create(op.get_bind(), checkfirst=True)
    eval_run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "projects",
        uuid_pk(),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("name", name="uq_projects_name"),
    )

    op.create_table(
        "app_settings",
        uuid_pk(),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("key", name="uq_app_settings_key"),
    )

    op.create_table(
        "documents",
        uuid_pk(),
        project_fk(),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            document_status,
            nullable=False,
            server_default=sa.text("'uploaded'"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *timestamps(),
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])
    op.create_index("ix_documents_project_id_status", "documents", ["project_id", "status"])

    op.create_table(
        "document_sections",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *timestamps(),
    )
    op.create_index("ix_document_sections_project_id", "document_sections", ["project_id"])
    op.create_index("ix_document_sections_document_id", "document_sections", ["document_id"])
    op.create_index(
        "ix_document_sections_project_document",
        "document_sections",
        ["project_id", "document_id"],
    )

    op.create_table(
        "ingestion_jobs",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            ingestion_job_status,
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "job_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *timestamps(),
    )
    op.create_index("ix_ingestion_jobs_project_id", "ingestion_jobs", ["project_id"])
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index(
        "ix_ingestion_jobs_project_status", "ingestion_jobs", ["project_id", "status"]
    )

    op.create_table(
        "chunks",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_sections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_chunks_project_id", "chunks", ["project_id"])
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_section_id", "chunks", ["section_id"])
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])
    op.create_index("ix_chunks_project_document", "chunks", ["project_id", "document_id"])
    op.create_index("ix_chunks_project_chunk_index", "chunks", ["project_id", "chunk_index"])
    op.create_index(
        "ix_chunks_search_vector",
        "chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_chunks_embedding",
        "chunks",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # Keep keyword search material in sync with chunk text at write time.
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

    op.create_table(
        "conversations",
        uuid_pk(),
        project_fk(),
        sa.Column("title", sa.String(length=240), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
    op.create_index(
        "ix_conversations_project_updated", "conversations", ["project_id", "updated_at"]
    )

    op.create_table(
        "messages",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "message_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *timestamps(),
    )
    op.create_index("ix_messages_project_id", "messages", ["project_id"])
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index(
        "ix_messages_project_conversation", "messages", ["project_id", "conversation_id"]
    )

    op.create_table(
        "message_citations",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column(
            "citation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *timestamps(),
    )
    op.create_index("ix_message_citations_project_id", "message_citations", ["project_id"])
    op.create_index("ix_message_citations_message_id", "message_citations", ["message_id"])
    op.create_index("ix_message_citations_chunk_id", "message_citations", ["chunk_id"])
    op.create_index(
        "ix_message_citations_project_message",
        "message_citations",
        ["project_id", "message_id"],
    )

    op.create_table(
        "retrieval_logs",
        uuid_pk(),
        project_fk(),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("mode", retrieval_mode, nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "retrieval_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *timestamps(),
    )
    op.create_index("ix_retrieval_logs_project_id", "retrieval_logs", ["project_id"])
    op.create_index(
        "ix_retrieval_logs_project_created", "retrieval_logs", ["project_id", "created_at"]
    )
    op.create_index(
        "ix_retrieval_logs_project_mode", "retrieval_logs", ["project_id", "mode"]
    )

    op.create_table(
        "retrieval_log_chunks",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "retrieval_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("retrieval_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("keyword_score", sa.Float(), nullable=True),
        sa.Column("fused_score", sa.Float(), nullable=True),
        sa.Column(
            "score_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *timestamps(),
    )
    op.create_index("ix_retrieval_log_chunks_project_id", "retrieval_log_chunks", ["project_id"])
    op.create_index(
        "ix_retrieval_log_chunks_retrieval_log_id",
        "retrieval_log_chunks",
        ["retrieval_log_id"],
    )
    op.create_index("ix_retrieval_log_chunks_chunk_id", "retrieval_log_chunks", ["chunk_id"])
    op.create_index(
        "ix_retrieval_log_chunks_project_log",
        "retrieval_log_chunks",
        ["project_id", "retrieval_log_id"],
    )

    op.create_table(
        "feedback",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", feedback_rating, nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_feedback_project_id", "feedback", ["project_id"])
    op.create_index("ix_feedback_conversation_id", "feedback", ["conversation_id"])
    op.create_index("ix_feedback_message_id", "feedback", ["message_id"])
    op.create_index("ix_feedback_project_message", "feedback", ["project_id", "message_id"])

    op.create_table(
        "eval_datasets",
        uuid_pk(),
        project_fk(),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_eval_datasets_project_id", "eval_datasets", ["project_id"])
    op.create_index("ix_eval_datasets_project", "eval_datasets", ["project_id"])

    op.create_table(
        "eval_questions",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "expected_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "expected_chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expected_answer_notes", sa.Text(), nullable=True),
        sa.Column("should_answer", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )
    op.create_index("ix_eval_questions_project_id", "eval_questions", ["project_id"])
    op.create_index("ix_eval_questions_dataset_id", "eval_questions", ["dataset_id"])
    op.create_index("ix_eval_questions_expected_document_id", "eval_questions", ["expected_document_id"])
    op.create_index("ix_eval_questions_expected_chunk_id", "eval_questions", ["expected_chunk_id"])
    op.create_index(
        "ix_eval_questions_project_dataset", "eval_questions", ["project_id", "dataset_id"]
    )

    op.create_table(
        "eval_runs",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", eval_run_status, nullable=False, server_default=sa.text("'queued'")),
        sa.Column("retrieval_mode", sa.String(length=40), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_eval_runs_project_id", "eval_runs", ["project_id"])
    op.create_index("ix_eval_runs_dataset_id", "eval_runs", ["dataset_id"])
    op.create_index("ix_eval_runs_project_dataset", "eval_runs", ["project_id", "dataset_id"])
    op.create_index("ix_eval_runs_project_status", "eval_runs", ["project_id", "status"])

    op.create_table(
        "eval_results",
        uuid_pk(),
        project_fk(),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "citation_covered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("refused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
        sa.Column("generation_latency_ms", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column(
            "result_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *timestamps(),
    )
    op.create_index("ix_eval_results_project_id", "eval_results", ["project_id"])
    op.create_index("ix_eval_results_run_id", "eval_results", ["run_id"])
    op.create_index("ix_eval_results_question_id", "eval_results", ["question_id"])
    op.create_index("ix_eval_results_project_run", "eval_results", ["project_id", "run_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_results_project_run", table_name="eval_results")
    op.drop_index("ix_eval_results_question_id", table_name="eval_results")
    op.drop_index("ix_eval_results_run_id", table_name="eval_results")
    op.drop_index("ix_eval_results_project_id", table_name="eval_results")
    op.drop_table("eval_results")

    op.drop_index("ix_eval_runs_project_status", table_name="eval_runs")
    op.drop_index("ix_eval_runs_project_dataset", table_name="eval_runs")
    op.drop_index("ix_eval_runs_dataset_id", table_name="eval_runs")
    op.drop_index("ix_eval_runs_project_id", table_name="eval_runs")
    op.drop_table("eval_runs")

    op.drop_index("ix_eval_questions_project_dataset", table_name="eval_questions")
    op.drop_index("ix_eval_questions_expected_chunk_id", table_name="eval_questions")
    op.drop_index("ix_eval_questions_expected_document_id", table_name="eval_questions")
    op.drop_index("ix_eval_questions_dataset_id", table_name="eval_questions")
    op.drop_index("ix_eval_questions_project_id", table_name="eval_questions")
    op.drop_table("eval_questions")

    op.drop_index("ix_eval_datasets_project", table_name="eval_datasets")
    op.drop_index("ix_eval_datasets_project_id", table_name="eval_datasets")
    op.drop_table("eval_datasets")

    op.drop_index("ix_feedback_project_message", table_name="feedback")
    op.drop_index("ix_feedback_message_id", table_name="feedback")
    op.drop_index("ix_feedback_conversation_id", table_name="feedback")
    op.drop_index("ix_feedback_project_id", table_name="feedback")
    op.drop_table("feedback")

    op.drop_index("ix_retrieval_log_chunks_project_log", table_name="retrieval_log_chunks")
    op.drop_index("ix_retrieval_log_chunks_chunk_id", table_name="retrieval_log_chunks")
    op.drop_index(
        "ix_retrieval_log_chunks_retrieval_log_id", table_name="retrieval_log_chunks"
    )
    op.drop_index("ix_retrieval_log_chunks_project_id", table_name="retrieval_log_chunks")
    op.drop_table("retrieval_log_chunks")

    op.drop_index("ix_retrieval_logs_project_mode", table_name="retrieval_logs")
    op.drop_index("ix_retrieval_logs_project_created", table_name="retrieval_logs")
    op.drop_index("ix_retrieval_logs_project_id", table_name="retrieval_logs")
    op.drop_table("retrieval_logs")

    op.drop_index("ix_message_citations_project_message", table_name="message_citations")
    op.drop_index("ix_message_citations_chunk_id", table_name="message_citations")
    op.drop_index("ix_message_citations_message_id", table_name="message_citations")
    op.drop_index("ix_message_citations_project_id", table_name="message_citations")
    op.drop_table("message_citations")

    op.drop_index("ix_messages_project_conversation", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_index("ix_messages_project_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_project_updated", table_name="conversations")
    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.drop_table("conversations")

    op.execute("DROP TRIGGER IF EXISTS chunks_search_vector_update ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_search_vector_update")
    op.drop_index("ix_chunks_embedding", table_name="chunks")
    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_index("ix_chunks_project_chunk_index", table_name="chunks")
    op.drop_index("ix_chunks_project_document", table_name="chunks")
    op.drop_index("ix_chunks_content_hash", table_name="chunks")
    op.drop_index("ix_chunks_section_id", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_index("ix_chunks_project_id", table_name="chunks")
    op.drop_table("chunks")

    op.drop_index("ix_ingestion_jobs_project_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_project_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    op.drop_index("ix_document_sections_project_document", table_name="document_sections")
    op.drop_index("ix_document_sections_document_id", table_name="document_sections")
    op.drop_index("ix_document_sections_project_id", table_name="document_sections")
    op.drop_table("document_sections")

    op.drop_index("ix_documents_project_id_status", table_name="documents")
    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_table("documents")

    op.drop_table("app_settings")
    op.drop_table("projects")

    eval_run_status.drop(op.get_bind(), checkfirst=True)
    feedback_rating.drop(op.get_bind(), checkfirst=True)
    retrieval_mode.drop(op.get_bind(), checkfirst=True)
    message_role.drop(op.get_bind(), checkfirst=True)
    ingestion_job_status.drop(op.get_bind(), checkfirst=True)
    document_status.drop(op.get_bind(), checkfirst=True)
