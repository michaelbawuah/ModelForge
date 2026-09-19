"""add canary deployment targets

Revision ID: 4f2d9c7a1b83
Revises: eca2e545b4c6
Create Date: 2026-09-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4f2d9c7a1b83"
down_revision: str | Sequence[str] | None = "eca2e545b4c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deployment_targets",
        sa.Column("canary_deployment_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "deployment_targets",
        sa.Column(
            "canary_weight",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_deployment_targets_canary_deployment_id",
        "deployment_targets",
        ["canary_deployment_id"],
    )
    op.create_foreign_key(
        "fk_deployment_targets_canary_deployment_id",
        "deployment_targets",
        "deployments",
        ["canary_deployment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_deployment_targets_canary_weight",
        "deployment_targets",
        "canary_weight >= 0 AND canary_weight <= 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_deployment_targets_canary_weight",
        "deployment_targets",
        type_="check",
    )
    op.drop_constraint(
        "fk_deployment_targets_canary_deployment_id",
        "deployment_targets",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_deployment_targets_canary_deployment_id",
        "deployment_targets",
        type_="unique",
    )
    op.drop_column("deployment_targets", "canary_weight")
    op.drop_column("deployment_targets", "canary_deployment_id")
