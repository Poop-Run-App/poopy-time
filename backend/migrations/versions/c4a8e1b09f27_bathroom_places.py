"""bathroom places and source records

Revision ID: c4a8e1b09f27
Revises: 677927e18136
Create Date: 2026-11-12 20:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4a8e1b09f27'
down_revision = '677927e18136'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'places',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('owner_key', sa.String(length=512), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('hours', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('seasonal', sa.Text(), nullable=True),
        sa.Column('wheelchair', sa.String(length=32), nullable=True),
        sa.Column('operator', sa.Text(), nullable=True),
        sa.Column('location_type', sa.Text(), nullable=True),
        sa.Column('changing_table', sa.Text(), nullable=True),
        sa.Column('fee', sa.Text(), nullable=True),
        sa.Column('website', sa.Text(), nullable=True),
        sa.Column('restroom_type', sa.Text(), nullable=True),
        sa.Column('primary_source', sa.String(length=64), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_key'),
    )
    op.create_index('ix_places_kind', 'places', ['kind'])

    op.create_table(
        'source_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('place_id', sa.Integer(), nullable=True),
        sa.Column('match_distance_m', sa.Float(), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('hours', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('seasonal', sa.Text(), nullable=True),
        sa.Column('wheelchair', sa.String(length=32), nullable=True),
        sa.Column('operator', sa.Text(), nullable=True),
        sa.Column('location_type', sa.Text(), nullable=True),
        sa.Column('changing_table', sa.Text(), nullable=True),
        sa.Column('fee', sa.Text(), nullable=True),
        sa.Column('website', sa.Text(), nullable=True),
        sa.Column('restroom_type', sa.Text(), nullable=True),
        sa.Column('raw', sa.JSON(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['place_id'], ['places.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'external_id', name='uq_source_records_source_external_id'),
    )
    op.create_index('ix_source_records_kind', 'source_records', ['kind'])
    op.create_index('ix_source_records_place_id', 'source_records', ['place_id'])
    op.create_index('ix_source_records_source', 'source_records', ['source'])


def downgrade():
    op.drop_index('ix_source_records_source', table_name='source_records')
    op.drop_index('ix_source_records_place_id', table_name='source_records')
    op.drop_index('ix_source_records_kind', table_name='source_records')
    op.drop_table('source_records')
    op.drop_index('ix_places_kind', table_name='places')
    op.drop_table('places')
