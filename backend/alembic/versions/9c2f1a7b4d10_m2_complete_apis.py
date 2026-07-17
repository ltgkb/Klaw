"""m2: add paused to executionstatus + workspace_files + push_channels

Revision ID: 9c2f1a7b4d10
Revises: 03e760fba145
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c2f1a7b4d10'
down_revision: Union[str, None] = '03e760fba145'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 修复 executionstatus 枚举: 补 'paused' 值 (PRD 暂停/恢复功能所需)
    #    PostgreSQL 的 ALTER TYPE ... ADD VALUE 不能在事务内执行, 用 autocommit_block。
    if bind.dialect.name == 'postgresql':
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE executionstatus ADD VALUE IF NOT EXISTS 'paused'")

    # 2. 文件工作区表 (PRD 6.7)
    op.create_table('workspace_files',
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('object_name', sa.String(length=1024), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('content_type', sa.String(length=255), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # 3. 推送渠道配置表 (PRD 6.6)
    op.create_table('push_channels',
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('type', sa.Enum('feishu', 'wechat', 'telegram', 'hermes', name='channeltype'), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('push_channels')
    op.drop_table('workspace_files')
    # executionstatus 的 'paused' 值在 PostgreSQL 上无法删除, 留存。
