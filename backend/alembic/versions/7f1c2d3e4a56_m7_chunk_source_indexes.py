"""Add indexes used by document-scoped chunk browsing and cleanup."""

from alembic import op


revision = "7f1c2d3e4a56"
down_revision = "5d4e1a2b8f66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_chunks_doc_id_created_at",
        "chunks",
        ["doc_id", "created_at"],
    )
    op.create_index(
        "ix_chunks_kb_id_created_at",
        "chunks",
        ["kb_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_kb_id_created_at", table_name="chunks")
    op.drop_index("ix_chunks_doc_id_created_at", table_name="chunks")
