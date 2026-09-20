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

## R6 Runtime Verification

JobGrid supports two deliberately different database verification paths.

**SQLite is the local functional path.** It verifies numeric parsing and sorting,
per-connection `jobgrid_numeric(value)` registration, foreign-key enforcement,
and fresh-process application startup without claiming migration portability.

```bash
cd backend
DATABASE_URL=sqlite:////tmp/jobgrid-r6.sqlite3 \
TEST_AUTH=true \
SECRET_KEY=jg020-local-test-secret \
FRONTEND_URL=http://localhost:5173 \
python -m pytest tests/test_numeric_sort.py tests/test_database_dialects.py -q
```

A local run can skip PostgreSQL-only release checks. That skip is expected when no
PostgreSQL runtime is configured, but it is **not release evidence**.

**PostgreSQL 16 is the deployment and migration acceptance path.** Release
verification requires an ordinary PostgreSQL test database plus a different,
explicitly disposable `TEST_DATABASE_URL` for fresh Alembic/schema checks.

```bash
cd backend
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/jobgrid_test \
TEST_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/jobgrid_schema_test \
TEST_AUTH=true \
SECRET_KEY=jg020-postgres-test-secret \
FRONTEND_URL=http://localhost:5173 \
ENVIRONMENT=test \
python -m pytest \
  tests/test_numeric_sort.py \
  tests/test_database_dialects.py \
  tests/test_schema_parity.py -q
```

The PostgreSQL account used for schema acceptance must be allowed to create and
drop only the named disposable test database. Never point `TEST_DATABASE_URL`
at production, staging, or the regular test database.

With the authenticated backend running against PostgreSQL 16, the focused
browser acceptance is:

```bash
cd frontend
npm run test:e2e -- tests/numeric-sort.spec.ts --project=chromium
```

The browser fixture uses `2`, `10`, `85%`, `1,000`, `$99.50`, `-3`,
blank, and `invalid`. It asserts exact numeric order, nulls last, reload
stability, and a successful rows API response after reversing Resume Score sort.

Repository CI is the release integration gate because it runs the backend suite
on PostgreSQL 16, provides the separate schema-test database, builds the
frontend, and runs Playwright against a PostgreSQL-backed backend.

There is no R6 data rewrite to roll back. SQLite remains a functional runtime,
but historical Alembic revisions contain PostgreSQL-specific types such as
JSONB and are not redefined as SQLite migrations. If R6 runtime code must be
rolled back, roll back the application code while preserving stored data.
Never downgrade a production database merely to run or satisfy this test gate.

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

## Remembered applications and companies

Select jobs on the Dashboard and click **Mark applied** after you submit them.
JobGrid saves the company, job title, URL, status, and first application date in
your account's database. Opening a link alone does not mark it applied.
**Applications** shows saved jobs; **Company History** now lists all remembered
companies with saved-job and applied counts, search, and pagination. Select a
company to see its roles and dates. Unknown names appear as **Unknown company**.
Names are grouped ignoring outer whitespace and letter case, not by corporate
parent or aliases. Edit missing company details in Applications.

Application snapshots survive Dashboard CSV deletion and normal reloads. Keep
backups using the existing backup export and database backup procedure. This is
not automatic detection of submissions on external sites: mark them applied or
import your application history. Previously incorrect actions cannot reliably
be reconstructed; verify existing records in Applications.

## Portable backup and restore

The Dashboard keeps ordinary CSV/JSON data export separate from portable account backup.
Use **Export complete backup** to download the v2 backup that includes all nine durable
backup sections. To restore, choose **Restore backup file**. JobGrid uploads the file for
`verify_only` preflight first and shows section-level create/skip/conflict counts plus safe
warning codes. Nothing is written until you click **Restore backup**.

Restore uses `merge_missing`: missing records are created, but an existing destination
record wins on a natural-key conflict and is not overwritten by older backup values. A
failed restore keeps the selected browser file so you can retry. A successful restore
refreshes Dashboard data and can download a summary containing only backup metadata,
counts, and warning codes, not job descriptions, notes, or other private records.

V1 files remain accepted for compatibility, but they are incomplete. The UI explicitly
warns that omitted history, dates, relationships, and sections cannot be reconstructed or
described as restored. The selected file is held only in browser memory for the current
page session. Portable backup is separate from database disaster-recovery scripts under
`scripts/backup.sh` and `scripts/restore.sh`.

## Open top 5 unopened

The Dashboard button chooses the first five unvisited HTTP(S) links across the
**entire filtered result**, in the active sort order, regardless of the visible
page. It opens fewer when fewer remain. The next click advances past recorded
visits. Opened-only and unopened-only filters are mutually exclusive; if
opened-only is active, no unopened links match it.

Use JobGrid in **Google Chrome** and allow pop-ups for its site to open the links
in Chrome tabs. Websites cannot force a different browser or override whether
the browser displays new windows instead of tabs. JobGrid reserves blank tabs
within the click, fetches current matches, closes unused tabs, and records only
links it navigated. Blocked tabs are not marked visited. Errors saving visits
are shown; refresh and check the rows before retrying. Concurrent batches in
separate app tabs may overlap; there is no cross-window reservation system.
External-page loading and application submission cannot be verified by JobGrid.

Implementation: `frontend/src/api/openJobs.js` controls tab lifecycle;
`Dashboard.jsx` supplies the existing server filter/sort parameters. `rows.py`
uses `CsvRow.clicked` for visit filters and detaches retained application records
before CSV deletion. `crm.py` upserts application snapshots by account and URL.
No database migration is needed. Deploy backend changes before frontend changes;
rolling back code does not remove stored applications.

API additions (session authentication required):

- `POST /crm/from-rows/bulk`: `{row_ids: number[], status?: string}`. Known status
  values only. Returns `created`, `updated`, `skipped`, and `application_ids`.
  Unknown or foreign row IDs return 404 before any write. `applied` sets a missing
  application date; repeated actions preserve it.
- `GET /crm/companies?q=&page=1&page_size=50`: returns `companies` with `company`,
  `total`, `applied`, plus `total_count`, `page`, `page_size`, `has_next`.
- `GET /rows?unopened_only=true&openable_only=true&page_size=5`: existing filters
  and sort parameters apply. `openable_only` restricts URL schemes for batches.

Regression checks:

```bash
DATABASE_URL=sqlite:////tmp/jobgrid-check.db backend/.venv/bin/pytest backend/tests/
node --test frontend/unit/open-jobs.test.mjs
cd frontend
npm run build
# With the TEST_AUTH backend running locally:
npx playwright test application-memory.spec.ts
```
