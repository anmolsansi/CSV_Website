from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import CsvRow, JobTrack
from ..undo_models import BulkAction, BulkActionEffect
from ..undo_schemas import (
    BULK_ACTION_KINDS,
    BULK_ACTION_METADATA_DAYS,
    MAX_BULK_SNAPSHOT_BYTES,
    MAX_BULK_TARGETS,
    UNDO_FIELD_ALLOWLISTS,
    UNDO_WINDOW_MINUTES,
    UndoContractError,
)


ENTITY_MODELS = {
    "csv_row": CsvRow,
    "job_track": JobTrack,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise UndoContractError(
        "unsupported_snapshot_value",
        "Undo before-images may contain only JSON-safe scalar values.",
    )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_uuid(value: str, *, field: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise UndoContractError(
            "invalid_request_key",
            f"{field} must be a UUID.",
            field=field,
        ) from exc
    canonical = str(parsed)
    if canonical != str(value).lower():
        raise UndoContractError(
            "invalid_request_key",
            f"{field} must use canonical UUID form.",
            field=field,
        )
    return canonical


def snapshot_changed_fields(
    entity_type: str,
    entity: CsvRow | JobTrack,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Capture only changed allowlisted values needed to reverse a mutation."""
    allowlist = UNDO_FIELD_ALLOWLISTS.get(entity_type)
    if allowlist is None:
        raise UndoContractError(
            "unknown_entity_type",
            "Undo journal entity type is not supported.",
            field="entity_type",
        )

    before: dict[str, Any] = {}
    for field, next_value in changes.items():
        if field not in allowlist:
            raise UndoContractError(
                "forbidden_snapshot_field",
                "Undo snapshots may include only explicitly allowlisted mutable fields.",
                field=field,
            )
        current = getattr(entity, field)
        if current != next_value:
            before[field] = _json_value(current)
    return before


def validate_effect_batch(effects: list[dict[str, Any]]) -> None:
    if not effects:
        raise UndoContractError(
            "empty_bulk_action",
            "Bulk journal requires at least one changed target.",
            field="effects",
        )
    if len(effects) > MAX_BULK_TARGETS:
        raise UndoContractError(
            "bulk_target_limit_exceeded",
            f"Bulk actions may affect at most {MAX_BULK_TARGETS} targets.",
            status_code=413,
            field="effects",
        )

    safe_snapshots = []
    for index, effect in enumerate(effects):
        entity_type = effect.get("entity_type")
        allowlist = UNDO_FIELD_ALLOWLISTS.get(entity_type)
        if allowlist is None:
            raise UndoContractError(
                "unknown_entity_type",
                "Undo journal entity type is not supported.",
                field=f"effects[{index}].entity_type",
            )
        before = effect.get("before_json")
        if not isinstance(before, dict) or not before:
            raise UndoContractError(
                "empty_before_image",
                "Every effect must contain changed before-image fields.",
                field=f"effects[{index}].before_json",
            )
        forbidden = sorted(set(before) - set(allowlist))
        if forbidden:
            raise UndoContractError(
                "forbidden_snapshot_field",
                "Undo before-image contains a field outside the strict allowlist.",
                field=f"effects[{index}].before_json.{forbidden[0]}",
            )
        safe_snapshots.append({
            "entity_type": entity_type,
            "entity_id": int(effect.get("entity_id", 0)),
            "before_json": before,
            "after_version": int(effect.get("after_version", 0)),
        })

    size_bytes = len(_canonical_bytes(safe_snapshots))
    if size_bytes > MAX_BULK_SNAPSHOT_BYTES:
        raise UndoContractError(
            "bulk_snapshot_limit_exceeded",
            "Bulk undo before-images exceed the 1 MiB journal limit.",
            status_code=413,
            field="effects",
            context={"snapshot_bytes": size_bytes, "max_snapshot_bytes": MAX_BULK_SNAPSHOT_BYTES},
        )


def _effect_fingerprint(kind: str, effects: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "entity_type": effect["entity_type"],
            "entity_id": int(effect["entity_id"]),
            "before_json": effect["before_json"],
            "after_version": int(effect["after_version"]),
        }
        for effect in effects
    ]
    return hashlib.sha256(_canonical_bytes({"kind": kind, "effects": normalized})).hexdigest()


def _validate_owned_effect_targets(
    db: Session,
    *,
    user_id: int,
    effects: list[dict[str, Any]],
) -> None:
    grouped: dict[str, set[int]] = {"csv_row": set(), "job_track": set()}
    for effect in effects:
        entity_type = effect["entity_type"]
        entity_id = effect.get("entity_id")
        if isinstance(entity_id, bool) or not isinstance(entity_id, int) or entity_id < 1:
            raise UndoContractError(
                "invalid_effect_entity_id",
                "Undo effect entity_id must be a positive integer.",
                field="effects.entity_id",
            )
        grouped[entity_type].add(entity_id)

    for entity_type, ids in grouped.items():
        if not ids:
            continue
        model = ENTITY_MODELS[entity_type]
        owned = {
            entity_id
            for (entity_id,) in db.query(model.id).filter(
                model.user_id == user_id,
                model.id.in_(ids),
            ).all()
        }
        if owned != ids:
            # Do not disclose whether a missing ID belongs to another account.
            raise UndoContractError(
                "effect_target_not_found",
                "One or more undo effect targets were not found for this account.",
                status_code=404,
                field="effects",
            )


def create_bulk_action_journal(
    db: Session,
    *,
    user_id: int,
    kind: str,
    request_key: str,
    effects: list[dict[str, Any]],
    result: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> tuple[BulkAction, bool]:
    """Create one bounded owner-scoped journal, or replay an identical journal.

    This helper only records an already-planned transaction. JG-061 does not
    expose an Undo route or mutate entities through this function.
    """
    if kind not in BULK_ACTION_KINDS:
        raise UndoContractError(
            "invalid_bulk_action_kind",
            "Bulk action kind is not supported by the frozen F10 contract.",
            field="kind",
        )
    request_key = _canonical_uuid(request_key, field="request_key")
    validate_effect_batch(effects)
    _validate_owned_effect_targets(db, user_id=user_id, effects=effects)
    fingerprint = _effect_fingerprint(kind, effects)

    existing = db.query(BulkAction).filter(
        BulkAction.user_id == user_id,
        BulkAction.request_key == request_key,
    ).first()
    if existing is not None:
        if (existing.result_json or {}).get("journal_fingerprint") != fingerprint:
            raise UndoContractError(
                "request_key_conflict",
                "This operation key was already used for different bulk-action input.",
                status_code=409,
                field="request_key",
            )
        return existing, True

    reference_now = now or _utc_now()
    result_json = dict(result or {})
    result_json.update({
        "journal_fingerprint": fingerprint,
        "effect_count": len(effects),
    })
    action = BulkAction(
        user_id=user_id,
        kind=kind,
        request_key=request_key,
        status="completed",
        created_at=reference_now,
        undo_expires_at=reference_now + timedelta(minutes=UNDO_WINDOW_MINUTES),
        result_json=result_json,
    )
    db.add(action)
    db.flush()

    for effect in effects:
        db.add(BulkActionEffect(
            action_id=action.id,
            entity_type=effect["entity_type"],
            entity_id=int(effect["entity_id"]),
            before_json=effect["before_json"],
            after_version=int(effect["after_version"]),
            undo_status="pending",
        ))
    db.flush()
    return action, False


def compare_and_update(
    db: Session,
    *,
    entity_type: str,
    user_id: int,
    entity_id: int,
    expected_version: int,
    changes: dict[str, Any],
):
    """Owner-scoped optimistic update used by future transactional F10 writers."""
    model = ENTITY_MODELS.get(entity_type)
    allowlist = UNDO_FIELD_ALLOWLISTS.get(entity_type)
    if model is None or allowlist is None:
        raise UndoContractError("unknown_entity_type", "Unsupported versioned entity type.")
    forbidden = sorted(set(changes) - set(allowlist))
    if forbidden:
        raise UndoContractError(
            "forbidden_update_field",
            "Versioned helper may update only the F10 allowlist.",
            field=forbidden[0],
        )
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
        raise UndoContractError(
            "invalid_expected_version",
            "expected_version must be a positive integer.",
            field="expected_version",
        )

    query = db.query(model).filter(model.id == entity_id, model.user_id == user_id)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    entity = query.first()
    if entity is None:
        raise UndoContractError(
            "entity_not_found",
            "Versioned entity was not found for this account.",
            status_code=404,
        )
    if entity.version != expected_version:
        raise UndoContractError(
            "version_conflict",
            "Entity changed after the bulk action was planned.",
            status_code=409,
            context={"expected_version": expected_version, "current_version": entity.version},
        )

    changed = False
    for field, value in changes.items():
        if getattr(entity, field) != value:
            setattr(entity, field, value)
            changed = True
    if changed:
        db.flush()
        if entity.version != expected_version + 1:
            raise RuntimeError("versioned mutation did not advance exactly once")
    return entity


def cleanup_bulk_action_journals(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 500,
) -> dict[str, int]:
    """Scrub expired private before-images and remove metadata after 30 days."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    reference_now = now or _utc_now()
    metadata_cutoff = reference_now - timedelta(days=BULK_ACTION_METADATA_DAYS)

    old_actions = (
        db.query(BulkAction)
        .filter(BulkAction.created_at <= metadata_cutoff)
        .order_by(BulkAction.created_at.asc())
        .limit(limit)
        .all()
    )
    deleted = len(old_actions)
    for action in old_actions:
        db.delete(action)
    db.flush()

    remaining = max(0, limit - deleted)
    scrubbed_effects = 0
    expired_actions = 0
    if remaining:
        expired = (
            db.query(BulkAction)
            .filter(
                BulkAction.undo_expires_at <= reference_now,
                BulkAction.created_at > metadata_cutoff,
            )
            .order_by(BulkAction.undo_expires_at.asc())
            .limit(remaining)
            .all()
        )
        for action in expired:
            for effect in action.effects:
                if effect.before_json is not None:
                    effect.before_json = None
                    scrubbed_effects += 1
            if action.status in {"completed", "partially_undone"}:
                action.status = "expired"
                expired_actions += 1
    db.flush()
    return {
        "deleted_actions": deleted,
        "expired_actions": expired_actions,
        "scrubbed_effects": scrubbed_effects,
    }


def serialize_bulk_action_metadata_for_backup(
    db: Session,
    *,
    user_id: int,
) -> list[dict[str, Any]]:
    """Portable audit metadata only. It never carries actionable before-images."""
    actions = (
        db.query(BulkAction)
        .filter(BulkAction.user_id == user_id)
        .order_by(BulkAction.created_at.asc(), BulkAction.id.asc())
        .all()
    )
    return [
        {
            "id": action.id,
            "kind": action.kind,
            "request_key": action.request_key,
            "status": action.status,
            "created_at": action.created_at.isoformat(),
            "undo_expires_at": action.undo_expires_at.isoformat(),
            "result_json": action.result_json or {},
            "effect_count": len(action.effects),
            "undo_available": False,
        }
        for action in actions
    ]
