# JobGrid Implementation Plan

## Overview

23 core features across 4 priority tiers, plus 17 extended features (F24–F40). Each feature includes:
- What changes in the backend (models, routers, schemas)
- What changes in the frontend (pages, components, API client)
- File paths and specific modifications
- Dependencies on other features

---

## Completion Status (as of session 2026-06-13)

### Completed: Features 1–23 + F24–F40 (all 40 features)
**Frontend build: ✅ passing**

### What's done:
- **F1–F3**: Alembic migrations (11 tables), smoke test script, GitHub Actions CI
- **F4–F5**: Pagination (page/page_size/total_count/has_next), server-side filtering
- **F6–F7**: Saved Views with apply/edit/duplicate/pin, 9 default views
- **F8–F10**: Active session bar, session activity counts from audit events, audit event log
- **F11–F14**: Row drawer with intelligence, status badges in DataTable, bulk status actions, bulk follow-up tools
- **F15–F17**: ApplyPilot batches (CRUD + download), batch history model, result import
- **F18**: ApplyPilot readiness score (8-check validation)
- **F19–F23**: Funnel analytics, ATS performance, bucket performance, daily goals with progress bars, weekly report
- **F24–F27**: Priority score (rule-based formula), triage (apply_now/maybe/skip/needs_review), AI summary stub, resume tailoring checklist stub
- **F28–F30**: Duplicate review page, URL normalization (canonical_company_job_key), company history page
- **F31–F33**: Backup export/import, export templates, external import (JSON)
- **F34**: Command palette (Cmd+K) with navigation + backup actions
- **F35**: Enhanced keyboard shortcuts (O/A/S/X/F/N/R)
- **F36**: Sticky toolbar improvements (all bulk actions)
- **F37**: Empty states with contextual CTAs across all pages
- **F38**: Density mode toggle (comfortable/compact/ultra-dense) with localStorage
- **F39**: Column pinning (sticky left) with localStorage
- **F40**: Priority score + triage column in DataTable (backend returns per-row)

---

## Phase 1: P0 — Stabilize (Features 1–5) ✅ DONE

### Feature 1: Database Migrations (Alembic)

**Why:** `create_all()` cannot add columns to existing tables. Any schema change risks data loss in production.

**Current state:** `alembic==1.13.1` is in `requirements.txt` but no `alembic.ini` or `migrations/` directory exists.

**Backend changes:**

1. **Initialize Alembic** — run `alembic init backend/alembic` from project root
2. **Edit `backend/alembic.ini`** — set `sqlalchemy.url` to read from env:
   ```ini
   sqlalchemy.url = %(DATABASE_URL)s
   ```
3. **Edit `backend/alembic/env.py`** — import `Base` from `app.database` and `settings` from `app.config`, set `target_metadata = Base.metadata`, read URL from `settings.DATABASE_URL`
4. **Generate initial migration** — `alembic revision --autogenerate -m "initial schema"`
5. **Edit `backend/app/main.py`** — replace `Base.metadata.create_all(bind=engine)` with:
   ```python
   from alembic.config import Config
   from alembic import command
   alembic_cfg = Config("alembic.ini")
   command.upgrade(alembic_cfg, "head")
   ```
6. **Future migrations** — any model change in `models.py` gets a migration via `alembic revision --autogenerate -m "description"`

**Tables covered:** `users`, `oauth_identities`, `url_history`, `csv_rows`, `job_tracks`, `saved_views`, `search_sessions`, `column_preferences`

**Files modified:**
- `backend/alembic.ini` (new)
- `backend/alembic/env.py` (new, from template)
- `backend/alembic/versions/` (new, auto-generated)
- `backend/app/main.py:11` (replace `create_all`)

---

### Feature 2: Smoke-Test Script

**Why:** Manual browser testing misses broken endpoints. Need automated validation.

**New file:** `scripts/smoke_jobgrid.py`

**Test sequence:**
```python
import requests, sys

BASE = "http://localhost:8000"
session = requests.Session()

# 1. Health check
r = session.get(f"{BASE}/health")
assert r.status_code == 200 and r.json()["status"] == "ok"

# 2. Auth (test mode or real)
r = session.get(f"{BASE}/auth/me")
# Should return 401 (no cookie) or 200 (if test auth)

# 3. Upload CSV (create temp CSV with 2-3 job URLs)
# POST /upload with file
# Assert: rows created, stats returned

# 4. List rows
r = session.get(f"{BASE}/rows")
assert "rows" in r.json()

# 5. Record click
row_id = r.json()["rows"][0]["id"]
r = session.post(f"{BASE}/rows/{row_id}/click")

# 6. CRM endpoints
session.get(f"{BASE}/crm/applications")
session.get(f"{BASE}/crm/analytics")
session.get(f"{BASE}/crm/views")
session.get(f"{BASE}/crm/sessions")
session.post(f"{BASE}/crm/from-rows/bulk", json={"row_ids": [row_id]})

# 7. Bulk application creation
# POST /crm/applications/bulk

# 8. Exports
session.get(f"{BASE}/crm/export/dashboard?format=csv")
session.get(f"{BASE}/crm/export/applications?format=csv")
```

**Files created:**
- `scripts/smoke_jobgrid.py`

**Note:** Script should accept `--base-url` flag and handle auth via cookie or test mode. Later add `--test-auth` for CI.

---

### Feature 3: GitHub Actions CI

**Why:** Catch build failures before merge.

**New file:** `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]
jobs:
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: cd frontend && npm ci && npm run build

  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: backend/requirements.txt
      - run: cd backend && pip install -r requirements.txt && python -m compileall app
```

**Files created:**
- `.github/workflows/ci.yml`

**Later:** Add API smoke tests with a PostgreSQL service container.

---

### Feature 4: Pagination

**Why:** `/rows` and `/crm/applications` return full datasets. Slow with thousands of rows.

**Backend changes:**

1. **Add pagination params to `GET /rows`** in `backend/app/routers/rows.py`:
   ```python
   page: int = Query(1, ge=1)
   page_size: int = Query(50, ge=1, le=500)
   ```
   - Add `.offset((page - 1) * page_size).limit(page_size)` to query
   - Add `total_count` via separate `COUNT(*)` query
   - Return: `{"rows": [...], "total_count": N, "page": 1, "page_size": 50, "has_next": true}`

2. **Add pagination params to `GET /crm/applications`** in `backend/app/routers/crm.py`:
   - Same pattern: `page`, `page_size`, return `total_count`, `has_next`

3. **Update `filtered_query()`** in `crm.py` — return the query without `.all()`, let caller add offset/limit and count separately.

**Frontend changes:**

4. **Add pagination controls** to `Dashboard.jsx` and `Applications.jsx`:
   - Page number, prev/next buttons, page size selector
   - Update API calls to pass `page` and `page_size`
   - Store `total_count` and `has_next` in state

5. **Update `api/client.js`** — pass `page` and `page_size` params

**Files modified:**
- `backend/app/routers/rows.py:129` (add params, offset/limit)
- `backend/app/routers/crm.py:142` (add params, offset/limit)
- `frontend/src/pages/Dashboard.jsx` (add pagination UI)
- `frontend/src/pages/Applications.jsx` (add pagination UI)
- `frontend/src/api/client.js:32` (pass page params)

---

### Feature 5: Backend-Driven Filtering for Applications

**Why:** Applications fetches all records then filters in React. Won't scale.

**Current state:** The backend `GET /crm/applications` already supports many filters via query params. The frontend `Applications.jsx` fetches all data (line 137) then applies client-side filtering (line 150-197).

**Backend changes:**

1. **Move client-side-only filters to backend** — these filters exist only in React:
   - `quickRange` → already supported server-side via `quick_range` param
   - `followUpToday` → already supported via `follow_up_today`
   - `followUpOverdue` → already supported via `follow_up_overdue`
   - `followUpNone` → already supported via `follow_up_none`
   - `onlyOpenedNotApplied` → already supported via `opened_not_applied`
   - `hasError` → already supported via `has_error`
   - `jdMissing` → already supported via `jd_missing`

   **The backend already handles these!** The frontend just isn't sending them.

2. **Update `Applications.jsx`** — when filters change, send all filter params to the API instead of fetching once and filtering client-side:
   ```javascript
   const refresh = (nextFilters = filters) => {
     setLoading(true)
     api.getApplications({
       sort_by: sort.field,
       sort_dir: sort.direction,
       status: nextFilters.status || undefined,
       company: nextFilters.company || undefined,
       ats_group: nextFilters.atsGroup || undefined,
       quick_range: nextFilters.quickRange || undefined,
       // ... all other params
     }).then((data) => {
       setApplications(data.rows || [])
       setFilterOptions(data.filter_options || {})
     }).finally(() => setLoading(false))
   }
   ```

3. **Remove client-side `useMemo` filtering** — delete the `filtered` and `sorted` useMemo blocks (lines 150-217). Use API results directly.

4. **Keep `quickRange` values consistent** — frontend has `today`, `yesterday` which backend doesn't handle. Add these to backend `filtered_query()` or map them to date ranges client-side before sending.

**Files modified:**
- `frontend/src/pages/Applications.jsx:135-217` (refactor to server-side filtering)
- `backend/app/routers/crm.py:86-91` (add `today`/`yesterday` quick ranges if missing)

---

## Phase 2: P1 — JobGrid V1 Complete (Features 6–14)

### Feature 6: Saved Views Apply Filters

**Why:** Views are stored but never loaded into any filter state.

**Backend changes:**

1. **Add `is_pinned` field to `SavedView`** in `models.py`:
   ```python
   is_pinned = Column(Boolean, default=False, nullable=False)
   ```
   Add migration for this.

2. **Add `PUT /crm/views/{view_id}/pin`** endpoint in `crm.py`

**Frontend changes:**

3. **Add "Apply" button** to each row in `SavedViews.jsx` — clicking it:
   - Reads `view.filters` JSON
   - Navigates to the target page (`/`, `/applications`, `/pipeline`)
   - Passes filters via URL search params or React state

4. **Add "Edit" button** — opens a form to update view name/filters

5. **Add "Duplicate" button** — creates a copy with " (copy)" suffix

6. **Add "Pin" button** — toggles `is_pinned` field

7. **Load filters from URL params** — in `Dashboard.jsx` and `Applications.jsx`, on mount, check for `?view_id=X` or `?filters=...` URL params and apply them

8. **Default views loading** — when a page loads with a pinned view, auto-apply its filters

**Files modified:**
- `backend/app/models.py:184-197` (add `is_pinned`)
- `backend/app/routers/crm.py:314-342` (add pin endpoint)
- `frontend/src/pages/SavedViews.jsx` (add Apply/Edit/Duplicate/Pin buttons)
- `frontend/src/pages/Dashboard.jsx` (load filters from URL/view)
- `frontend/src/pages/Applications.jsx` (load filters from URL/view)
- Migration file for `is_pinned`

---

### Feature 7: Default Saved Views

**Why:** New users have no views. Auto-create useful defaults.

**Backend changes:**

1. **Add endpoint `POST /crm/views/defaults`** in `crm.py`:
   ```python
   DEFAULT_VIEWS = [
       {"name": "High score unopened", "view_type": "job_links", "filters": {"openedOnly": False, "minScore": "80"}},
       {"name": "Opened not applied", "view_type": "applications", "filters": {"onlyOpenedNotApplied": True}},
       {"name": "Follow-ups due", "view_type": "applications", "filters": {"followUpDue": True}},
       {"name": "Applied this week", "view_type": "applications", "filters": {"quickRange": "last_7_days", "status": "applied"}},
       {"name": "Greenhouse only", "view_type": "job_links", "filters": {"atsGroup": "greenhouse"}},
       {"name": "Sponsorship positive", "view_type": "job_links", "filters": {"sponsorshipStatus": "positive"}},
       {"name": "Sponsorship unclear", "view_type": "job_links", "filters": {"sponsorshipStatus": "unclear"}},
       {"name": "JD missing", "view_type": "job_links", "filters": {"jdMissing": True}},
       {"name": "Errors only", "view_type": "job_links", "filters": {"hasError": True}},
   ]
   ```
   - Creates defaults for the user (upsert by name+view_type)
   - Skips any that already exist

2. **Auto-call on first login** — in `auth_router.py`, after user creation, call this endpoint

**Frontend changes:**

3. **Add "Create default views" button** to `SavedViews.jsx` (for manual trigger)

**Files modified:**
- `backend/app/routers/crm.py` (add defaults endpoint)
- `backend/app/routers/auth_router.py` (auto-create on first login)
- `frontend/src/pages/SavedViews.jsx` (add button)

---

### Feature 8: Active Session Bar Globally

**Why:** Sessions exist but the active session is only shown on the Sessions page.

**Frontend changes:**

1. **Create `ActiveSessionBar.jsx` component** — shows:
   ```
   Active session: Friday applications | Started: 6:42 PM | Opened: 12 | Sent to Applications: 8 | Applied: 4 | [End session]
   ```
   - Fetches active session from `GET /crm/sessions`
   - Computes counts from `GET /crm/stats` (or new session-scoped stats endpoint)
   - Includes "End session" button

2. **Add to `App.jsx`** — render `ActiveSessionBar` below the topbar in `AuthenticatedApp`, only when an active session exists

3. **Update `styles.css`** — style the global session bar (sticky at top, distinct from page content)

**Backend changes:**

4. **Add `GET /crm/sessions/active`** endpoint — returns the currently active session (where `ended_at IS NULL`) with stats

**Files created/modified:**
- `frontend/src/components/ActiveSessionBar.jsx` (new)
- `frontend/src/App.jsx:38-67` (add bar to layout)
- `backend/app/routers/crm.py` (add active session endpoint)
- `frontend/src/styles.css` (add styles)

---

### Feature 9: Track Session Activity Counts

**Why:** Sessions only store name/time/notes. No activity tracking.

**Best approach:** Audit events table (Feature 10), then calculate session stats from events.

**Backend changes:**

1. **Add `AuditEvent` model** (see Feature 10)

2. **Add `GET /crm/sessions/{session_id}/stats`** endpoint:
   ```python
   def session_stats(session_id, db, user):
       session = db.query(SearchSession).filter_by(id=session_id, user_id=user.id).first()
       events = db.query(AuditEvent).filter(
           AuditEvent.session_id == session_id,
           AuditEvent.user_id == user.id,
       ).all()
       return {
           "uploads_count": count(events, "csv_uploaded"),
           "urls_opened": count(events, "row_opened"),
           "sent_to_applications": count(events, "row_sent_to_applications"),
           "applications_marked_applied": count(events, "application_marked_applied"),
           "followups_set": count(events, "followup_set"),
           "exports_created": count(events, "rows_exported") + count(events, "applypilot_batch_exported"),
       }
   ```

3. **Emit events** — when any tracked action occurs, create an `AuditEvent` with the current `session_id`

**Files modified:**
- `backend/app/models.py` (add `AuditEvent`)
- `backend/app/routers/crm.py` (add session stats endpoint, emit events)
- Migration file for `audit_events`

---

### Feature 10: Audit Event Log

**Why:** Powers analytics, undo, session summaries, debugging.

**Backend changes:**

1. **Add `AuditEvent` model** to `models.py`:
   ```python
   class AuditEvent(Base):
       __tablename__ = "audit_events"
       id = Column(Integer, primary_key=True)
       user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
       session_id = Column(Integer, ForeignKey("search_sessions.id"), nullable=True, index=True)
       event_type = Column(String(100), nullable=False, index=True)
       entity_type = Column(String(50), nullable=False)
       entity_id = Column(Integer, nullable=True)
       metadata_json = Column(JSONB, default=dict)
       created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
   ```

2. **Add event emission helper** in `crm.py` or a new `audit.py`:
   ```python
   def emit_event(db, user_id, session_id, event_type, entity_type, entity_id=None, metadata=None):
       event = AuditEvent(
           user_id=user_id, session_id=session_id,
           event_type=event_type, entity_type=entity_type,
           entity_id=entity_id, metadata_json=metadata or {},
       )
       db.add(event)
   ```

3. **Emit events at these points:**
   - `upload.py` → `csv_uploaded`
   - `rows.py:record_click` → `row_opened`
   - `crm.py:bulk_create_from_rows` → `row_sent_to_applications`
   - `crm.py:update_app` (when `mark_applied`) → `application_marked_applied`
   - `crm.py:update_app` (when status changes) → `application_status_changed`
   - `crm.py:set_follow_up_preset` → `followup_set`
   - `crm.py:export_dashboard/export_applications` → `rows_exported`
   - `Dashboard.jsx:exportApplyPilot` → `applypilot_batch_exported`

4. **Add `GET /crm/audit`** endpoint — list events with filtering by `event_type`, `session_id`, date range

5. **Auto-link to active session** — when emitting events, look up the user's active session and set `session_id`

**Files modified:**
- `backend/app/models.py` (add `AuditEvent`)
- `backend/app/routers/crm.py` (emit events, add audit endpoint)
- `backend/app/routers/upload.py` (emit csv_uploaded)
- `backend/app/routers/rows.py` (emit row_opened)
- Migration file for `audit_events`

---

### Feature 11: Dashboard Row Drawer

**Why:** Table has too many columns. A side drawer shows full details.

**Frontend changes:**

1. **Create `RowDrawer.jsx` component** — a slide-in panel from the right:
   - Company / title / URL
   - Application status badge
   - Notes (editable)
   - Follow-up date
   - JD text (scrollable)
   - Sponsorship evidence
   - Location evidence
   - Duplicate info
   - ApplyPilot payload preview
   - Original CSV fields (all 33 columns)

2. **Add to `Dashboard.jsx`** — when a row is clicked (not the URL link), open the drawer:
   - Track `selectedDrawerRow` state
   - Pass row data to `RowDrawer`
   - Drawer has close button

3. **Update `DataTable.jsx`** — add an expand/detail icon column that opens the drawer (separate from the URL click)

4. **Styles** — add drawer CSS: fixed position, right side, overlay, slide animation

**Files created/modified:**
- `frontend/src/components/RowDrawer.jsx` (new)
- `frontend/src/pages/Dashboard.jsx` (add drawer state, render drawer)
- `frontend/src/components/DataTable.jsx` (add expand button)
- `frontend/src/styles.css` (drawer styles)

---

### Feature 12: Application Status Badges in Job Links

**Why:** Backend already returns `app_status`, `app_id`, `applied_at`, `follow_up_at`, `app_notes` in `/rows`. Now show them visually.

**Frontend changes:**

1. **Update `DataTable.jsx`** — in the "Status" or a new "App Status" column, render badges:
   ```jsx
   {row.app_status && (
     <span className={`app-status-badge ${row.app_status}`}>
       {row.app_status}
     </span>
   )}
   ```
   - CSS classes already exist in `styles.css:309-316` (`.app-status-badge.applied`, `.interview`, etc.)

2. **Add follow-up badge** — if `row.follow_up_at` is set:
   ```jsx
   {row.follow_up_at && <span className="follow-up-badge">Follow-up</span>}
   ```

3. **Add "Already sent" indicator** — if `row.app_id` is set but `app_status` is `opened`, show "Sent to Applications" badge

**Files modified:**
- `frontend/src/components/DataTable.jsx` (add badge rendering)

---

### Feature 13: Bulk Status Actions on Dashboard

**Why:** Only "Send to Applications" exists. Need bulk mark-applied, not-applying, follow-up, rejected.

**Backend changes:**

1. **Extend `PATCH /crm/applications/bulk`** — already supports `status` field in the patch. Just need to use it from the frontend.

**Frontend changes:**

2. **Add bulk action buttons** to `Dashboard.jsx` sticky toolbar:
   ```jsx
   <button onClick={() => bulkStatusAction('applied')}>Mark applied</button>
   <button onClick={() => bulkStatusAction('not_applying')}>Mark not applying</button>
   <button onClick={() => bulkStatusAction('follow_up')}>Mark follow-up</button>
   <button onClick={() => bulkStatusAction('rejected')}>Mark rejected</button>
   ```

3. **Implement `bulkStatusAction`**:
   ```javascript
   const bulkStatusAction = async (status) => {
     const ids = [...selectedRowIds]
     // First, ensure all rows have applications
     await api.bulkCreateApplicationsFromRows(ids)
     // Then update status
     await api.bulkUpdateApplications(ids, { status })
     toast(`Marked ${ids.length} as ${status}`, 'success')
     await loadRows(sort, filters)
   }
   ```

4. **Add keyboard shortcuts** — extend `handleKeyDown`:
   - `Shift+A` → mark applied
   - `Shift+N` → mark not applying
   - `Shift+F` → mark follow-up
   - `Shift+R` → mark rejected

**Files modified:**
- `frontend/src/pages/Dashboard.jsx` (add buttons, handler, shortcuts)

---

### Feature 14: Bulk Follow-Up Tools

**Why:** Backend already has follow-up presets (`3_days`, `7_days`, `next_monday`, `clear`). Make them available everywhere.

**Backend changes:**

1. **Add bulk follow-up endpoint** — `POST /crm/applications/bulk/follow-up`:
   ```python
   @router.post("/applications/bulk/follow-up")
   def bulk_set_follow_up(item_ids: List[int], preset: str, db, user):
       items = db.query(JobTrack).filter(JobTrack.id.in_(item_ids), JobTrack.user_id == user.id).all()
       for item in items:
           # Apply same preset logic as single follow-up
       db.commit()
   ```

**Frontend changes:**

2. **Add bulk follow-up buttons** to `Dashboard.jsx` and `Applications.jsx` sticky toolbars:
   ```jsx
   <button onClick={() => bulkFollowUp('3_days')}>Follow up in 3 days</button>
   <button onClick={() => bulkFollowUp('7_days')}>Follow up in 7 days</button>
   <button onClick={() => bulkFollowUp('next_monday')}>Follow up next Monday</button>
   <button onClick={() => bulkFollowUp('clear')}>Clear follow-up</button>
   ```

3. **Update `api/client.js`** — add `bulkFollowUpPreset(ids, preset)` method

**Files modified:**
- `backend/app/routers/crm.py` (add bulk follow-up endpoint)
- `frontend/src/pages/Dashboard.jsx` (add buttons)
- `frontend/src/pages/Applications.jsx` (add buttons)
- `frontend/src/api/client.js` (add method)

---

## Phase 3: P2 — ApplyPilot Handoff System (Features 15–18)

### Feature 15: ApplyPilot Batches Page

**Why:** Currently downloads a raw JSON file. Need trackable batches.

**New page:** `frontend/src/pages/ApplyPilotBatches.jsx`

**Backend changes:**

1. **Add `ApplyPilotBatch` model** (see Feature 16)

2. **Add `POST /crm/applypilot/batches`** — create a batch from selected row IDs:
   ```python
   @router.post("/applypilot/batches")
   def create_batch(row_ids: List[int], name: str = None, db, user):
       rows = db.query(CsvRow).filter(CsvRow.id.in_(row_ids), CsvRow.user_id == user.id).all()
       payload = [serialize_for_applypilot(r) for r in rows]
       batch = ApplyPilotBatch(
           user_id=user.id, name=name or f"Batch {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
           payload_json=payload, status="downloaded", job_count=len(payload),
       )
       db.add(batch)
       db.commit()
       return {"batch_id": batch.id, "status": batch.status, "job_count": batch.job_count}
   ```

3. **Add `GET /crm/applypilot/batches`** — list all batches

4. **Add `GET /crm/applypilot/batches/{batch_id}/download`** — re-download the JSON payload

**Frontend changes:**

5. **Create `ApplyPilotBatches.jsx`** page:
   - Table: Name, Created, Job Count, Status, Actions (Download, Delete)
   - Status badges: downloaded (blue), sent (yellow), completed (green), failed (red)

6. **Update `Dashboard.jsx`** — change "Send 5 to ApplyPilot" to create a batch:
   ```javascript
   const exportApplyPilot = async () => {
     const ids = [...selectedRowIds]
     const result = await api.createApplyPilotBatch(ids)
     toast(`Batch created: ${result.job_count} jobs`, 'success')
   }
   ```

7. **Add route** in `App.jsx`:
   ```jsx
   <Route path="/applypilot" element={<ApplyPilotBatches />} />
   ```

8. **Add nav tab** in `Navigation.jsx`

**Files created/modified:**
- `frontend/src/pages/ApplyPilotBatches.jsx` (new)
- `backend/app/routers/crm.py` (add batch endpoints)
- `backend/app/models.py` (add `ApplyPilotBatch`)
- `frontend/src/pages/Dashboard.jsx` (change export to create batch)
- `frontend/src/App.jsx` (add route)
- `frontend/src/components/Navigation.jsx` (add tab)
- Migration file for `applypilot_batches`

---

### Feature 16: Store ApplyPilot Batch History

**Why:** Currently just downloads JSON. Need to persist batch records.

**Backend changes:**

1. **Add `ApplyPilotBatch` model** to `models.py`:
   ```python
   class ApplyPilotBatch(Base):
       __tablename__ = "applypilot_batches"
       id = Column(Integer, primary_key=True)
       user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
       session_id = Column(Integer, ForeignKey("search_sessions.id"), nullable=True)
       name = Column(String(200))
       payload_json = Column(JSONB, nullable=False)
       status = Column(String(50), default="downloaded", nullable=False)
       created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
       updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
   ```

2. **Add relationship** to `User` model

3. **Migration** — add `applypilot_batches` table

**Files modified:**
- `backend/app/models.py` (add model)
- Migration file

---

### Feature 17: ApplyPilot Result Import

**Why:** When ApplyPilot returns results, update application status automatically.

**Backend changes:**

1. **Add `POST /crm/applypilot/import`** endpoint:
   ```python
   @router.post("/applypilot/import")
   def import_results(results: List[ApplyPilotResultIn], db, user):
       for result in results:
           track = db.query(JobTrack).filter_by(user_id=user.id, url=result.url).first()
           if track:
               if result.submitted:
                   track.status = "applied"
                   track.applied_at = parse_dt(result.submitted_at)
               if result.error:
                   track.notes = f"ApplyPilot error: {result.error}"
               # Update batch status
       db.commit()
   ```

2. **Add `ApplyPilotResultIn` schema** to `schemas.py`

**Frontend changes:**

3. **Add import button** to `ApplyPilotBatches.jsx` — upload `applypilot_results.json`

**Files modified:**
- `backend/app/routers/crm.py` (add import endpoint)
- `backend/app/schemas.py` (add result schema)
- `frontend/src/pages/ApplyPilotBatches.jsx` (add import UI)

---

### Feature 18: ApplyPilot Readiness Score

**Why:** Validate jobs before export.

**Backend changes:**

1. **Add readiness calculation** to batch creation endpoint:
   ```python
   def calculate_readiness(row):
       checks = {
           "url_present": bool(row.url),
           "jd_text_present": bool(row.jd_text and len(row.jd_text) > 50),
           "company_present": bool(row.company_guess),
           "title_present": bool(row.title),
           "location_acceptable": row.location_group not in ["remote_restricted", "unknown"],
           "sponsorship_acceptable": row.sponsorship_status not in ["negative"],
           "resume_score_high": float(row.resume_match_score or 0) >= 70,
           "not_duplicate": not row.is_duplicate,
       }
       passed = sum(checks.values())
       total = len(checks)
       if passed == total:
           return "ready"
       elif passed >= total * 0.6:
           return "needs_review"
       else:
           return "do_not_send"
   ```

2. **Include readiness in batch response** and in each row's data

**Frontend changes:**

3. **Show readiness badges** in `ApplyPilotBatches.jsx` and `Dashboard.jsx`:
   - Ready (green), Needs review (yellow), Do not send (red)

**Files modified:**
- `backend/app/routers/crm.py` (add readiness calculation)
- `frontend/src/pages/ApplyPilotBatches.jsx` (show badges)
- `frontend/src/pages/Dashboard.jsx` (show readiness in export preview)

---

## Phase 4: P3 — Better Analytics (Features 19–23)

### Feature 19: Funnel Analytics

**Why:** Show conversion rates through the pipeline.

**Backend changes:**

1. **Add funnel endpoint** `GET /crm/analytics/funnel`:
   ```python
   @router.get("/analytics/funnel")
   def funnel_analytics(db, user):
       uploaded = db.query(CsvRow).filter(CsvRow.user_id == user.id).count()
       tracks = db.query(JobTrack).filter(JobTrack.user_id == user.id)
       opened = tracks.count()
       sent_to_apps = tracks.filter(JobTrack.csv_row_id.isnot(None)).count()
       applied = tracks.filter(JobTrack.applied_at.isnot(None)).count()
       interview = tracks.filter(JobTrack.status == "interview").count()
       offer = tracks.filter(JobTrack.status == "offer").count()
       rejected = tracks.filter(JobTrack.status == "rejected").count()
       return {
           "stages": [
               {"name": "Uploaded", "count": uploaded},
               {"name": "Opened", "count": opened},
               {"name": "Sent to Applications", "count": sent_to_apps},
               {"name": "Applied", "count": applied},
               {"name": "Interview", "count": interview},
               {"name": "Offer", "count": offer},
           ],
           "rates": {
               "open_rate": round(opened / uploaded * 100, 1) if uploaded else 0,
               "application_rate": round(applied / opened * 100, 1) if opened else 0,
               "interview_rate": round(interview / applied * 100, 1) if applied else 0,
               "rejection_rate": round(rejected / applied * 100, 1) if applied else 0,
           }
       }
   ```

**Frontend changes:**

2. **Add funnel visualization** to `Analytics.jsx`:
   - Horizontal funnel bar showing each stage getting smaller
   - Conversion rate percentages between stages

**Files modified:**
- `backend/app/routers/crm.py` (add funnel endpoint)
- `frontend/src/pages/Analytics.jsx` (add funnel chart)
- `frontend/src/api/client.js` (add `getFunnelAnalytics`)
- `frontend/src/styles.css` (funnel styles)

---

### Feature 20: ATS Performance

**Why:** Show which ATS platforms perform best.

**Backend changes:**

1. **Extend `GET /crm/analytics`** or add `GET /crm/analytics/ats`:
   ```python
   # For each ATS group, compute:
   - uploaded count (from csv_rows)
   - opened count (from job_tracks with that ats_group)
   - applied count (from job_tracks with applied_at)
   - interview count
   - rejection count
   - average score
   ```

**Frontend changes:**

2. **Add ATS performance table/chart** to `Analytics.jsx`:
   - Table with columns: ATS, Uploaded, Opened, Applied, Interviews, Rejections, Avg Score
   - Bar chart for visual comparison

**Files modified:**
- `backend/app/routers/crm.py` (extend analytics)
- `frontend/src/pages/Analytics.jsx` (add ATS table)

---

### Feature 21: Search Bucket Performance

**Why:** Which scraper buckets are most useful?

**Backend changes:**

1. **Add `GET /crm/analytics/buckets`** — same pattern as ATS but grouped by `search_bucket`:
   - average score, applied count, interview count, opened-not-applied count

**Frontend changes:**

2. **Add bucket performance chart** to `Analytics.jsx`

**Files modified:**
- `backend/app/routers/crm.py` (add bucket analytics endpoint)
- `frontend/src/pages/Analytics.jsx` (add bucket chart)

---

### Feature 22: Daily Goals

**Why:** Track progress against configurable goals.

**Backend changes:**

1. **Add `UserGoal` model**:
   ```python
   class UserGoal(Base):
       __tablename__ = "user_goals"
       user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
       open_per_day = Column(Integer, default=30)
       apply_per_day = Column(Integer, default=10)
       followup_per_day = Column(Integer, default=5)
       applypilot_per_day = Column(Integer, default=5)
   ```

2. **Add `GET/PUT /crm/goals`** endpoints

3. **Add `GET /crm/analytics/goals`** — compute today's progress against goals using audit events

**Frontend changes:**

4. **Add goals panel** to `Analytics.jsx`:
   - Progress bars for each goal
   - "Open 30/day: 18/30 (60%)"
   - Configuration modal to edit goals

**Files modified:**
- `backend/app/models.py` (add `UserGoal`)
- `backend/app/routers/crm.py` (add goals endpoints)
- `frontend/src/pages/Analytics.jsx` (add goals UI)
- Migration file for `user_goals`

---

### Feature 23: Weekly Report

**Why:** Summarize weekly progress.

**Backend changes:**

1. **Add `GET /crm/analytics/weekly`** endpoint:
   ```python
   @router.get("/analytics/weekly")
   def weekly_report(db, user):
       now = datetime.utcnow()
       week_start = now - timedelta(days=7)
       # Compute: jobs uploaded, opened, applied, follow-ups completed, interviews
       # Top companies, best ATS sources, next week's follow-ups
   ```

**Frontend changes:**

2. **Add weekly report section** to `Analytics.jsx`:
   - Summary cards
   - "Export as Markdown" button (generates markdown client-side)

**Files modified:**
- `backend/app/routers/crm.py` (add weekly endpoint)
- `frontend/src/pages/Analytics.jsx` (add report section)

---

## Implementation Order (Recommended)

### Sprint 1: Foundation (P0)
1. Feature 1: Alembic migrations
2. Feature 3: GitHub Actions CI
3. Feature 2: Smoke test script

### Sprint 2: Scale (P0)
4. Feature 4: Pagination
5. Feature 5: Backend-driven filtering

### Sprint 3: Views & Sessions (P1)
6. Feature 6: Saved Views apply filters
7. Feature 7: Default saved views
8. Feature 8: Active session bar globally
9. Feature 10: Audit event log
10. Feature 9: Session activity counts

### Sprint 4: Dashboard UX (P1)
11. Feature 11: Row drawer
12. Feature 12: Application status badges
13. Feature 13: Bulk status actions
14. Feature 14: Bulk follow-up tools

### Sprint 5: ApplyPilot (P2)
15. Feature 16: Batch history model
16. Feature 15: Batches page
17. Feature 18: Readiness score
18. Feature 17: Result import

### Sprint 6: Analytics (P3)
19. Feature 19: Funnel analytics
20. Feature 20: ATS performance
21. Feature 21: Bucket performance
22. Feature 22: Daily goals
23. Feature 23: Weekly report

---

## Migration Summary

Total new migrations needed:

1. Initial schema (from `create_all` → Alembic)
2. Add `is_pinned` to `saved_views`
3. Add `audit_events` table
4. Add `applypilot_batches` table
5. Add `user_goals` table

---

## Dependencies Graph

```
Feature 1 (Alembic) ─────────────────────────────────────────┐
Feature 2 (Smoke test) ──────────────────────────────────────┤
Feature 3 (CI) ──────────────────────────────────────────────┤
Feature 4 (Pagination) ──────────────────────────────────────┤
Feature 5 (Server filtering) ────────────────────────────────┤
                                                              │
Feature 6 (Saved Views apply) ── depends on: Feature 1       │
Feature 7 (Default views) ── depends on: Feature 6           │
Feature 8 (Session bar) ── depends on: Feature 10            │
Feature 9 (Session counts) ── depends on: Feature 10         │
Feature 10 (Audit events) ── depends on: Feature 1           │
Feature 11 (Row drawer) ── standalone                        │
Feature 12 (Status badges) ── standalone                     │
Feature 13 (Bulk status) ── standalone                       │
Feature 14 (Bulk follow-up) ── standalone                    │
                                                              │
Feature 15 (Batches page) ── depends on: Feature 16          │
Feature 16 (Batch model) ── depends on: Feature 1            │
Feature 17 (Result import) ── depends on: Feature 16         │
Feature 18 (Readiness) ── depends on: Feature 16             │
                                                              │
Feature 19 (Funnel) ── depends on: Feature 10                │
Feature 20 (ATS perf) ── standalone                          │
Feature 21 (Bucket perf) ── standalone                       │
Feature 22 (Daily goals) ── depends on: Feature 10           │
Feature 23 (Weekly report) ── depends on: Feature 10         │
```
