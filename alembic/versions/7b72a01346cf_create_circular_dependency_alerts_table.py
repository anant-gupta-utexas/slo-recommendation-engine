"""create_circular_dependency_alerts_table

Revision ID: 7b72a01346cf
Revises: 4f4258078909
Create Date: 2026-02-14 20:32:02.650107

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7b72a01346cf"
down_revision: str | Sequence[str] | None = "4f4258078909"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create circular_dependency_alerts table with indexes."""
    # Create circular_dependency_alerts table
    op.create_table(
        "circular_dependency_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cycle_path", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("acknowledged_by", sa.String(255), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column(
            "detected_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Unique constraint: prevent duplicate alerts for same cycle
        sa.UniqueConstraint("cycle_path", name="uq_cycle_path"),
        # Check constraint: status validation
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')", name="ck_alert_status"
        ),
    )

    # Create indexes
    op.create_index(
        "idx_circular_deps_status",
        "circular_dependency_alerts",
        ["status"],
        postgresql_where=sa.text("status IN ('open', 'acknowledged')"),
    )
    op.create_index(
        "idx_circular_deps_detected_at",
        "circular_dependency_alerts",
        ["detected_at"],
        postgresql_using="btree",
    )


def downgrade() -> None:
    """Drop circular_dependency_alerts table and indexes."""
    # Drop indexes
    op.drop_index("idx_circular_deps_detected_at", table_name="circular_dependency_alerts")
    op.drop_index("idx_circular_deps_status", table_name="circular_dependency_alerts")

    # Drop table
    op.drop_table("circular_dependency_alerts")

    # Drop trigger function (shared across all tables, drop in final downgrade)
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE")
