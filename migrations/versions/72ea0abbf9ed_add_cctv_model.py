"""add cctv model

Revision ID: 72ea0abbf9ed
Revises: f9a03ecb2aa8
Create Date: 2025-01-02 13:51:58.982498

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '72ea0abbf9ed'
down_revision = 'f9a03ecb2aa8'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('cctvs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cctv_id', sa.String(length=50), nullable=False),
    sa.Column('location', sa.String(length=100), nullable=False),
    sa.Column('registration_date', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=True),
    sa.Column('access_permission', sa.String(length=50), nullable=False),
    sa.Column('last_access', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cctv_id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('cctvs')
    # ### end Alembic commands ###
