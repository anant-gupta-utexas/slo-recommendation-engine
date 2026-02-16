"""create_sli_aggregates_table

Revision ID: 0493364c9562
Revises: ecd649c39043
Create Date: 2026-02-15 22:29:09.017975

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

# revision identifiers, used by Alembic.
revision: str = "0493364c9562"
down_revision: str | Sequence[str] | None = "ecd649c39043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create sli_aggregates table for FR-2."""
    # Create sli_aggregates table
    op.create_table(
        "sli_aggregates",
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
        sa.Column("sli_type", sa.String(30), nullable=False),
        # Time window (renamed to avoid SQL reserved keyword)
        sa.Column("time_window", sa.String(10), nullable=False),
        # Aggregated value
        sa.Column("value", sa.DECIMAL, nullable=False),
        # Sample count
        sa.Column(
            "sample_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        # Computation timestamp
        sa.Column(
            "computed_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Constraints
        sa.CheckConstraint(
            "sli_type IN ('availability', 'latency_p50', 'latency_p95', 'latency_p99', 'latency_p999', 'error_rate', 'request_rate')",
            name="ck_sli_type",
        ),
        sa.CheckConstraint(
            "time_window IN ('1h', '1d', '7d', '28d', '90d')",
            name="ck_sli_window",
        ),
        sa.CheckConstraint(
            "sample_count >= 0",
            name="ck_sli_sample_count",
        ),
    )

    # Create index for primary lookup pattern
    op.create_index(
        "idx_sli_lookup",
        "sli_aggregates",
        ["service_id", "sli_type", "time_window", sa.text("computed_at DESC")],
    )


def downgrade() -> None:
    """Drop sli_aggregates table and indexes."""
    # Drop index
    op.drop_index("idx_sli_lookup", table_name="sli_aggregates")

    # Drop table
    op.drop_table("sli_aggregates")
