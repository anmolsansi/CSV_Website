# CSV URL Tracker

<!-- scaffold -->
A per-user web app where authenticated users upload CSVs that render as a table.
The `url` column appears as a button: **blue** when unvisited, **green** after a
click (which opens the URL in a new tab). Rows are auto-deleted **2 days** after
the button turns green. Multiple uploads are appended and deduplicated per user
by `url`. Users can show/hide columns, and the preference is saved.

## Stack

- **Frontend:** React (Vite) + TanStack Table
- **Backend:** FastAPI + SQLAlchemy + APScheduler (cleanup job)
- **Database:** PostgreSQL
- **Auth:** OAuth 2.0 via Authlib (Google, Microsoft, Apple). OAuth-only (no
  passwords). Accounts are linked by email, so signing in with any provider
  that shares your email resolves to the same account.

## Setup

### 1. Configure environment

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Create Google OAuth credentials at
<https://console.cloud.google.com/apis/credentials> with the redirect URI:

```
http://localhost:8000/auth/callback/google
```

Then set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `backend/.env`, and set
a long random `SECRET_KEY`.

### 2. Run with Docker

```bash
docker compose up --build
```

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>

### 3. Run locally (without Docker)

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## How it works

- **Dedup:** a unique constraint on `(user_id, url)` plus
  `ON CONFLICT DO NOTHING` means re-uploading the same URL keeps only one row
  (and preserves its click state/timer).
- **Click tracking:** clicking the button calls `POST /rows/{id}/click`, which
  sets `clicked=true` and `clicked_at=now()` server-side, so the green state
  survives refresh/logout.
- **Auto-delete:** an APScheduler job (default hourly) deletes rows where
  `clicked_at < now() - 2 days`. Unvisited (blue) rows are never auto-deleted.
- **Column visibility:** stored per user in `column_preferences.hidden_columns`.

## OAuth providers

Google, Microsoft, and Apple are supported via generic
`/auth/login/{provider}` and `/auth/callback/{provider}` routes.

Configure credentials in `backend/.env`:

- **Google / Microsoft:** standard client id + secret. Add the redirect URI
  `http://localhost:8000/auth/callback/<provider>`.
- **Apple:** requires an Apple Developer account. Create a Services ID
  (`APPLE_CLIENT_ID`), note your `APPLE_TEAM_ID` and `APPLE_KEY_ID`, and download
  the `.p8` private key. Mount it into the backend and point
  `APPLE_PRIVATE_KEY_PATH` at it. The client secret is generated automatically
  as a signed ES256 JWT at request time.

To add another provider, register it in `backend/app/auth.py` and add its name
to `SUPPORTED_PROVIDERS`.

## Add new CSV columns

The expected columns are defined in `CSV_COLUMNS` in `backend/app/models.py`.
Update that list and add matching `Column(Text)` fields, then create a migration.
