"""run_evaluations table

Revision ID: 6a120e159144
Revises: 7211bf900ce3
Create Date: 2026-05-27 17:50:50.754365
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '6a120e159144'
down_revision: Union[str, None] = '7211bf900ce3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("overall", sa.Numeric(4, 3), nullable=True),
        sa.Column("scores", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("verdict", sa.String(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_run_evaluations_run_id", "run_evaluations", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_run_evaluations_run_id", table_name="run_evaluations")
    op.drop_table("run_evaluations")
