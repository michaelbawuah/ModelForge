"""add browser sessions and OIDC PKCE login challenges

Revision ID: e19a7c63b204
Revises: c32f6a948d72
Create Date: 2026-09-19 18:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e19a7c63b204"
down_revision: str | Sequence[str] | None = "c32f6a948d72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_browser_sessions_user_id",
        "browser_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_browser_sessions_token_hash",
        "browser_sessions",
        ["token_hash"],
    )
    op.create_index(
        "ix_browser_sessions_expires_at",
        "browser_sessions",
        ["expires_at"],
    )

    op.create_table(
        "oidc_login_challenges",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("redirect_path", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("state_hash"),
    )
    op.create_index(
        "ix_oidc_login_challenges_expires_at",
        "oidc_login_challenges",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oidc_login_challenges_expires_at",
        table_name="oidc_login_challenges",
    )
    op.drop_table("oidc_login_challenges")

    op.drop_index(
        "ix_browser_sessions_expires_at",
        table_name="browser_sessions",
    )
    op.drop_index(
        "ix_browser_sessions_token_hash",
        table_name="browser_sessions",
    )
    op.drop_index(
        "ix_browser_sessions_user_id",
        table_name="browser_sessions",
    )
    op.drop_table("browser_sessions")
