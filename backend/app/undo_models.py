from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import relationship

from .database import Base
from .models import CsvRow, JobTrack


BULK_ACTION_KIND_VALUES = ("archive_rows", "update_rows", "update_tracks")
BULK_ACTION_STATUS_VALUES = ("completed", "undone", "partially_undone", "expired")
BULK_EFFECT_STATUS_VALUES = ("pending", "restored", "conflict", "missing")


# JG-061 adds optimistic versions to the existing mapped classes without
# duplicating their large declarations. DeclarativeMeta supports appending a
# mapped Column after class declaration, and importing app registers these
# columns before runtime sessions are created.
if "version" not in CsvRow.__table__.c:
    CsvRow.version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    CsvRow.__table__.append_constraint(
        CheckConstraint("version > 0", name="ck_csv_rows_version_positive")
    )

if "version" not in JobTrack.__table__.c:
    JobTrack.version = Column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    JobTrack.__table__.append_constraint(
        CheckConstraint("version > 0", name="ck_job_tracks_version_positive")
    )


def _increment_version_for_real_change(mapper, connection, target) -> None:
    state = inspect(target)
    changed = any(
        state.attrs[column.key].history.has_changes()
        for column in mapper.column_attrs
        if column.key != "version"
    )
    if changed:
        target.version = int(target.version or 1) + 1


# ORM writers receive a version increment automatically. Raw/bulk SQL mutation
# paths are inventoried separately and must route through the shared helper.
event.listen(CsvRow, "before_update", _increment_version_for_real_change)
event.listen(JobTrack, "before_update", _increment_version_for_real_change)


class BulkAction(Base):
    __tablename__ = "bulk_actions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = Column(String(32), nullable=False)
    request_key = Column(String(36), nullable=False)
    status = Column(String(24), nullable=False, default="completed", index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    undo_expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc) + timedelta(minutes=10),
        index=True,
    )
    result_json = Column(JSON, nullable=False, default=dict)

    effects = relationship(
        "BulkActionEffect",
        back_populates="action",
        cascade="all, delete-orphan",
        order_by="BulkActionEffect.id",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_bulk_actions_user_request_key"),
        CheckConstraint(
            "kind IN ('archive_rows', 'update_rows', 'update_tracks')",
            name="ck_bulk_actions_kind",
        ),
        CheckConstraint(
            "status IN ('completed', 'undone', 'partially_undone', 'expired')",
            name="ck_bulk_actions_status",
        ),
        CheckConstraint("length(id) = 36", name="ck_bulk_actions_id_length"),
        CheckConstraint("length(request_key) = 36", name="ck_bulk_actions_request_key_length"),
        Index("ix_bulk_actions_user_created", "user_id", "created_at"),
        Index("ix_bulk_actions_user_undo_expiry", "user_id", "undo_expires_at"),
    )


class BulkActionEffect(Base):
    __tablename__ = "bulk_action_effects"

    id = Column(Integer, primary_key=True)
    action_id = Column(
        String(36),
        ForeignKey("bulk_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type = Column(String(16), nullable=False)
    entity_id = Column(Integer, nullable=False)
    before_json = Column(JSON, nullable=True)
    after_version = Column(Integer, nullable=False)
    undo_status = Column(String(16), nullable=False, default="pending", index=True)

    action = relationship("BulkAction", back_populates="effects")

    __table_args__ = (
        UniqueConstraint(
            "action_id",
            "entity_type",
            "entity_id",
            name="uq_bulk_action_effect_entity",
        ),
        CheckConstraint(
            "entity_type IN ('csv_row', 'job_track')",
            name="ck_bulk_action_effects_entity_type",
        ),
        CheckConstraint(
            "undo_status IN ('pending', 'restored', 'conflict', 'missing')",
            name="ck_bulk_action_effects_undo_status",
        ),
        CheckConstraint("after_version > 0", name="ck_bulk_action_effects_after_version_positive"),
        Index("ix_bulk_action_effects_action_status", "action_id", "undo_status"),
    )
