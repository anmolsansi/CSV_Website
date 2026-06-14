from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .jobs import cleanup_clicked_rows
from .routers import auth_router, crm, rows, upload
from .schema import ensure_schema

ensure_schema()

api_app = FastAPI(title="CSV URL Tracker")

api_app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

api_app.include_router(auth_router.router)
api_app.include_router(upload.router)
api_app.include_router(rows.router)
api_app.include_router(crm.router)

scheduler = BackgroundScheduler()


@api_app.on_event("startup")
def start_scheduler():
    scheduler.add_job(
        cleanup_clicked_rows,
        "interval",
        minutes=settings.CLEANUP_INTERVAL_MINUTES,
        id="cleanup_clicked_rows",
    )
    scheduler.start()


@api_app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()


@api_app.get("/health")
def health():
    return {"status": "ok"}


app = CORSMiddleware(
    api_app,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
