"""scope customer resources to workspaces

Revision ID: c32f6a948d72
Revises: 8b7e2f19a4c1
Create Date: 2026-09-19 17:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c32f6a948d72"
down_revision: str | Sequence[str] | None = "8b7e2f19a4c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("models", sa.Column("workspace_id", sa.Integer(), nullable=True))
    op.execute("UPDATE models SET workspace_id = 1")
    op.alter_column(\n        "models",\n        "workspace_id",\n        existing_type=sa.Integer(),\n        nullable=False,\n    )
    op.create_foreign_key(
        "fk_models_workspace_id",
        "models",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_models_workspace_id", "models", ["workspace_id"])
    op.drop_index("ix_models_name", table_name="models")
    op.create_index("ix_models_name", "models", ["name"], unique=False)
    op.create_unique_constraint(
        "uq_models_workspace_name",
        "models",
        ["workspace_id", "name"],
    )

    op.add_column(
        "deployments",
        sa.Column("workspace_id", sa.Integer(), nullable=True),
    )
    op.execute("UPDATE deployments SET workspace_id = 1")
    op.alter_column(\n        "deployments",\n        "workspace_id",\n        existing_type=sa.Integer(),\n        nullable=False,\n    )
    op.create_foreign_key(
        "fk_deployments_workspace_id",
        "deployments",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_deployments_workspace_id",
        "deployments",
        ["workspace_id"],
    )
    op.drop_constraint(
        "uq_deployments_model_version_environment",
        "deployments",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_deployments_workspace_version_environment",
        "deployments",
        ["workspace_id", "model_version_id", "environment"],
    )

    op.create_table(
        "deployment_targets_v2",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("active_deployment_id", sa.Integer(), nullable=False),
        sa.Column("canary_deployment_id", sa.Integer(), nullable=True),
        sa.Column(
            "canary_weight",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "canary_weight >= 0 AND canary_weight <= 100",
            name="ck_deployment_targets_canary_weight",
        ),
        sa.ForeignKeyConstraint(
            ["active_deployment_id"],
            ["deployments.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["canary_deployment_id"],
            ["deployments.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("active_deployment_id"),
        sa.UniqueConstraint("canary_deployment_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "environment",
            name="uq_deployment_targets_workspace_environment",
        ),
    )
    op.execute(
        "INSERT INTO deployment_targets_v2 "
        "(workspace_id, environment, active_deployment_id, "
        "canary_deployment_id, canary_weight, updated_at) "
        "SELECT 1, environment, active_deployment_id, "
        "canary_deployment_id, canary_weight, updated_at "
        "FROM deployment_targets"
    )
    op.drop_table("deployment_targets")
    op.rename_table("deployment_targets_v2", "deployment_targets")
    op.create_index(
        "ix_deployment_targets_workspace_id",
        "deployment_targets",
        ["workspace_id"],
    )
    op.create_index(
        "ix_deployment_targets_environment",
        "deployment_targets",
        ["environment"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Workspace isolation migration is intentionally non-destructive and "
        "does not support automatic downgrade."
    )
