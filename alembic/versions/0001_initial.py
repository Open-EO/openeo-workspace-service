"""Initial workspace table

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("provider_type", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="provisioning"),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("quota", sa.Integer, nullable=True),
        sa.Column("free", sa.Integer, nullable=True),
        sa.Column("parameters_json", sa.Text, nullable=True),
        sa.Column("properties_json", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_workspaces_owner", "workspaces", ["owner"])


def downgrade() -> None:
    op.drop_index("ix_workspaces_owner", table_name="workspaces")
    op.drop_table("workspaces")
