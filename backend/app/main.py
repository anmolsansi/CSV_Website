from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import Base, engine
from .jobs import cleanup_clicked_rows
from .routers import auth_router, crm, rows, upload

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
