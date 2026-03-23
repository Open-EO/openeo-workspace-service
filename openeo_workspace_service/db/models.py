"""
openeo_workspace_service/db/models.py
--------------------------------------
SQLAlchemy 2.x ORM mapping.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class WorkspaceRecord(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    provider_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="provisioning")
    details: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    quota: Mapped[int | None] = mapped_column(Integer)
    free: Mapped[int | None] = mapped_column(Integer)
    # JSON-encoded dicts
    _parameters_json: Mapped[str | None] = mapped_column("parameters_json", Text)
    _properties_json: Mapped[str | None] = mapped_column("properties_json", Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    @property
    def parameters(self) -> dict:
        return json.loads(self._parameters_json or "{}")

    @parameters.setter
    def parameters(self, value: dict) -> None:
        self._parameters_json = json.dumps(value)

    @property
    def properties(self) -> dict:
        return json.loads(self._properties_json or "{}")

    @properties.setter
    def properties(self, value: dict) -> None:
        self._properties_json = json.dumps(value)
