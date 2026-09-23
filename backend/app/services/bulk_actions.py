from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from sqlalchemy.orm import Session

from ..config import settings
from ..models import CsvRow, JobTrack
from ..undo_models import BulkAction, BulkActionEffect
from ..undo_schemas import MAX_BULK_TARGETS, UndoContractError
from .lifecycle import apply_job_track_changes
from .reminders import sync_track_reminder
from .undo_foundation import create_bulk_action_journal, snapshot_changed_fields


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical_request_key(value: str | None) -> str:
    if value is None:
        return str(uuid4())
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise UndoContractError(
            "invalid_request_key",
            "request_key must be a UUID.",
            field="request_key",
        ) from exc


def _normalize_ids(values: Iterable[int], *, field: str = "row_ids") -> list[int]:
    ids = list(values)
    if not ids:
        raise UndoContractError("empty_bulk_action", "Select at least one row.", field=field)
    if len(ids) > MAX_BULK_TARGETS:
        raise UndoContractError(
            "bulk_target_limit_exceeded",
            f"Bulk actions may affect at most {MAX_BULK_TARGETS} targets.",
            status_code=413,
            field=field,
        )
    normalized: list[int] = []
    seen: set[int] = set()
    for value in ids:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise UndoContractError(
                "invalid_target_id", "Row IDs must be positive integers.", field=field
            )
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def _owned_rows(
    db: Session,
    *,
    user_id: int,
    row_ids: list[int],
    for_update: bool = True,
) -> list[CsvRow]:
    query = db.query(CsvRow).filter(CsvRow.user_id == user_id, CsvRow.id.in_(row_ids))
    if for_update and db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    found = query.all()
    by_id = {row.id: row for row in found}
    if set(by_id) != set(row_ids):
        raise UndoContractError(
            "target_not_found",
            "One or more rows were not found for this account.",
            status_code=404,
            field="row_ids",
        )
    return [by_id[row_id] for row_id in row_ids]


def _action_result(action: BulkAction) -> dict[str, Any]:
    result = dict(action.result_json or {})
    result.update(
        {
            "operation_id": action.id,
            "undo_expires_at": action.undo_expires_at.isoformat(),
            "undo_status": action.status,
        }
    )
    return result


def archive_rows(
    db: Session,
    *,
    user_id: int,
    row_ids: Iterable[int],
    request_key: str | None,
    expected_versions: dict[int, int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Archive rows and write their undo journal in the caller-owned transaction.

    Historical callers omitted request_key and received exactly archived/deleted.
    First-party F10 callers send a stable request_key and receive additive Undo
    metadata. Both paths still journal the mutation transactionally.
    """
    ids = _normalize_ids(row_ids)
    legacy_response = request_key is None
    key = _canonical_request_key(request_key)
    existing = db.query(BulkAction).filter(
        BulkAction.user_id == user_id,
        BulkAction.request_key == key,
    ).first()
    if existing is not None:
        if legacy_response:
            return {
                "archived": int((existing.result_json or {}).get("archived", 0)),
                "deleted": int((existing.result_json or {}).get("deleted", 0)),
            }
        return _action_result(existing)

    rows = _owned_rows(db, user_id=user_id, row_ids=ids)
    expected_versions = expected_versions or {}
    reference_now = now or utc_now()
    archive_time = reference_now.astimezone(timezone.utc).replace(tzinfo=None)

    planned: list[tuple[CsvRow, dict[str, Any]]] = []
    for row in rows:
        expected = expected_versions.get(row.id)
        if expected is not None and int(row.version) != int(expected):
            raise UndoContractError(
                "version_conflict",
                "A selected row changed. Reload before archiving.",
                status_code=409,
                field=f"expected_versions.{row.id}",
                context={"row_id": row.id, "expected_version": expected, "current_version": row.version},
            )
        if row.archived:
            continue
        changes = {"archived": True, "archived_at": archive_time}
        before = snapshot_changed_fields("csv_row", row, changes)
        planned.append((row, before))

    if not planned:
        if legacy_response:
            return {"archived": 0, "deleted": 0}
        return {
            "archived": 0,
            "deleted": 0,
            "operation_id": None,
            "undo_expires_at": None,
            "undo_status": "no_change",
        }

    effects: list[dict[str, Any]] = []
    for row, before in planned:
        row.archived = True
        row.archived_at = archive_time
        db.flush()
        effects.append(
            {
                "entity_type": "csv_row",
                "entity_id": row.id,
                "before_json": before,
                "after_version": int(row.version),
            }
        )

    action, replayed = create_bulk_action_journal(
        db,
        user_id=user_id,
        kind="archive_rows",
        request_key=key,
        effects=effects,
        result={"archived": len(effects), "deleted": 0},
        now=reference_now,
    )
    action.result_json = {
        **(action.result_json or {}),
        "archived": len(effects),
        "deleted": 0,
    }
    db.flush()
    if legacy_response:
        return {"archived": len(effects), "deleted": 0}
    result = _action_result(action)
    result["replayed"] = replayed
    return result


def _decode_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field.endswith("_at") and isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    return value


def _load_effect_entity(db: Session, *, user_id: int, effect: BulkActionEffect):
    model = CsvRow if effect.entity_type == "csv_row" else JobTrack
    query = db.query(model).filter(model.id == effect.entity_id, model.user_id == user_id)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    return query.first()


def _restore_track(
    db: Session,
    *,
    user_id: int,
    track: JobTrack,
    before: dict[str, Any],
    action_id: str,
) -> None:
    lifecycle_fields = {"status", "applied_at", "follow_up_at"}
    direct_fields = set(before) - lifecycle_fields
    for field in direct_fields:
        setattr(track, field, _decode_value(field, before[field]))

    lifecycle_kwargs: dict[str, Any] = {}
    for field in lifecycle_fields:
        if field in before:
            lifecycle_kwargs[field] = _decode_value(field, before[field])
    if lifecycle_kwargs:
        operation_id = uuid5(NAMESPACE_URL, f"jobgrid:undo:{action_id}:{track.id}")
        apply_job_track_changes(
            db,
            user_id=user_id,
            item=track,
            source="bulk_undo",
            operation_id=operation_id,
            now=datetime.utcnow(),
            infer_applied_at_from_status=False,
            **lifecycle_kwargs,
        )
        if "status" in lifecycle_kwargs or "follow_up_at" in lifecycle_kwargs:
            sync_track_reminder(
                db,
                user_id=user_id,
                track_id=track.id,
                now_utc=utc_now(),
            )


def undo_action(
    db: Session,
    *,
    user_id: int,
    action_id: str,
    mode: str = "all_or_nothing",
    now: datetime | None = None,
) -> dict[str, Any]:
    if mode not in {"all_or_nothing", "restore_unchanged"}:
        raise UndoContractError(
            "invalid_undo_mode",
            "mode must be all_or_nothing or restore_unchanged.",
            field="mode",
        )
    action = db.query(BulkAction).filter(
        BulkAction.id == action_id,
        BulkAction.user_id == user_id,
    ).first()
    if action is None:
        raise UndoContractError(
            "bulk_action_not_found",
            "Bulk action was not found.",
            status_code=404,
        )

    reference_now = now or utc_now()
    if action.status == "expired" or _db_utc(action.undo_expires_at) <= _db_utc(reference_now):
        raise UndoContractError(
            "undo_expired",
            "Immediate Undo has expired. Archived rows remain recoverable from Archive.",
            status_code=410,
            context={"operation_id": action.id, "undo_expires_at": action.undo_expires_at.isoformat()},
        )

    effects = list(action.effects)
    if any(effect.before_json is None and effect.undo_status != "restored" for effect in effects):
        raise UndoContractError(
            "undo_expired",
            "Immediate Undo data has expired. Archived rows remain recoverable from Archive.",
            status_code=410,
        )

    already_restored = sum(effect.undo_status == "restored" for effect in effects)
    if action.status == "undone" or already_restored == len(effects):
        result = dict(action.result_json or {})
        undo_result = result.get("undo_result") or {
            "restored": already_restored,
            "conflicts": 0,
            "missing": 0,
        }
        return {
            "operation_id": action.id,
            "status": "undone",
            **undo_result,
            "replayed": True,
        }

    states: list[tuple[BulkActionEffect, Any | None, str]] = []
    for effect in effects:
        if effect.undo_status == "restored":
            states.append((effect, None, "restored"))
            continue
        entity = _load_effect_entity(db, user_id=user_id, effect=effect)
        if entity is None:
            states.append((effect, None, "missing"))
        elif int(entity.version) != int(effect.after_version):
            states.append((effect, entity, "conflict"))
        else:
            states.append((effect, entity, "restorable"))

    conflicts = sum(state == "conflict" for _, _, state in states)
    missing = sum(state == "missing" for _, _, state in states)
    if mode == "all_or_nothing" and (conflicts or missing):
        for effect, _, state in states:
            if state in {"conflict", "missing"}:
                effect.undo_status = state
        action.result_json = {
            **(action.result_json or {}),
            "last_undo_preflight": {"conflicts": conflicts, "missing": missing},
        }
        db.flush()
        raise UndoContractError(
            "undo_conflict",
            "Undo was not applied because one or more records changed or disappeared.",
            status_code=409,
            context={
                "operation_id": action.id,
                "restored": 0,
                "conflicts": conflicts,
                "missing": missing,
            },
        )

    restored = 0
    for effect, entity, state in states:
        if state == "restored":
            continue
        if state == "missing":
            effect.undo_status = "missing"
            continue
        if state == "conflict":
            effect.undo_status = "conflict"
            continue
        before = dict(effect.before_json or {})
        if effect.entity_type == "job_track":
            _restore_track(
                db,
                user_id=user_id,
                track=entity,
                before=before,
                action_id=action.id,
            )
        else:
            for field, value in before.items():
                setattr(entity, field, _decode_value(field, value))
        db.flush()
        effect.undo_status = "restored"
        restored += 1

    total_restored = sum(effect.undo_status == "restored" for effect in effects)
    conflicts = sum(effect.undo_status == "conflict" for effect in effects)
    missing = sum(effect.undo_status == "missing" for effect in effects)
    action.status = "undone" if total_restored == len(effects) else "partially_undone"
    undo_result = {
        "restored": total_restored,
        "conflicts": conflicts,
        "missing": missing,
    }
    action.result_json = {**(action.result_json or {}), "undo_result": undo_result}
    db.flush()
    return {
        "operation_id": action.id,
        "status": action.status,
        **undo_result,
        "restored_this_request": restored,
        "replayed": False,
    }


def restore_archived_rows(
    db: Session,
    *,
    user_id: int,
    row_ids: Iterable[int],
    expected_versions: dict[int, int],
    mode: str = "all_or_nothing",
) -> dict[str, Any]:
    ids = _normalize_ids(row_ids)
    if mode not in {"all_or_nothing", "restore_unchanged"}:
        raise UndoContractError("invalid_restore_mode", "Invalid restore mode.", field="mode")
    rows = _owned_rows(db, user_id=user_id, row_ids=ids)
    states: list[tuple[CsvRow, str]] = []
    for row in rows:
        expected = expected_versions.get(row.id)
        if expected is None:
            raise UndoContractError(
                "missing_expected_version",
                "Every restored row requires its current version.",
                field=f"expected_versions.{row.id}",
            )
        if not row.archived:
            states.append((row, "missing"))
        elif int(row.version) != int(expected):
            states.append((row, "conflict"))
        else:
            states.append((row, "restorable"))

    conflicts = sum(state == "conflict" for _, state in states)
    missing = sum(state == "missing" for _, state in states)
    if mode == "all_or_nothing" and (conflicts or missing):
        raise UndoContractError(
            "restore_conflict",
            "Restore was not applied because one or more rows changed.",
            status_code=409,
            context={"restored": 0, "conflicts": conflicts, "missing": missing},
        )

    restored = 0
    for row, state in states:
        if state != "restorable":
            continue
        row.archived = False
        row.archived_at = None
        db.flush()
        restored += 1
    return {"restored": restored, "conflicts": conflicts, "missing": missing}


def _delete_fingerprint(user_id: int, rows: list[CsvRow]) -> str:
    material = {
        "user_id": user_id,
        "rows": [{"id": row.id, "version": int(row.version)} for row in rows],
    }
    return json.dumps(material, sort_keys=True, separators=(",", ":"))


def permanent_delete_preview(
    db: Session,
    *,
    user_id: int,
    row_ids: Iterable[int],
    expected_versions: dict[int, int] | None = None,
) -> dict[str, Any]:
    ids = _normalize_ids(row_ids)
    rows = _owned_rows(db, user_id=user_id, row_ids=ids, for_update=False)
    for row in rows:
        if not row.archived:
            raise UndoContractError(
                "active_row_delete_forbidden",
                "Permanent deletion is available only for rows already in Archive.",
                status_code=409,
                field="row_ids",
            )
        expected = (expected_versions or {}).get(row.id)
        if expected is not None and int(row.version) != int(expected):
            raise UndoContractError(
                "version_conflict",
                "An archived row changed. Reload before deleting.",
                status_code=409,
            )
    fingerprint = _delete_fingerprint(user_id, rows)
    token = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), fingerprint.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {
        "eligible_count": len(rows),
        "row_ids": ids,
        "confirmation_token": token,
        "automatic_purge_enabled": False,
        "warning": "This permanently deletes only the archived source rows. Application and document history are preserved.",
    }


def permanent_delete_rows(
    db: Session,
    *,
    user_id: int,
    row_ids: Iterable[int],
    confirmation_token: str | None,
    expected_versions: dict[int, int] | None = None,
) -> dict[str, Any]:
    ids = _normalize_ids(row_ids)
    rows = _owned_rows(db, user_id=user_id, row_ids=ids)
    preview = permanent_delete_preview(
        db,
        user_id=user_id,
        row_ids=ids,
        expected_versions=expected_versions,
    )
    if not confirmation_token or not hmac.compare_digest(
        confirmation_token, preview["confirmation_token"]
    ):
        raise UndoContractError(
            "confirmation_required",
            "Permanent deletion requires the current preview confirmation token.",
            status_code=409,
            field="confirmation_token",
        )

    tracks = db.query(JobTrack).filter(
        JobTrack.user_id == user_id,
        JobTrack.csv_row_id.in_(ids),
    ).all()
    for track in tracks:
        track.csv_row_id = None
    duplicates = db.query(CsvRow).filter(
        CsvRow.user_id == user_id,
        CsvRow.duplicate_of_id.in_(ids),
    ).all()
    for duplicate in duplicates:
        duplicate.duplicate_of_id = None
    db.flush()

    for row in rows:
        db.delete(row)
    db.flush()
    return {
        "deleted": len(rows),
        "archived": 0,
        "detached_applications": len(tracks),
        "detached_duplicates": len(duplicates),
        "automatic_purge_enabled": False,
    }