from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..evidence_schemas import (
    EVIDENCE_RECEIPT_RETENTION_DAYS,
    EVIDENCE_SOFT_DELETE_RETENTION_DAYS,
)
from ..models import ApplicationEvidence, EvidenceCreateReceipt, JobTrack


MAX_EVIDENCE_MAINTENANCE_BATCH = 500


class EvidenceServiceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EvidenceMaintenanceResult:
    bodies_blanked: int
    receipts_deleted: int


def require_owned_track(
    session: Session,
    *,
    user_id: int,
    track_id: int,
) -> JobTrack:
    """Resolve an evidence parent only inside the authenticated account."""
    track = (
        session.query(JobTrack)
        .filter(JobTrack.id == track_id, JobTrack.user_id == user_id)
        .first()
    )
    if track is None:
        raise EvidenceServiceError(
            "inaccessible_job_track",
            "Application is not available to this account.",
        )
    return track


def purge_expired_evidence_recovery_state(
    session: Session,
    *,
    now: datetime,
    limit: int = MAX_EVIDENCE_MAINTENANCE_BATCH,
) -> EvidenceMaintenanceResult:
    """Bound recovery retention without deleting evidence history markers.

    The caller owns the transaction and scheduling. JG-033 intentionally adds
    no background scheduler. Deleted evidence keeps its row and audit metadata
    after the private body is blanked. Short-lived create receipts are removed
    after the same thirty-day window.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_EVIDENCE_MAINTENANCE_BATCH:
        raise EvidenceServiceError(
            "invalid_maintenance_limit",
            f"limit must be between 1 and {MAX_EVIDENCE_MAINTENANCE_BATCH}.",
        )
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)

    evidence_cutoff = now - timedelta(days=EVIDENCE_SOFT_DELETE_RETENTION_DAYS)
    expired_evidence = (
        session.query(ApplicationEvidence)
        .filter(
            ApplicationEvidence.is_deleted.is_(True),
            ApplicationEvidence.body.is_not(None),
            ApplicationEvidence.updated_at <= evidence_cutoff,
        )
        .order_by(ApplicationEvidence.updated_at.asc(), ApplicationEvidence.id.asc())
        .limit(limit)
        .all()
    )
    for item in expired_evidence:
        deleted_at = item.updated_at
        item.body = None
        # Maintenance redaction must not rewrite the user's deletion timestamp.
        item.updated_at = deleted_at

    receipt_cutoff = now - timedelta(days=EVIDENCE_RECEIPT_RETENTION_DAYS)
    remaining = max(0, limit - len(expired_evidence))
    expired_receipts = (
        session.query(EvidenceCreateReceipt)
        .filter(EvidenceCreateReceipt.created_at <= receipt_cutoff)
        .order_by(EvidenceCreateReceipt.created_at.asc(), EvidenceCreateReceipt.id.asc())
        .limit(remaining)
        .all()
        if remaining
        else []
    )
    for receipt in expired_receipts:
        session.delete(receipt)

    return EvidenceMaintenanceResult(
        bodies_blanked=len(expired_evidence),
        receipts_deleted=len(expired_receipts),
    )
