"""add_service_type_to_services

Revision ID: b8ca908bf04a
Revises: 0493364c9562
Create Date: 2026-02-16 17:13:17.138332

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8ca908bf04a'
down_revision: Union[str, Sequence[str], None] = '0493364c9562'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add service_type column with default 'internal'
    op.add_column(
        "services",
        sa.Column(
            "service_type",
            sa.String(length=20),
            nullable=False,
            server_default="internal",
        ),
    )

    # Add CHECK constraint for service_type values
    op.create_check_constraint(
        "ck_service_type",
        "services",
        "service_type IN ('internal', 'external')",
    )

    # Add published_sla column (external services only)
    op.add_column(
        "services", sa.Column("published_sla", sa.Numeric(precision=8, scale=6), nullable=True)
    )

    # Create partial index for external service lookups
    op.execute(
        """
        CREATE INDEX idx_services_external
        ON services(service_type)
        WHERE service_type = 'external'
    """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop partial index
    op.drop_index("idx_services_external", table_name="services")

    # Drop columns
    op.drop_column("services", "published_sla")
    op.drop_constraint("ck_service_type", "services", type_="check")
    op.drop_column("services", "service_type")
