# JobGrid

JobGrid is a local-first job search command center. It turns job-list CSVs into
an authenticated dashboard where you can review URLs, mark visited jobs, send
rows into an Applications tracker, manage follow-ups, analyze progress, export
data, and create ApplyPilot batches.

## Stack

- Frontend: React, Vite, TanStack Table, Playwright.
- Backend: FastAPI, SQLAlchemy, Alembic, APScheduler.
- Database: PostgreSQL for Docker/prod, SQLite for local smoke and test runs.
- Auth: OAuth for real accounts, plus gated local dev login with `TEST_AUTH=true`.

## Quick Start

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up --build
```

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>

The dev Compose stack waits for Postgres to pass `pg_isready`, waits for backend
`/health`, then starts the frontend. The example env enables local test login so
you can use the app without OAuth credentials while developing.

## Local Run

Backend:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
TEST_AUTH=true DATABASE_URL=sqlite:///./dev.db uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the frontend and choose "Continue as local test user". For real OAuth,
configure provider credentials in `backend/.env` and disable `TEST_AUTH`.

## CSV Uploads

The only required CSV column is `url`. A URL-only CSV is valid and enough to
start using the dashboard.

Recommended optional columns unlock richer filtering, scoring, and tracking:

- `title`
- `company_guess`
- `ats_group`
- `search_bucket`
- `resume_match_score`
- `location_group`
- `sponsorship_status`
- `posted_age_days`
- `jd_text`

Download the sample template from the upload panel or open
`frontend/public/jobgrid_sample.csv`.

Upload behavior:

- URLs are deduplicated per user.
- Duplicate URLs in one upload are skipped and reported.
- Rows missing `url` are skipped and can be downloaded as an invalid-rows CSV.
- Missing optional columns are shown as context, not as upload errors.

## Core Workflow

1. Upload a CSV.
2. Review and filter jobs on the Dashboard.
3. Open a job URL to mark it visited.
4. Send selected rows to Applications.
5. Update status, applied date, follow-up date, and notes.
6. Use Analytics, Pipeline, Saved Views, Duplicates, Company History, and
   ApplyPilot pages for follow-through.

## Verification

Backend tests require Python 3.12:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/
```

Frontend build:

```bash
cd frontend
npm ci
npm run build
```

Minimum usable API smoke test:

```bash
# Start the backend with TEST_AUTH=true first.
python scripts/smoke_jobgrid.py --base-url http://localhost:8000
```

The smoke test logs in through `/auth/dev-login`, uploads a unique CSV, verifies
rows, records a click, sends rows to Applications, updates application status and
follow-up data, and checks exports. For non-test environments, pass `--cookie`
or `--no-dev-login`.

## Database Migrations

Alembic is the schema source of truth. The app runs `alembic upgrade head` on
startup for non-SQLite databases. Any model or `CSV_COLUMNS` change must include
a matching migration under `backend/alembic/versions`.

Schema parity is guarded by backend tests:

- every `CSV_COLUMNS` entry must exist on `CsvRow`;
- migration files must cover every CSV column;
- Alembic must have a single current head.

The older manual `backend/app/schema.py` patch path has been removed.

## OAuth Providers

Google, Microsoft, and Apple are supported through
`/auth/login/{provider}` and `/auth/callback/{provider}`.

Configure credentials in `backend/.env`:

- Google and Microsoft: set client id and secret, then add redirect URI
  `http://localhost:8000/auth/callback/<provider>`.
- Apple: set `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, and
  `APPLE_PRIVATE_KEY_PATH`.

To add another provider, register it in `backend/app/auth.py` and add its name to
`SUPPORTED_PROVIDERS`.
