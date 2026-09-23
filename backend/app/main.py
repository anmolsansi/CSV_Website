import csv
import io
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, UploadFile, File, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from .backup_schemas import MAX_BACKUP_JSON_BYTES
from .config import cookie_security_options, settings
from .database import Base, engine, get_db
from .jobs import cleanup_clicked_rows
from .services.reminders import run_reminder_worker_once
from .services.today_f8 import build_today_queue_with_interviews, snooze_action_with_interviews
from .services.import_backups import (
    export_backup_v2_with_import_mappings,
    restore_backup_payload_with_import_mappings,
)
from .middleware import MetricsMiddleware
from .models import User, CsvRow, CSV_COLUMNS
from . import contact_models, import_models
from .routers import auth_router, availability, backup, bulk_actions, capture, company_aliases, contacts, crm, documents, email, evidence, imports, reminders, rows, today, upload
from .sentry_init import init_sentry

# F8 extends the established Today route without replacing its request contract.
today.build_today_queue = build_today_queue_with_interviews
today.snooze_action = snooze_action_with_interviews

# F9 extends the already-versioned portable v2 backup without changing the
# legacy v1 route or transient-preview storage contract.
backup.export_backup_v2_with_contacts = export_backup_v2_with_import_mappings
backup.restore_backup_payload_with_contacts = restore_backup_payload_with_import_mappings

if "sqlite" not in settings.DATABASE_URL:
    alembic_cfg = AlembicConfig(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    alembic_command.upgrade(alembic_cfg, "head")
else:
    Base.metadata.create_all(bind=engine)

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
reminder_scheduler = BackgroundScheduler()
_maintenance_registration_lock = threading.Lock()
_maintenance_registered = False
_reminder_registration_lock = threading.Lock()
_reminder_registered = False


def _start_maintenance_scheduler() -> bool:
    """Register maintenance at most once in this Python process."""
    global _maintenance_registered
    with _maintenance_registration_lock:
        if _maintenance_registered:
            logger.info("maintenance_scheduler outcome=skipped reason=already_registered")
            return False
        scheduler.add_job(
            cleanup_clicked_rows,
            "interval",
            minutes=settings.CLEANUP_INTERVAL_MINUTES,
            id="cleanup_clicked_rows",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        scheduler.start()
        _maintenance_registered = True
        logger.info("maintenance_scheduler outcome=started")
        return True


def _stop_maintenance_scheduler() -> None:
    global _maintenance_registered
    with _maintenance_registration_lock:
        if not _maintenance_registered:
            return
        scheduler.shutdown(wait=False)
        _maintenance_registered = False
        logger.info("maintenance_scheduler outcome=stopped")


def _start_reminder_scheduler() -> bool:
    """Start one process-local reminder worker when explicitly enabled."""
    global _reminder_registered
    with _reminder_registration_lock:
        if _reminder_registered:
            logger.info("reminder_scheduler outcome=skipped reason=already_registered")
            return False
        reminder_scheduler.add_job(
            run_reminder_worker_once,
            "interval",
            seconds=settings.REMINDER_WORKER_INTERVAL_SECONDS,
            id="reminder_worker",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        reminder_scheduler.start()
        _reminder_registered = True
        logger.info("reminder_scheduler outcome=started")
        return True


def _stop_reminder_scheduler() -> None:
    global _reminder_registered
    with _reminder_registration_lock:
        if not _reminder_registered:
            return
        reminder_scheduler.shutdown(wait=False)
        _reminder_registered = False
        logger.info("reminder_scheduler outcome=stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    maintenance_started = False
    reminder_started = False
    if settings.RUN_MAINTENANCE_JOBS:
        maintenance_started = _start_maintenance_scheduler()
    if settings.RUN_REMINDER_WORKER:
        reminder_started = _start_reminder_scheduler()
    try:
        yield
    finally:
        if reminder_started:
            _stop_reminder_scheduler()
        if maintenance_started:
            _stop_maintenance_scheduler()


app = FastAPI(title="CSV URL Tracker", lifespan=lifespan)

BACKUP_IMPORT_REQUEST_MAX_BYTES = MAX_BACKUP_JSON_BYTES + (1024 * 1024)


@app.middleware("http")
async def reject_oversized_backup_import_request(request: Request, call_next):
    if request.url.path == "/crm/backup/import" and request.method.upper() == "POST":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                request_bytes = int(content_length)
            except ValueError:
                request_bytes = None
            if request_bytes is not None and request_bytes > BACKUP_IMPORT_REQUEST_MAX_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": {
                            "code": "backup_too_large",
                            "message": "Backup request exceeds the application body limit.",
                        }
                    },
                )
    return await call_next(request)


_session_cookie_options = cookie_security_options(settings.ENVIRONMENT)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    https_only=_session_cookie_options["secure"],
    same_site=_session_cookie_options["samesite"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MetricsMiddleware)

if settings.SENTRY_DSN:
    init_sentry(settings.SENTRY_DSN, settings.ENVIRONMENT)

crm.router.routes[:] = [
    route
    for route in crm.router.routes
    if not (
        getattr(route, "path", None) in {"/crm/backup/export", "/crm/backup/import"}
        and (
            "GET" in (getattr(route, "methods", set()) or set())
            or "POST" in (getattr(route, "methods", set()) or set())
        )
    )
]

app.include_router(auth_router.router)
app.include_router(upload.router)
app.include_router(availability.router)
app.include_router(rows.router)
app.include_router(backup.router)
app.include_router(imports.router)
app.include_router(capture.router)
app.include_router(company_aliases.router)
app.include_router(evidence.router)
app.include_router(documents.router)
app.include_router(contacts.router)
app.include_router(bulk_actions.router)
app.include_router(crm.router)
app.include_router(today.router)
app.include_router(reminders.router)
app.include_router(email.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if settings.TEST_AUTH:
    import uuid

    @app.post("/test/seed")
    def test_seed(db: Session = Depends(get_db)):
        """Seed test data for E2E tests. Only available when TEST_AUTH=true."""
        user = db.query(User).filter_by(email="test@jobgrid.dev").first()
        if not user:
            user = User(email="test@jobgrid.dev")
            db.add(user)
            db.commit()
            db.refresh(user)

        batch_id = str(uuid.uuid4())
        test_rows = [
            {"company_guess": "Acme Corp", "title": "Senior Engineer", "url": f"https://acme.com/jobs/{i}", "ats_group": "greenhouse", "search_bucket": "ai", "resume_match_score": "85", "location_group": "remote", "sponsorship_status": "positive", "posted_age_days": "5"}
            for i in range(20)
        ]
        created = 0
        for row_data in test_rows:
            existing = db.query(CsvRow).filter_by(user_id=user.id, url=row_data["url"]).first()
            if not existing:
                row = CsvRow(user_id=user.id, upload_batch_id=batch_id, **row_data)
                from .services.job_identity import apply_persisted_job_identity
                apply_persisted_job_identity(row)
                db.add(row)
                created += 1
        db.commit()
        return {"user_id": user.id, "batch_id": batch_id, "rows_created": created}

    @app.post("/test/reset")
    def test_reset(db: Session = Depends(get_db)):
        """Reset all test data. Only available when TEST_AUTH=true."""
        user = db.query(User).filter_by(email="test@jobgrid.dev").first()
        from .models import ApplicationDocument, ApplicationEvidence, CaptureRequest, CompanyAlias, DocumentCreateReceipt, DocumentVersion, EvidenceCreateReceipt, JobAvailability, JobCheckRequest, JobLifecycleEvent, JobTrack, RequestWindowCounter, SavedView, SearchSession, AuditEvent, ApplyPilotBatch, UserGoal, ColumnPreference, UrlHistory, MaintenanceStatus, WorkItem, WorkItemOverride, ReminderDelivery, ReminderPreference
        from .contact_models import ApplicationContact, Contact, Interview, MutationReceipt
        from .import_models import ImportMapping, ImportPreview
        from .undo_models import BulkAction, BulkActionEffect
        db.query(MaintenanceStatus).delete()
        if not user:
            db.commit()
            return {"deleted": 0}
        user.retention_days = None
        db.query(BulkActionEffect).filter(BulkActionEffect.action_id.in_(db.query(BulkAction.id).filter_by(user_id=user.id))).delete(synchronize_session=False)
        db.query(BulkAction).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.query(ImportPreview).filter_by(user_id=user.id).delete()
        db.query(ImportMapping).filter_by(user_id=user.id).delete()
        db.query(RequestWindowCounter).filter_by(user_id=user.id).delete()
        db.query(CaptureRequest).filter_by(user_id=user.id).delete()
        db.query(JobCheckRequest).filter_by(user_id=user.id).delete()
        db.query(JobAvailability).filter_by(user_id=user.id).delete()
        db.query(ReminderDelivery).filter_by(user_id=user.id).delete()
        db.query(ReminderPreference).filter_by(user_id=user.id).delete()
        db.query(JobLifecycleEvent).filter_by(user_id=user.id).delete()
        db.query(EvidenceCreateReceipt).filter_by(user_id=user.id).delete()
        db.query(ApplicationDocument).filter_by(user_id=user.id).delete()
        db.query(DocumentCreateReceipt).filter_by(user_id=user.id).delete()
        db.query(ApplicationEvidence).filter_by(user_id=user.id).delete()
        db.query(DocumentVersion).filter_by(user_id=user.id).delete()
        db.query(MutationReceipt).filter_by(user_id=user.id).delete()
        db.query(Interview).filter_by(user_id=user.id).delete()
        db.query(ApplicationContact).filter_by(user_id=user.id).delete()
        db.query(Contact).filter_by(user_id=user.id).delete()
        db.query(AuditEvent).filter_by(user_id=user.id).delete()
        db.query(ApplyPilotBatch).filter_by(user_id=user.id).delete()
        db.query(UserGoal).filter_by(user_id=user.id).delete()
        db.query(ColumnPreference).filter_by(user_id=user.id).delete()
        db.query(WorkItemOverride).filter_by(user_id=user.id).delete()
        db.query(WorkItem).filter_by(user_id=user.id).delete()
        db.query(SavedView).filter_by(user_id=user.id).delete()
        db.query(SearchSession).filter_by(user_id=user.id).delete()
        db.query(JobTrack).filter_by(user_id=user.id).delete()
        db.query(CompanyAlias).filter_by(user_id=user.id).delete()
        db.query(CsvRow).filter_by(user_id=user.id).delete()
        db.query(UrlHistory).filter_by(user_id=user.id).delete()
        db.commit()
        return {"deleted": True}
