"""create_api_keys_table

Revision ID: 2d6425d45f9f
Revises: 7b72a01346cf
Create Date: 2026-02-15 09:50:59.266671

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

# revision identifiers, used by Alembic.
revision: str = "2d6425d45f9f"
down_revision: str | Sequence[str] | None = "7b72a01346cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create api_keys table for API authentication."""
    op.create_table(
        "api_keys",
        # Primary key
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Key identifier
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        # Bcrypt hash
        sa.Column("key_hash", sa.String(255), nullable=False),
        # Client metadata
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        # Revocation
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("revoked_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(255), nullable=True),
        # Audit timestamps
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_used_at", TIMESTAMP(timezone=True), nullable=True),
    )

    # Create indexes
    op.create_index("ix_api_keys_name", "api_keys", ["name"])
    op.create_index("ix_api_keys_is_active", "api_keys", ["is_active"])


def downgrade() -> None:
    """Drop api_keys table."""
    op.drop_index("ix_api_keys_is_active", table_name="api_keys")
    op.drop_index("ix_api_keys_name", table_name="api_keys")
    op.drop_table("api_keys")
