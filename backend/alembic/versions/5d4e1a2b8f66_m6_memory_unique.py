"""m6: memories 表加 (user_id, key, session_id) 唯一约束

配合 save_memory 的 upsert 语义: 并发插入冲突 (IntegrityError) 转 update。

Revision ID: 5d4e1a2b8f66
Revises: 4b2e9a1c7d33
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5d4e1a2b8f66'
down_revision: Union[str, None] = '4b2e9a1c7d33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_memories_user_key_session',
        'memories',
        ['user_id', 'key', 'session_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_memories_user_key_session', 'memories', type_='unique')
