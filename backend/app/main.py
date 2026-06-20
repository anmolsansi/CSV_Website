import csv
import io
import os
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, get_db
from .jobs import cleanup_clicked_rows
from .models import User, CsvRow, CSV_COLUMNS
from .routers import auth_router, crm, email, rows, upload

if "sqlite" not in settings.DATABASE_URL:
    alembic_cfg = AlembicConfig(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    alembic_command.upgrade(alembic_cfg, "head")
else:
    from .database import Base, engine
    Base.metadata.create_all(bind=engine)

app = FastAPI(title="CSV URL Tracker")

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(upload.router)
app.include_router(rows.router)
app.include_router(crm.router)
app.include_router(email.router)

scheduler = BackgroundScheduler()


@app.on_event("startup")
def start_scheduler():
    scheduler.add_job(
        cleanup_clicked_rows,
        "interval",
        minutes=settings.CLEANUP_INTERVAL_MINUTES,
        id="cleanup_clicked_rows",
    )
    scheduler.start()


@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()


@app.get("/health")
def health():
    return {"status": "ok"}


if settings.TEST_AUTH:
    import uuid
    from fastapi.responses import JSONResponse

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
                db.add(row)
                created += 1
        db.commit()
        return {"user_id": user.id, "batch_id": batch_id, "rows_created": created}

    @app.post("/test/reset")
    def test_reset(db: Session = Depends(get_db)):
        """Reset all test data. Only available when TEST_AUTH=true."""
        user = db.query(User).filter_by(email="test@jobgrid.dev").first()
        if not user:
            return {"deleted": 0}
        from .models import JobTrack, SavedView, SearchSession, AuditEvent, ApplyPilotBatch, UserGoal, ColumnPreference, UrlHistory
        db.query(AuditEvent).filter_by(user_id=user.id).delete()
        db.query(ApplyPilotBatch).filter_by(user_id=user.id).delete()
        db.query(UserGoal).filter_by(user_id=user.id).delete()
        db.query(ColumnPreference).filter_by(user_id=user.id).delete()
        db.query(SavedView).filter_by(user_id=user.id).delete()
        db.query(SearchSession).filter_by(user_id=user.id).delete()
        db.query(JobTrack).filter_by(user_id=user.id).delete()
        db.query(CsvRow).filter_by(user_id=user.id).delete()
        db.query(UrlHistory).filter_by(user_id=user.id).delete()
        db.commit()
        return {"deleted": True}
