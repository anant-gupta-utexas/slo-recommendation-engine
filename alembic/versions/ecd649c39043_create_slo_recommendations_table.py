"""create_slo_recommendations_table

Revision ID: ecd649c39043
Revises: 2d6425d45f9f
Create Date: 2026-02-15 22:29:05.262732

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

# revision identifiers, used by Alembic.
revision: str = "ecd649c39043"
down_revision: str | Sequence[str] | None = "2d6425d45f9f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create slo_recommendations table for FR-2."""
    # Create slo_recommendations table
    op.create_table(
        "slo_recommendations",
        # Primary key
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Foreign key to services
        sa.Column(
            "service_id",
            UUID(as_uuid=True),
            sa.ForeignKey("services.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SLI type
        sa.Column("sli_type", sa.String(20), nullable=False),
        # Metric name
        sa.Column("metric", sa.String(50), nullable=False),
        # Recommendation tiers (JSONB)
        sa.Column("tiers", JSONB, nullable=False),
        # Explanation (JSONB)
        sa.Column("explanation", JSONB, nullable=False),
        # Data quality metadata (JSONB)
        sa.Column("data_quality", JSONB, nullable=False),
        # Lookback window
        sa.Column(
            "lookback_window_start",
            TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "lookback_window_end",
            TIMESTAMP(timezone=True),
            nullable=False,
        ),
        # Generation and expiry timestamps
        sa.Column(
            "generated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "expires_at",
            TIMESTAMP(timezone=True),
            nullable=False,
        ),
        # Status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        # Constraints
        sa.CheckConstraint(
            "sli_type IN ('availability', 'latency')",
            name="ck_slo_rec_sli_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'expired')",
            name="ck_slo_rec_status",
        ),
        sa.CheckConstraint(
            "lookback_window_start < lookback_window_end",
            name="ck_slo_rec_lookback_window",
        ),
    )

    # Create indexes for efficient queries
    # Primary lookup: active recommendations by service
    op.create_index(
        "idx_slo_rec_service_active",
        "slo_recommendations",
        ["service_id", "status"],
        postgresql_where=sa.text("status = 'active'"),
    )

    # Expiry cleanup
    op.create_index(
        "idx_slo_rec_expires",
        "slo_recommendations",
        ["expires_at"],
        postgresql_where=sa.text("status = 'active'"),
    )

    # Lookup by sli_type
    op.create_index(
        "idx_slo_rec_sli_type",
        "slo_recommendations",
        ["service_id", "sli_type", "status"],
    )


def downgrade() -> None:
    """Drop slo_recommendations table and indexes."""
    # Drop indexes
    op.drop_index("idx_slo_rec_sli_type", table_name="slo_recommendations")
    op.drop_index("idx_slo_rec_expires", table_name="slo_recommendations")
    op.drop_index("idx_slo_rec_service_active", table_name="slo_recommendations")

    # Drop table
    op.drop_table("slo_recommendations")
