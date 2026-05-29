"""add supabase user id to users

Revision ID: 0fd672c28f85
Revises: c547746670d6
Create Date: 2026-05-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fd672c28f85'
down_revision: Union[str, None] = 'c547746670d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('supabase_user_id', sa.String(length=36), nullable=True))
    op.create_unique_constraint('uq_users_supabase_user_id', 'users', ['supabase_user_id'])
    op.create_table(
        'reviews',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('listing_id', sa.UUID(), nullable=True),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('buyer_name', sa.String(length=100), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['listing_id'], ['listings.id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('reviews')
    op.drop_constraint('uq_users_supabase_user_id', 'users', type_='unique')
    op.drop_column('users', 'supabase_user_id')