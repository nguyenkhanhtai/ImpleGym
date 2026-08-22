"""add_contest_session_fields

Revision ID: a1b2c3d4e5f6
Revises: e81833419e8c
Create Date: 2026-08-21 11:32:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e81833419e8c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema with contest session fields."""
    with op.batch_alter_table("practice_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("name", sa.String(length=256), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("problem_ids", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("current_problem_index", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("problem_statuses", sa.JSON(), nullable=False, server_default="{}")
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("practice_sessions", schema=None) as batch_op:
        batch_op.drop_column("problem_statuses")
        batch_op.drop_column("current_problem_index")
        batch_op.drop_column("problem_ids")
        batch_op.drop_column("name")
