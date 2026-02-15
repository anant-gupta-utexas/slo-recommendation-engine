"""create_services_table

Revision ID: 13cdc22bf8f3
Revises:
Create Date: 2026-02-14 20:30:15.842996

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "13cdc22bf8f3"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create services table with indexes and triggers."""
    # Create services table
    op.create_table(
        "services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("service_id", sa.String(255), unique=True, nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("criticality", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("team", sa.String(255), nullable=True),
        sa.Column("discovered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "criticality IN ('critical', 'high', 'medium', 'low')",
            name="ck_services_criticality",
        ),
    )

    # Create indexes
    op.create_index("idx_services_service_id", "services", ["service_id"])
    op.create_index(
        "idx_services_team",
        "services",
        ["team"],
        postgresql_where=sa.text("team IS NOT NULL"),
    )
    op.create_index("idx_services_criticality", "services", ["criticality"])
    op.create_index(
        "idx_services_discovered",
        "services",
        ["discovered"],
        postgresql_where=sa.text("discovered = true"),
    )

    # Create trigger function for updated_at
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Create trigger for services table
    op.execute(
        """
        CREATE TRIGGER update_services_updated_at
            BEFORE UPDATE ON services
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    """Drop services table, indexes, and triggers."""
    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS update_services_updated_at ON services")

    # Drop indexes (will be dropped with table, but explicit for clarity)
    op.drop_index("idx_services_discovered", table_name="services")
    op.drop_index("idx_services_criticality", table_name="services")
    op.drop_index("idx_services_team", table_name="services")
    op.drop_index("idx_services_service_id", table_name="services")

    # Drop table
    op.drop_table("services")

    # Note: trigger function is shared across tables, so we don't drop it here
    # It will be dropped in the last migration's downgrade
