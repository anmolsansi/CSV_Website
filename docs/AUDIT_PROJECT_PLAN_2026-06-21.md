# CSV_Website Audit Project Plan - 2026-06-21

## Current State

This project is a full-stack JobGrid/CSV URL tracker app:

- Frontend: React + Vite.
- Backend: FastAPI + SQLAlchemy + Alembic + APScheduler.
- Database: PostgreSQL in Docker, SQLite path used by backend tests.
- Main user flow: login, upload CSV, review rows, open job URLs, send rows to Applications, track status/follow-ups, export data.

The implementation is substantial, but the app is not currently in a usable state because the frontend production build fails and the backend has a startup route registration typo.

## Tasks Already Accomplished

- Core CSV upload model exists, including per-user rows, URL dedupe, upload result breakdown, invalid row reporting, and URL history.
- Authentication exists through OAuth providers, with a test/dev login endpoint gated by `TEST_AUTH=true`.
- Dashboard exists with CSV upload, server-backed pagination, filters, sort controls, column preferences, column presets, bulk actions, and export controls.
- Applications CRM exists with job status, follow-up dates, notes, pagination, filters, bulk update, export, and basic analytics integration.
- Supporting pages exist for Analytics, Pipeline, Sessions, Saved Views, ApplyPilot batches, Duplicates, Company History, and external import.
- Backend API has routers for auth, upload, rows, CRM, and email.
- Alembic migrations exist for the initial schema and expanded CSV columns.
- CI workflow exists for frontend build, backend compile, backend tests, and Playwright E2E.
- Backend unit/integration tests and frontend Playwright specs exist.
- Deployment support exists through Docker Compose, production Compose, Nginx config, backup/restore scripts, smoke script, and load test script.

## Confirmed Blockers To Fix First

1. Frontend build is broken.
   - `npm run build` fails in `frontend/src/pages/Applications.jsx`.
   - Cause: duplicate `clearFilters` declaration and leftover code referencing undefined `setPage`, `page`, `pageSize`, and `total`.

2. Backend startup has a hard runtime typo.
   - `backend/app/main.py` registers `/health` with `@api_app.get("/health")`, but the FastAPI instance is named `app`.
   - Expected fix: change to `@app.get("/health")` and add a startup/import test that catches this.

3. Local backend tests could not run in the current shell because Python dependencies are not installed.
   - `pytest tests` failed before app import with `ModuleNotFoundError: No module named 'apscheduler'`.
   - Expected fix: create a reproducible local test path, document it, and run the test suite after installing dependencies.

4. Local user login is not practical unless OAuth credentials are configured.
   - The backend has `/auth/dev-login` for `TEST_AUTH=true`, but the Login UI only exposes OAuth and disabled email/phone controls.
   - Expected fix: add a dev-only login button or document the exact local dev-login path.

5. Docker dev startup is fragile.
   - `docker-compose.yml` uses `depends_on` without a DB health condition.
   - The backend runs Alembic at import time, so it can fail if Postgres is not ready.

## Minimum Usable Milestone

These are the minimum tasks required before using the website for real work:

1. Fix `Applications.jsx` so `npm run build` passes.
2. Fix `/health` registration in `backend/app/main.py`.
3. Install backend dependencies and verify `pytest tests` runs.
4. Add or document local dev login with `TEST_AUTH=true`.
5. Run the app locally and verify this flow end to end:
   - Login.
   - Upload a CSV with at least a `url` column.
   - See rows in Dashboard.
   - Open one URL and see the row turn visited/green.
   - Send selected rows to Applications.
   - Update an application status and follow-up date.
6. Run the existing smoke script or update it until it validates the above flow.

## Additional Fixes Needed

- Align README and project docs. README still presents the simpler CSV URL tracker, while project docs describe JobGrid and 40 completed features.
- Make CI catch runtime import/startup issues, not only `compileall`.
- Replace or reconcile the old `backend/app/schema.py` manual schema patch with Alembic-only migration management.
- Add a health-gated dev Docker Compose startup path.
- Audit SQLite compatibility for tests, especially SQL expressions using PostgreSQL-specific regex functions/operators.
- Add tests around frontend Applications pagination/filter reset to prevent stale state regressions.
- Add a browser smoke test for Dashboard upload -> open URL -> Applications handoff.
- Improve upload guidance for partial CSVs. The backend accepts CSVs with only `url`, but the UI shows a long list of missing expected columns that may look like an error.
- Persist Applications column visibility preferences like Dashboard column preferences.
- Add clearer handling for popup blockers when opening many job URLs.

## Features Worth Adding Later

- User-facing onboarding checklist for first local run and first CSV upload.
- Sample CSV download/template.
- Import mapping UI for CSVs with non-standard column names.
- Saved view application from URL/query params.
- Real AI summary/resume tailoring integration, or rename current rule-based stubs so expectations are clear.
- Better duplicate review workflow with side-by-side comparison.
- Background job status page for cleanup, import, export, and email jobs.
- Production readiness dashboard: environment validation, DB migration status, Sentry status, backup status, and latest smoke result.
- Role/permission model if more than one user type will use this app.
- Better mobile table experience for dense CSV data.

## Verification Run During Audit

- `frontend: npm run build` failed due to `Applications.jsx`.
- `backend: pytest tests` failed because dependencies are missing in the active Python environment.
- `backend: python3 -m compileall app` passed after redirecting Python bytecode cache into the workspace.
