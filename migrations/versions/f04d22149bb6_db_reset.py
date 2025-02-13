"""db reset

Revision ID: f04d22149bb6
Revises: 
Create Date: 2025-02-13 10:04:29.530518

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f04d22149bb6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('dailycount',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('final_standard_count', sa.Integer(), nullable=False),
    sa.Column('final_break_count', sa.Integer(), nullable=False),
    sa.Column('final_normal_count', sa.Integer(), nullable=False),
    sa.Column('log_type', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('date')
    )
    op.create_table('normallog',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('standardlog',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('standardlog')
    op.drop_table('normallog')
    op.drop_table('dailycount')
    # ### end Alembic commands ###
