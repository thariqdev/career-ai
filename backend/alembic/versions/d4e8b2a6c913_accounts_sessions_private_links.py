"""accounts: passwords, login sessions, private saved links

Revision ID: d4e8b2a6c913
Revises: a7c3e91d4f20
Create Date: 2026-11-02 10:00:00.000000

Stage 97. Users get a password hash and a lockout counter; logged-in browsers get rows
in auth_sessions (only a hash of each token); saved learning links become private to
the user who saved them. Existing links go to the existing (oldest) user, so nothing
is lost.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e8b2a6c913'
down_revision: Union[str, None] = 'a7c3e91d4f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.String(), nullable=True))
    op.add_column('users', sa.Column('failed_logins', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'auth_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index(op.f('ix_auth_sessions_user_id'), 'auth_sessions', ['user_id'], unique=False)

    op.add_column('learning_resources', sa.Column('user_id', sa.Integer(), nullable=True))
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM learning_resources LIMIT 1")).first() is not None:
        if bind.execute(sa.text("SELECT 1 FROM users LIMIT 1")).first() is None:
            bind.execute(sa.text("INSERT INTO users (email) VALUES ('me@career-ai.local')"))
        bind.execute(sa.text("UPDATE learning_resources SET user_id = (SELECT MIN(id) FROM users)"))
    op.alter_column('learning_resources', 'user_id', nullable=False)
    op.create_foreign_key('learning_resources_user_id_fkey', 'learning_resources', 'users', ['user_id'], ['id'])
    op.drop_constraint('uq_learning_resource', 'learning_resources', type_='unique')
    op.create_unique_constraint('uq_learning_resource', 'learning_resources', ['user_id', 'skill_id', 'mode', 'url'])


def downgrade() -> None:
    op.drop_constraint('uq_learning_resource', 'learning_resources', type_='unique')
    op.create_unique_constraint('uq_learning_resource', 'learning_resources', ['skill_id', 'mode', 'url'])
    op.drop_constraint('learning_resources_user_id_fkey', 'learning_resources', type_='foreignkey')
    op.drop_column('learning_resources', 'user_id')
    op.drop_index(op.f('ix_auth_sessions_user_id'), table_name='auth_sessions')
    op.drop_table('auth_sessions')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_logins')
    op.drop_column('users', 'password_hash')
