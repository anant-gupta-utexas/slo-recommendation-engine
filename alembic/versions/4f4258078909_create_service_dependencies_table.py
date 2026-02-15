"""create_service_dependencies_table

Revision ID: 4f4258078909
Revises: 13cdc22bf8f3
Create Date: 2026-02-14 20:30:49.123744

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4f4258078909"
down_revision: str | Sequence[str] | None = "13cdc22bf8f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create service_dependencies table with foreign keys, indexes, and constraints."""
    # Create service_dependencies table
    op.create_table(
        "service_dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("communication_mode", sa.String(10), nullable=False),
        sa.Column("criticality", sa.String(20), nullable=False, server_default="hard"),
        sa.Column("protocol", sa.String(50), nullable=True),
        sa.Column("timeout_ms", sa.Integer, nullable=True),
        sa.Column("retry_config", postgresql.JSONB, nullable=True),
        sa.Column("discovery_source", sa.String(50), nullable=False),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="1.0"),
        sa.Column(
            "last_observed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("is_stale", sa.Boolean, nullable=False, server_default="false"),
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
        # Foreign keys
        sa.ForeignKeyConstraint(
            ["source_service_id"],
            ["services.id"],
            name="fk_source_service",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_service_id"],
            ["services.id"],
            name="fk_target_service",
            ondelete="CASCADE",
        ),
        # Unique constraint: same edge from same source (allow different sources)
        sa.UniqueConstraint(
            "source_service_id",
            "target_service_id",
            "discovery_source",
            name="uq_edge_per_source",
        ),
        # Check constraints
        sa.CheckConstraint(
            "source_service_id != target_service_id", name="ck_no_self_loops"
        ),
        sa.CheckConstraint(
            "communication_mode IN ('sync', 'async')", name="ck_communication_mode"
        ),
        sa.CheckConstraint(
            "criticality IN ('hard', 'soft', 'degraded')",
            name="ck_dependency_criticality",
        ),
        sa.CheckConstraint(
            "discovery_source IN ('manual', 'otel_service_graph', 'kubernetes', 'service_mesh')",
            name="ck_discovery_source",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_confidence_score_bounds",
        ),
        sa.CheckConstraint(
            "timeout_ms IS NULL OR timeout_ms > 0", name="ck_timeout_positive"
        ),
    )

    # Create indexes for graph traversal
    op.create_index(
        "idx_deps_source",
        "service_dependencies",
        ["source_service_id"],
        postgresql_where=sa.text("is_stale = false"),
    )
    op.create_index(
        "idx_deps_target",
        "service_dependencies",
        ["target_service_id"],
        postgresql_where=sa.text("is_stale = false"),
    )
    op.create_index(
        "idx_deps_source_target",
        "service_dependencies",
        ["source_service_id", "target_service_id"],
    )
    op.create_index(
        "idx_deps_discovery_source", "service_dependencies", ["discovery_source"]
    )
    op.create_index(
        "idx_deps_last_observed", "service_dependencies", ["last_observed_at"]
    )
    op.create_index(
        "idx_deps_stale",
        "service_dependencies",
        ["is_stale"],
        postgresql_where=sa.text("is_stale = true"),
    )

    # Create trigger for updated_at
    op.execute(
        """
        CREATE TRIGGER update_service_dependencies_updated_at
            BEFORE UPDATE ON service_dependencies
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    """Drop service_dependencies table, indexes, and triggers."""
    # Drop trigger
    op.execute(
        "DROP TRIGGER IF EXISTS update_service_dependencies_updated_at ON service_dependencies"
    )

    # Drop indexes
    op.drop_index("idx_deps_stale", table_name="service_dependencies")
    op.drop_index("idx_deps_last_observed", table_name="service_dependencies")
    op.drop_index("idx_deps_discovery_source", table_name="service_dependencies")
    op.drop_index("idx_deps_source_target", table_name="service_dependencies")
    op.drop_index("idx_deps_target", table_name="service_dependencies")
    op.drop_index("idx_deps_source", table_name="service_dependencies")

    # Drop table (foreign keys will be dropped automatically)
    op.drop_table("service_dependencies")
