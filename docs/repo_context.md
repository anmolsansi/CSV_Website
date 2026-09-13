# Repo Context — JobGrid — 2026-09-10

React 18 / Vite 5 frontend (`frontend/src`), FastAPI 0.111 / SQLAlchemy 2.0
backend (`backend/app`), Alembic migrations, PostgreSQL deployment and SQLite
local tests. Dependencies are pinned in backend/requirements.txt and frontend/package-lock.json.

`routers/rows.py` owns CSV browsing, visits and deletion. `routers/crm.py`
owns durable `JobTrack` snapshots, applications and company history.
`models.py` defines per-user unique URLs for rows and tracks. Tracks have a
nullable CSV reference and retain company/title/URL independently.
`schemas.py` defines Pydantic request models. Routes use `get_current_user`
and explicitly restrict queries to `user.id`; errors follow FastAPI detail responses.
`frontend/src/api/client.js` uses Axios with session cookies. Dashboard.jsx
holds filters/sorting and server pagination; DataTable.jsx displays status.
CompanyHistory.jsx previously required an exact name and had no company directory.

Tests: pytest backend/tests with auth_client; Playwright frontend/tests uses
local dev login and a seeded backend. `npm run build` is the frontend check.
README.md is the developer guide. No SERVIQ build guide exists.

Landmines: CSV IDs and application IDs are distinct. Visit state is CsvRow.clicked,
not JobTrack existence. Never cascade CSV deletion into application history.
Existing bulk status code confuses those ID spaces; existing batch opener is page-local.
Git started clean on main at 9bfea7e. origin/main is the default branch.
GitHub issue discovery failed because api.github.com was unreachable. No issue,
Linear task, version or PR was supplied; work stays local without publishing.
