"""configure daily observation auto analyze

Revision ID: ec5df5c66b92
Revises: 2165576649b7
Create Date: 2026-08-17 18:10:18.961154

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'ec5df5c66b92'
down_revision = '2165576649b7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE priceobservationdaily SET (
            autovacuum_analyze_scale_factor = 0.01,
            autovacuum_analyze_threshold = 1000
        )
        """
    )
    op.execute("ANALYZE priceobservationdaily")


def downgrade():
    op.execute(
        """
        ALTER TABLE priceobservationdaily RESET (
            autovacuum_analyze_scale_factor,
            autovacuum_analyze_threshold
        )
        """
    )
