from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import JobTrack, OAuthIdentity, ReminderDelivery, ReminderPreference, User
from ..reminder_schemas import (
    apply_delivery_transition,
    is_quiet_local_time,
    parse_local_time,
    reminder_occurrence_key,
    validate_timezone_name,
)
from .email_transport import SMTPNotConfigured, render_html_email, send_via_smtp


logger = logging.getLogger(__name__)

TERMINAL_REMINDER_TRACK_STATUSES = frozenset({"rejected", "offer", "not_applying"})
CLAIMABLE_STATUSES = frozenset({"pending", "failed"})
UNSENT_CANCELLABLE_STATUSES = frozenset({"pending", "failed"})
MAX_CLAIM_BATCH = 50
MAX_DELIVERY_ATTEMPTS = 3
RETRY_DELAYS_MINUTES = (1, 5, 30)


@dataclass(frozen=True)
class PlannedReminder:
    occurrence_key: str
    scheduled_at: datetime
    notification_local_date: date
    channel: str


@dataclass(frozen=True)
class DeliveryOutcome:
    kind: Literal["accepted", "rejected", "transient", "unknown"]
    error_code: str | None = None


class ReminderTransport(Protocol):
    def send(self, *, user: User, track: JobTrack, delivery: ReminderDelivery) -> DeliveryOutcome:
        ...


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _valid_wall_candidates(local_naive: datetime, zone: ZoneInfo) -> list[datetime]:
    candidates: list[datetime] = []
    for fold in (0, 1):
        candidate = local_naive.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
        if round_trip.replace(tzinfo=None) == local_naive:
            if not any(existing.utcoffset() == candidate.utcoffset() for existing in candidates):
                candidates.append(candidate)
    return candidates


def resolve_local_wall_time(
    local_date: date,
    hhmm: str,
    timezone_name: str,
) -> datetime:
    """Resolve one account-local wall time using the frozen F4 DST policy.

    For a spring-forward gap, use the first valid local instant after the gap.
    For a fall-back overlap, fold=0 is the earlier occurrence and is used once.
    """

    zone = validate_timezone_name(timezone_name)
    wall = datetime.combine(local_date, parse_local_time(hhmm))
    for minute_offset in range(0, 181):
        candidate_wall = wall + timedelta(minutes=minute_offset)
        candidates = _valid_wall_candidates(candidate_wall, zone)
        if candidates:
            return candidates[0].astimezone(timezone.utc)
    raise ValueError("No valid reminder wall-clock instant found within three hours.")


def _quiet_end_for(local_dt: datetime, preference: ReminderPreference) -> datetime:
    zone = local_dt.tzinfo
    if zone is None:
        raise ValueError("Local reminder time must be timezone-aware.")
    start = parse_local_time(preference.quiet_start)
    end = parse_local_time(preference.quiet_end)
    if start == end:
        return local_dt
    wall = local_dt.timetz().replace(tzinfo=None)
    if not is_quiet_local_time(
        wall,
        quiet_start=preference.quiet_start,
        quiet_end=preference.quiet_end,
    ):
        return local_dt

    target_date = local_dt.date()
    if start > end and wall >= start:
        target_date += timedelta(days=1)
    return resolve_local_wall_time(
        target_date,
        preference.quiet_end,
        getattr(zone, "key", "UTC"),
    ).astimezone(zone)


def plan_due_occurrence(
    *,
    track: JobTrack,
    preference: ReminderPreference,
    timezone_name: str,
    now_utc: datetime,
) -> PlannedReminder | None:
    """Pure planning decision for one follow-up source."""

    del now_utc  # injected clock is part of the explicit contract and future policy hook.
    if not preference.enabled or track.follow_up_at is None:
        return None
    if track.status in TERMINAL_REMINDER_TRACK_STATUSES:
        return None

    zone = validate_timezone_name(timezone_name)
    due_utc = aware_utc(track.follow_up_at)
    local_date = due_utc.astimezone(zone).date()
    scheduled_utc = resolve_local_wall_time(
        local_date,
        preference.local_time,
        timezone_name,
    )
    scheduled_local = scheduled_utc.astimezone(zone)
    scheduled_local = _quiet_end_for(scheduled_local, preference)
    scheduled_utc = scheduled_local.astimezone(timezone.utc)

    return PlannedReminder(
        occurrence_key=reminder_occurrence_key(
            track_id=track.id,
            due_at=due_utc,
            notification_local_date=local_date,
        ),
        scheduled_at=scheduled_utc,
        notification_local_date=local_date,
        channel=preference.channel,
    )


def _cancel_stale_unsent(
    db: Session,
    *,
    user_id: int,
    track_id: int,
    keep_occurrence_key: str | None,
    keep_channel: str | None,
) -> int:
    query = db.query(ReminderDelivery).filter(
        ReminderDelivery.user_id == user_id,
        ReminderDelivery.track_id == track_id,
        ReminderDelivery.status.in_(tuple(UNSENT_CANCELLABLE_STATUSES)),
    )
    rows = query.all()
    cancelled = 0
    for row in rows:
        if (
            keep_occurrence_key is not None
            and row.occurrence_key == keep_occurrence_key
            and row.channel == keep_channel
        ):
            continue
        apply_delivery_transition(row, "cancelled")
        row.lease_until = None
        row.next_attempt_at = None
        row.last_error_code = "source_changed"
        cancelled += 1
    return cancelled


def sync_track_reminder(
    db: Session,
    *,
    user_id: int,
    track_id: int,
    now_utc: datetime | None = None,
) -> ReminderDelivery | None:
    track = (
        db.query(JobTrack)
        .filter(JobTrack.id == track_id, JobTrack.user_id == user_id)
        .first()
    )
    if track is None:
        return None
    preference = (
        db.query(ReminderPreference)
        .filter(ReminderPreference.user_id == user_id)
        .first()
    )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or preference is None:
        _cancel_stale_unsent(
            db,
            user_id=user_id,
            track_id=track_id,
            keep_occurrence_key=None,
            keep_channel=None,
        )
        return None

    planned = plan_due_occurrence(
        track=track,
        preference=preference,
        timezone_name=user.timezone,
        now_utc=aware_utc(now_utc or utc_now()),
    )
    _cancel_stale_unsent(
        db,
        user_id=user_id,
        track_id=track_id,
        keep_occurrence_key=planned.occurrence_key if planned else None,
        keep_channel=planned.channel if planned else None,
    )
    if planned is None:
        return None

    existing = (
        db.query(ReminderDelivery)
        .filter(
            ReminderDelivery.user_id == user_id,
            ReminderDelivery.occurrence_key == planned.occurrence_key,
            ReminderDelivery.channel == planned.channel,
        )
        .first()
    )
    if existing is not None:
        if existing.status in {"pending", "failed"}:
            existing.scheduled_at = planned.scheduled_at
            existing.next_attempt_at = None
        return existing

    delivery = ReminderDelivery(
        user_id=user_id,
        track_id=track_id,
        occurrence_key=planned.occurrence_key,
        channel=planned.channel,
        status="pending",
        scheduled_at=planned.scheduled_at,
        attempt_count=0,
        version=1,
    )
    db.add(delivery)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent planner may win the deterministic unique key. The caller
        # transaction must remain usable, so resolve through a savepoint.
        db.rollback()
        return (
            db.query(ReminderDelivery)
            .filter(
                ReminderDelivery.user_id == user_id,
                ReminderDelivery.occurrence_key == planned.occurrence_key,
                ReminderDelivery.channel == planned.channel,
            )
            .first()
        )
    return delivery


def sync_user_reminders(
    db: Session,
    *,
    user_id: int,
    now_utc: datetime | None = None,
) -> int:
    tracks = (
        db.query(JobTrack)
        .filter(JobTrack.user_id == user_id)
        .filter(JobTrack.follow_up_at.isnot(None))
        .all()
    )
    count = 0
    for track in tracks:
        if sync_track_reminder(
            db,
            user_id=user_id,
            track_id=track.id,
            now_utc=now_utc,
        ) is not None:
            count += 1
    return count


def sync_all_enabled_reminders(
    db: Session,
    *,
    now_utc: datetime | None = None,
) -> int:
    user_ids = [
        row.user_id
        for row in db.query(ReminderPreference)
        .filter(ReminderPreference.enabled.is_(True))
        .all()
    ]
    return sum(
        sync_user_reminders(db, user_id=user_id, now_utc=now_utc)
        for user_id in user_ids
    )


def recover_expired_claims(db: Session, *, now_utc: datetime) -> int:
    now_utc = aware_utc(now_utc)
    rows = (
        db.query(ReminderDelivery)
        .filter(
            ReminderDelivery.status == "sending",
            ReminderDelivery.lease_until.isnot(None),
            ReminderDelivery.lease_until <= now_utc,
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        apply_delivery_transition(row, "unknown")
        row.lease_until = None
        row.next_attempt_at = None
        row.last_error_code = "lease_expired_unknown"
    return len(rows)


def claim_due_deliveries(
    db: Session,
    *,
    now_utc: datetime,
    lease_seconds: int,
    limit: int = MAX_CLAIM_BATCH,
) -> list[int]:
    if limit < 1 or limit > MAX_CLAIM_BATCH:
        raise ValueError("Reminder claim limit must be between 1 and 50.")
    now_utc = aware_utc(now_utc)

    query = (
        db.query(ReminderDelivery)
        .join(
            ReminderPreference,
            ReminderPreference.user_id == ReminderDelivery.user_id,
        )
        .filter(
            ReminderPreference.enabled.is_(True),
            ReminderDelivery.status.in_(tuple(CLAIMABLE_STATUSES)),
            ReminderDelivery.scheduled_at <= now_utc,
            or_(
                ReminderDelivery.next_attempt_at.is_(None),
                ReminderDelivery.next_attempt_at <= now_utc,
            ),
            or_(
                ReminderDelivery.lease_until.is_(None),
                ReminderDelivery.lease_until <= now_utc,
            ),
        )
        .order_by(ReminderDelivery.scheduled_at.asc(), ReminderDelivery.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    rows = query.all()
    lease_until = now_utc + timedelta(seconds=max(30, lease_seconds))
    for row in rows:
        apply_delivery_transition(row, "sending")
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.lease_until = lease_until
        row.next_attempt_at = None
        row.last_error_code = None
    db.flush()
    return [row.id for row in rows]


def email_delivery_availability(db: Session, *, user: User) -> tuple[bool, str | None]:
    if not settings.REMINDER_EMAIL_DELIVERY_ENABLED:
        return False, "email_delivery_disabled"
    if not settings.SMTP_HOST or not (settings.EMAIL_FROM or settings.SMTP_USER):
        return False, "smtp_not_configured"
    linked_identity = (
        db.query(OAuthIdentity)
        .filter(OAuthIdentity.user_id == user.id)
        .first()
    )
    if linked_identity is None:
        return False, "verified_destination_unavailable"
    return True, None


class SmtpReminderTransport:
    def send(
        self,
        *,
        user: User,
        track: JobTrack,
        delivery: ReminderDelivery,
    ) -> DeliveryOutcome:
        subject = f"JobGrid reminder: {track.company or 'follow up'}"
        html = (
            "<p>Your JobGrid follow-up is due.</p>"
            f"<p><strong>{track.company or 'Company'}</strong>"
            f" — {track.title or 'Role'}</p>"
            "<p>Open JobGrid to review the application before taking action.</p>"
        )
        message = render_html_email(user.email, subject, html)
        try:
            send_via_smtp(message)
            return DeliveryOutcome("accepted")
        except SMTPNotConfigured:
            return DeliveryOutcome("rejected", "smtp_not_configured")
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused):
            return DeliveryOutcome("rejected", "smtp_rejected")
        except smtplib.SMTPResponseException as exc:
            if 400 <= int(exc.smtp_code) < 500:
                return DeliveryOutcome("transient", "smtp_transient")
            return DeliveryOutcome("rejected", "smtp_rejected")
        except (smtplib.SMTPServerDisconnected, TimeoutError, OSError):
            # Once SMTP I/O begins, a disconnect can be ambiguous. Do not retry
            # automatically because provider acceptance may already have happened.
            return DeliveryOutcome("unknown", "smtp_ambiguous")
        except Exception:
            logger.exception(
                "reminder_transport outcome=unknown delivery_id=%s",
                delivery.id,
            )
            return DeliveryOutcome("unknown", "smtp_unknown")


def _claimed_delivery_eligible(
    db: Session,
    *,
    delivery: ReminderDelivery,
    now_utc: datetime,
) -> tuple[bool, User | None, JobTrack | None]:
    user = (
        db.query(User)
        .filter(User.id == delivery.user_id)
        .first()
    )
    preference = (
        db.query(ReminderPreference)
        .filter(ReminderPreference.user_id == delivery.user_id)
        .first()
    )
    track = (
        db.query(JobTrack)
        .filter(
            JobTrack.id == delivery.track_id,
            JobTrack.user_id == delivery.user_id,
        )
        .first()
        if delivery.track_id is not None
        else None
    )
    if user is None or preference is None or track is None or not preference.enabled:
        return False, user, track
    planned = plan_due_occurrence(
        track=track,
        preference=preference,
        timezone_name=user.timezone,
        now_utc=now_utc,
    )
    return (
        planned is not None
        and planned.occurrence_key == delivery.occurrence_key
        and planned.channel == delivery.channel,
        user,
        track,
    )


def _finish_claim(
    db: Session,
    *,
    delivery: ReminderDelivery,
    outcome: DeliveryOutcome,
    now_utc: datetime,
) -> str:
    delivery.lease_until = None
    if outcome.kind == "accepted":
        apply_delivery_transition(delivery, "sent", sent_at=now_utc)
        delivery.last_error_code = None
        return "sent"
    if outcome.kind == "unknown":
        apply_delivery_transition(delivery, "unknown")
        delivery.next_attempt_at = None
        delivery.last_error_code = outcome.error_code or "delivery_unknown"
        return "unknown"

    apply_delivery_transition(delivery, "failed")
    delivery.last_error_code = outcome.error_code or "delivery_failed"
    if outcome.kind == "transient" and delivery.attempt_count < MAX_DELIVERY_ATTEMPTS:
        delay_index = min(max(delivery.attempt_count - 1, 0), len(RETRY_DELAYS_MINUTES) - 1)
        delivery.next_attempt_at = now_utc + timedelta(
            minutes=RETRY_DELAYS_MINUTES[delay_index]
        )
    else:
        delivery.next_attempt_at = None
    return "failed"


def process_reminder_batch(
    db: Session,
    *,
    now_utc: datetime | None = None,
    transport: ReminderTransport | None = None,
    limit: int = MAX_CLAIM_BATCH,
    lease_seconds: int | None = None,
) -> dict[str, int]:
    now_utc = aware_utc(now_utc or utc_now())
    counters = {
        "planned": 0,
        "recovered_unknown": 0,
        "claimed": 0,
        "processed": 0,
        "sent": 0,
        "failed": 0,
        "unknown": 0,
        "cancelled": 0,
        "email_unavailable": 0,
    }

    counters["planned"] = sync_all_enabled_reminders(db, now_utc=now_utc)
    counters["recovered_unknown"] = recover_expired_claims(db, now_utc=now_utc)
    db.commit()

    claimed_ids = claim_due_deliveries(
        db,
        now_utc=now_utc,
        lease_seconds=lease_seconds or settings.REMINDER_LEASE_SECONDS,
        limit=limit,
    )
    counters["claimed"] = len(claimed_ids)
    db.commit()

    sender = transport or SmtpReminderTransport()
    for delivery_id in claimed_ids:
        delivery = db.query(ReminderDelivery).filter(ReminderDelivery.id == delivery_id).first()
        if delivery is None or delivery.status != "sending":
            continue
        eligible, user, track = _claimed_delivery_eligible(
            db,
            delivery=delivery,
            now_utc=now_utc,
        )
        if not eligible or user is None or track is None:
            apply_delivery_transition(delivery, "cancelled")
            delivery.lease_until = None
            delivery.next_attempt_at = None
            delivery.last_error_code = "ineligible_after_claim"
            counters["cancelled"] += 1
            counters["processed"] += 1
            db.commit()
            continue

        if delivery.channel == "in_app":
            outcome = DeliveryOutcome("accepted")
        else:
            available, reason = email_delivery_availability(db, user=user)
            if not available:
                outcome = DeliveryOutcome("rejected", reason)
                counters["email_unavailable"] += 1
            else:
                outcome = sender.send(user=user, track=track, delivery=delivery)

        terminal = _finish_claim(
            db,
            delivery=delivery,
            outcome=outcome,
            now_utc=now_utc,
        )
        counters[terminal] += 1
        counters["processed"] += 1
        db.commit()

    logger.info(
        "reminder_worker outcome=complete processed=%s sent=%s failed=%s unknown=%s "
        "cancelled=%s claimed=%s recovered_unknown=%s",
        counters["processed"],
        counters["sent"],
        counters["failed"],
        counters["unknown"],
        counters["cancelled"],
        counters["claimed"],
        counters["recovered_unknown"],
    )
    return counters


def run_reminder_worker_once() -> dict[str, int]:
    db = SessionLocal()
    try:
        return process_reminder_batch(db)
    except Exception:
        db.rollback()
        logger.exception("reminder_worker outcome=failed")
        raise
    finally:
        db.close()
