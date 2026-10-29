"""create note_embeddings table (pgvector where available)

Revision ID: a7c3e91d4f20
Revises: b2eab744a82e
Create Date: 2026-10-29 12:00:00.000000

Stored note embeddings for the assistant's meaning search. On a PostgreSQL that offers
the pgvector extension (Neon does), the extension is enabled and the column becomes
pgvector's `vector` type. Where pgvector isn't installed (e.g. a local Windows
PostgreSQL), the column stays `text`; the app reads and writes both the same way.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7c3e91d4f20'
down_revision: Union[str, None] = 'b2eab744a82e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _pgvector_available() -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bind.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).first() is not None


def upgrade() -> None:
    op.create_table(
        'note_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('note_key', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('dims', sa.Integer(), nullable=False),
        sa.Column('vector', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('note_key', 'model_name', 'dims', name='uq_note_embeddings_key_model_dims'),
    )
    if _pgvector_available():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        # No fixed size: one table holds 768-dim Gemini and Ollama rows (kept apart by model).
        op.execute("ALTER TABLE note_embeddings ALTER COLUMN vector TYPE vector USING vector::vector")


def downgrade() -> None:
    op.drop_table('note_embeddings')  # the extension is left in place: other things may use it
