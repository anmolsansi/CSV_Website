# JobGrid — Project Structure

Full-stack job search tracking app (FastAPI + React/Vite + PostgreSQL).

```
CSV_Website/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── main.py            # App entry, routers, scheduler, test endpoints
│   │   ├── config.py          # Settings (env vars, TEST_AUTH flag)
│   │   ├── database.py        # SQLAlchemy engine + session
│   │   ├── models.py          # 11 ORM tables (CsvRow, JobTrack, SavedView, etc.)
│   │   ├── schemas.py         # Pydantic request/response models
│   │   ├── auth.py            # OAuth registration (Google, Microsoft, Apple)
│   │   ├── jobs.py            # Background cleanup tasks
│   │   ├── scoring.py         # Priority score, triage, skills extraction
│   │   ├── email_templates.py # HTML email templates (weekly digest)
│   │   ├── middleware.py       # Request metrics middleware
│   │   ├── sentry_init.py     # Sentry SDK initialization
│   │   └── routers/
│   │       ├── auth_router.py    # /auth/* — OAuth + dev login
│   │       ├── crm.py           # /crm/* — Applications, analytics, views, sessions, export
│   │       ├── email.py         # /crm/email/* — Weekly digest endpoint
│   │       ├── rows.py          # /rows/* — Row CRUD, filtering, preferences
│   │       └── upload.py        # /upload — CSV upload + dedup
│   ├── alembic/               # Database migrations
│   ├── tests/                 # pytest tests
│   │   ├── conftest.py        # Fixtures (client, db, auth_client)
│   │   ├── test_api.py        # Health, auth, upload, rows, analytics tests
│   │   ├── test_scoring.py    # Scoring/triage unit tests
│   │   └── test_email.py      # Email template tests
│   ├── requirements.txt       # Python dependencies
│   ├── .env                   # Environment config (not committed)
│   └── .env.prod.example      # Production env template
├── frontend/                  # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx            # Routes, auth flow, toast provider
│   │   ├── api/client.js      # Axios API client (all endpoints)
│   │   ├── styles.css         # Global CSS (dark mode, responsive, a11y)
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx       # Main CSV dashboard (upload, table, bulk actions)
│   │   │   ├── Applications.jsx    # Application tracking (kanban, stats)
│   │   │   ├── Pipeline.jsx        # Pipeline board (drag-drop status)
│   │   │   ├── Analytics.jsx       # Analytics dashboard (funnel, daily, ATS)
│   │   │   ├── Sessions.jsx        # Search session tracking
│   │   │   ├── SavedViews.jsx      # Saved view management
│   │   │   └── ...                 # Other pages (CompanyHistory, Duplicates, etc.)
│   │   └── components/
│   │       ├── DataTable.jsx       # Sortable/filterable table
│   │       ├── CsvUpload.jsx       # Drag-drop CSV upload
│   │       ├── Navigation.jsx      # Tab navigation
│   │       ├── DarkModeToggle.jsx  # Dark/light mode toggle
│   │       ├── SkipToContent.jsx   # Accessibility skip link
│   │       ├── RowDrawer.jsx       # Row detail side panel
│   │       ├── CommandPalette.jsx  # Cmd+K command palette
│   │       └── ActiveSessionBar.jsx # Active session indicator
│   ├── tests/                 # Playwright E2E tests
│   │   ├── auth.setup.ts      # Test auth setup (dev login)
│   │   ├── fixtures.ts        # Shared test fixtures
│   │   └── dashboard.spec.ts  # Dashboard tests
│   ├── playwright.config.ts   # Playwright config
│   ├── package.json           # Node dependencies
│   └── Dockerfile.prod        # Production Dockerfile
├── nginx/                     # Nginx reverse proxy
│   ├── nginx.conf
│   └── default.conf
├── scripts/
│   ├── deploy.sh              # Deployment script
│   ├── backup.sh              # Database backup
│   ├── restore.sh             # Database restore
│   └── load_test.py           # Load testing (10k+ rows)
├── docs/
│   └── BACKUP_STRATEGY.md     # Backup & recovery documentation
├── docker-compose.yml         # Dev compose (db + backend + frontend)
├── docker-compose.prod.yml    # Prod compose (nginx, healthchecks, limits)
├── .github/workflows/ci.yml   # CI: build, E2E, pytest, compile
├── IMPLEMENTATION_PLAN.md     # Feature tracking (F1–F40)
└── README.md
```

## Features (40/40 complete)

F1–F10: CSV upload, dedup, table, filtering, sorting, bulk actions, export, row detail, status tracking, click tracking
F11–F20: Applications (kanban), pipeline, analytics, funnel, saved views, sessions, audit log, goals, follow-ups, ApplyPilot
F21–F30: Intelligence (priority, summary, checklist), company history, duplicates, import external, column preferences, email digest, scoring
F31–F40: Dark mode, mobile responsive, accessibility (ARIA, skip links, keyboard nav), command palette, shareable views, monitoring (Sentry + metrics), backup/restore, load testing, CI pipeline

## Quick Start

```bash
# Dev (Docker)
docker compose up -d

# Dev (local)
cd backend && pip install -r requirements.txt
TEST_AUTH=true uvicorn app.main:app --reload
cd frontend && npm install && npm run dev

# Tests
cd backend && pytest tests/
cd frontend && npx playwright test

# Load test
python3 scripts/load_test.py --rows 10000
```

## Remaining Work

- None — all 40 PRD features complete, all 15 polish items done
