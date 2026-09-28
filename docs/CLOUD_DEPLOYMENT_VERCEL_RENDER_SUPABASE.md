# JobGrid Cloud Deployment: Vercel + Render + Supabase

This runbook is the C-09 deployment contract for JobGrid:

- **Vercel**: React/Vite frontend
- **Render**: one FastAPI backend instance with a private persistent disk
- **Supabase**: managed PostgreSQL only

Supabase Auth, Storage, Realtime, and the Data API are not required. FastAPI remains the only application layer that reads and writes PostgreSQL through SQLAlchemy. Private document bytes remain on the existing filesystem adapter; C-09 makes that filesystem durable instead of replacing the adapter.

## Repository deployment assets

- `/render.yaml` — Render Blueprint for the backend and durable document disk
- `/backend/.python-version` — pins Python 3.12
- `/frontend/vercel.json` — SPA fallback for React Router/deep links
- `/backend/scripts/c09_storage_audit.py` — read-only database/filesystem reconciliation for restart, redeploy, and recovery evidence
- `/docs/RELEASE_ACCEPTANCE.md` — staging acceptance and release-evidence contract
- `/docs/BACKUP_STRATEGY.md` — portable application backup/recovery rules

## Cost and topology boundary

C-09 cannot use Render Free for the backend because Free web services cannot attach a persistent disk. The checked-in Blueprint therefore uses Render plan `0.5c-512mb`, the smallest paid web-service compute plan at the time C-09 was prepared, plus a 1 GB persistent disk.

At the 2026-09-28 Render prices used during preparation, this means approximately:

- backend compute: **$7/month** when continuously running;
- persistent disk: **$0.25/GB/month**;
- C-09 disk: **1 GB**, or **$0.25/month**.

Pricing and plan identifiers can change. Re-check Render's official pricing and compute-plan documentation before provisioning. Repository changes do not authorize billing changes.

The disk is mounted at `/var/data`; JobGrid writes only under:

```text
/var/data/jobgrid-documents
```

`DOCUMENT_STORAGE_DIR` must point to that exact private directory. Only data below the Render disk mount survives deploys/restarts. The disk belongs to one service instance, so the backend is intentionally pinned to `numInstances: 1` and cannot use horizontal autoscaling while this storage architecture is in place.

Render persistent disks also prevent zero-downtime instance swaps. A redeploy can therefore create a short backend interruption. This is an accepted C-09 tradeoff for the current single-user/small-scale architecture; moving to object storage is a future architecture change, not a C-09 requirement.

Official references:

- https://render.com/docs/disks
- https://render.com/docs/compute-plans
- https://render.com/pricing

## Deployment order

Use one fixed candidate SHA.

1. Confirm the Supabase staging database and record its current Alembic revision.
2. Confirm Vercel frontend project/root/build settings.
3. Sync the Render Blueprint **after explicitly accepting the paid compute/disk change**.
4. Supply the host-managed secrets/origins described below.
5. Let the single backend process start. For PostgreSQL, application import runs `alembic upgrade head` before route registration.
6. Require `GET /ready` to return HTTP 200. A migration, database, or document-storage failure must prevent readiness.
7. Require `GET /health` to retain the lightweight `{"status":"ok"}` liveness contract.
8. Point the Vercel frontend at the candidate backend and confirm CORS/HTTPS behavior.
9. Configure real OAuth callback URLs and controlled SMTP only when C-10 is authorized.
10. Execute C-10 against the same candidate; do not treat C-09 configuration as real-provider acceptance.

Do not start several application instances to race the same startup migration. The persistent disk already enforces the intended one-instance backend. If the project later moves to horizontally scaled/object-storage architecture, schema migration ownership must move to one explicit coordinated migration job before scaling.

## Supabase

Use Supabase as PostgreSQL only.

Current C-09 provider evidence was collected from the connected `jobgrid` project:

- region: `ap-southeast-1` (Singapore);
- PostgreSQL: 17.6;
- observed Alembic revision at C-09 intake: `018`;
- reported server connection limit at intake: 60;
- observed active connections during inspection: 7.

These are observations, not permanent capacity guarantees. Re-check connection utilization before promotion.

For Render, use the Supabase **Session Pooler** connection string if the direct hostname is not reachable over IPv4. Set the complete connection string in Render as `DATABASE_URL`. Never commit it.

The application starts Alembic automatically whenever `DATABASE_URL` is not SQLite. A failed migration therefore prevents successful application startup and `/ready` success.

## Render Blueprint contract

The checked-in Blueprint declares:

- Runtime: Python
- Python family: 3.12
- Region: Singapore
- Compute plan: `0.5c-512mb`
- Instance count: 1
- Persistent disk mount: `/var/data`
- Persistent disk size: 1 GB
- Private document root: `/var/data/jobgrid-documents`
- Root directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Liveness endpoint: `/health`
- Render readiness/health gate: `/ready`
- Auto-deploy: only after repository checks pass

Required host-managed values:

- `DATABASE_URL` — Supabase PostgreSQL connection string
- `FRONTEND_URL` — actual Vercel staging/production HTTPS origin
- `CORS_ORIGINS` — explicit allowed HTTPS origins
- `OAUTH_REDIRECT_BASE` — actual public backend callback base or final proxied `/api` base
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — only when Google OAuth is configured

`APP_SECRET_KEY` is generated by Render from `render.yaml`. Never copy it to source control.

C-09 safe defaults remain explicit in the Blueprint:

```text
ENVIRONMENT=production
TEST_AUTH=false
RUN_MAINTENANCE_JOBS=false
RUN_REMINDER_WORKER=false
REMINDER_EMAIL_DELIVERY_ENABLED=false
JOB_URL_CHECKS_ENABLED=false
AUTO_ARCHIVE_AFTER_DAYS=0
AUTO_PURGE_AFTER_DAYS=0
```

The single Render backend process is the **designated scheduler owner**. C-10 may enable the maintenance/reminder switches only for a controlled test window after the relevant fixture/SMTP authorization exists. Email delivery remains a separate gate. Do not enable the reminder worker with uncontrolled real recipients merely to prove the scheduler starts.

### Worker restart/concurrency contract

The execution arrangement relies on durable PostgreSQL coordination, not only process-local flags:

- automatic archive uses a PostgreSQL advisory lock in addition to an in-process lock;
- reminder claiming uses row locks plus durable `lease_until` state;
- expired reminder claims are recovered as an explicit unknown state rather than blindly re-sent;
- external URL checks remain disabled;
- automatic purge remains disabled.

This means restarting the designated process does not make the process-local scheduler itself durable; the **work state and concurrency boundary** are durable in PostgreSQL. C-10 must still exercise restart/recovery on the deployed candidate.

## Liveness and readiness

`GET /health` is intentionally only process liveness and remains backward compatible:

```json
{"status":"ok"}
```

`GET /ready` is the deployment gate. It performs:

1. `SELECT 1` through the configured application database session;
2. private document-storage validation/creation of the expected internal directories;
3. safe writable/readable/executable checks without returning the configured path.

Healthy response:

```json
{
  "status": "ready",
  "checks": {
    "database": "ready",
    "document_storage": "ready"
  }
}
```

Failure returns HTTP 503 with only safe component codes. It must not include a DSN, secret, document name, storage path, or exception text.

Important: `/ready` proves that the configured filesystem is usable. It does **not** prove that the filesystem is persistent. Persistence proof requires the C-09/C-10 restart/redeploy procedure below.

## Durable document proof

After paid disk provisioning and before C-09 is called externally complete:

1. create/use a synthetic staging account;
2. upload a small non-sensitive PDF or UTF-8 text document through JobGrid;
3. record its application-visible SHA-256/metadata without recording file content;
4. from the Render service runtime, run:

```bash
cd backend
python scripts/c09_storage_audit.py
```

5. record the aggregate `inventory_sha256` and zero mismatch counts;
6. restart the Render service and run the audit again;
7. redeploy the **same candidate SHA** and run the audit again;
8. download the synthetic document through the authenticated application and confirm its SHA-256 is unchanged.

A PASS requires the same ready-document inventory with zero missing/size/hash mismatches after restart and redeploy. A local temporary directory or successful `/ready` alone is not durability evidence.

## Database + document recovery package

There are two distinct layers:

### Application-portable recovery

JobGrid complete backup/restore ZIPs are the account-scoped portable recovery format. They preserve the supported database graph plus verified immutable document bytes. The C-10 restore gate must use a nonempty synthetic account and compare normalized records plus file hashes.

### Hosting/disaster recovery

The staging hosting package has two provider-owned components:

- **Supabase PostgreSQL** — provider database backups plus an operator-created logical dump before a release/restore rehearsal;
- **Render document disk** — Render automatically snapshots an attached persistent disk once every 24 hours; snapshots are available for at least seven days according to the current Render documentation.

A database dump by itself is **not** a complete JobGrid recovery package because document bytes live on the Render disk. A Render disk snapshot by itself is also incomplete because document metadata and the rest of application state live in PostgreSQL.

Before a destructive rehearsal, record both recovery points and their timestamps. Restore only into the authorized disposable destination described in `docs/RELEASE_ACCEPTANCE.md`. After recovery, run the portable-account comparison and `c09_storage_audit.py`/document hash checks before accepting the result.

The existing `scripts/backup.sh` and `scripts/restore.sh` are Docker Compose PostgreSQL utilities. They do not back up the Render document disk and must never be described as a complete cloud-environment backup.

## Backup objectives and ownership

C-09 preparation uses these minimum facts:

- Render document disk: automatic daily snapshot, at least seven days of available snapshots under current Render policy;
- PostgreSQL: take an explicit logical dump before each C-10 restore/rollback rehearsal in addition to provider backup capability;
- restore target: disposable staging database/storage only until C-10 proves the procedure;
- owner: release operator with access to Render, Supabase, Vercel, OAuth provider, and controlled inbox;
- secrets/backups: private operator-controlled storage only, never the public repository or a public CI artifact.

**Needs Operator Decision before C-09 external closure:** agree the target RPO and RTO and the private off-platform destination/retention for logical database backups. Do not convert provider snapshot frequency into a claimed business RPO/RTO without a measured rehearsal.

## Vercel

Configure the Vercel project with:

- Root directory: `frontend`
- Framework: Vite
- Build command: `npm run build`
- Output directory: `dist`

`frontend/vercel.json` provides the SPA fallback required for direct React Router navigation.

Before a Vercel-to-Render reverse proxy is configured, set `VITE_API_URL` to the actual Render HTTPS origin. If `/api/*` is later proxied through Vercel, change `VITE_API_URL` to `/api` and align backend frontend/CORS/OAuth values with the final public origin.

No database credential belongs in any `VITE_*` variable.

## OAuth and SMTP

Real OAuth and SMTP receipt are C-10 external acceptance gates.

- keep provider credentials in Render's secret store only;
- keep `TEST_AUTH=false` in staging/production;
- use only a controlled OAuth test account;
- send only to an explicitly authorized controlled inbox;
- `logged`, queued, or mocked email is not delivery evidence;
- never commit provider access tokens, session cookies, recipient addresses, inbox bodies, or credentials.

## Monitoring and induced-failure checks

At minimum the release operator must have documented checks for:

| Risk | Check | Failure signal |
|---|---|---|
| Backend unavailable | Render service health + `GET /ready` | non-200 / deploy health failure |
| Database unavailable | `/ready` | `checks.database=unavailable` |
| Document mount unavailable | `/ready` | `checks.document_storage!=ready` |
| Missing/corrupt document bytes | `python scripts/c09_storage_audit.py` | nonzero exit or mismatch count |
| Disk exhaustion | Render Disk usage + audit `free_bytes` | agreed free-capacity threshold crossed |
| Maintenance failure/staleness | maintenance health endpoint/logs and `MaintenanceStatus` | failed/stale outcome |
| Reminder failure | reminder delivery history/logs | repeated failed/unknown outcomes |
| Backup failure | provider backup/snapshot status + rehearsal record | missing/failed expected recovery point |

Induced storage failure procedure for a disposable staging configuration:

1. record the currently working storage setting privately;
2. temporarily point `DOCUMENT_STORAGE_DIR` at a known unavailable/invalid private path **only in the disposable staging service**;
3. confirm `/ready` returns 503 with a safe storage code;
4. restore the real disk-backed setting;
5. confirm `/ready` returns 200 and the storage audit is still PASS.

Do not run this against production and do not delete or corrupt the actual persistent disk to test monitoring.

## C-09/C-10 verification checklist

### C-09 preparation

- [ ] Actual Vercel frontend project and URL recorded
- [ ] Actual Render backend service and URL recorded
- [x] Supabase `jobgrid` provider/runtime inspected
- [ ] Paid Render disk explicitly approved and provisioned
- [ ] `/ready` is healthy on the deployed candidate
- [ ] Synthetic document survives restart and redeploy
- [ ] Storage audit reports zero mismatches after both events
- [ ] One scheduler owner is recorded
- [ ] Private controlled inbox/test OAuth account are ready
- [ ] Database + disk recovery points are recorded
- [ ] RPO/RTO and private backup destination are agreed
- [ ] Induced failure is visible to the operator
- [ ] Existing release-evidence file is prepared with exact PASS/BLOCKED state

### C-10 acceptance

Follow `docs/RELEASE_ACCEPTANCE.md`. Real OAuth, real controlled SMTP receipt, deployed workflow smoke, restart/recovery, backup restore, and old-code rollback remain C-10. A green repository CI run does not replace these gates.

## Rollback

Keep the immediately previous known-good application SHA/build available.

Application rollback order:

1. stop/disable external workers if an ambiguous delivery failure is involved;
2. roll the application back to the previous known-good build only if its compatibility with the current schema has been checked;
3. do **not** automatically downgrade the schema;
4. verify `/health`, `/ready`, login/history, and document download;
5. restore a Render disk snapshot only for demonstrated document-disk corruption/loss, understanding that post-snapshot file changes will be lost;
6. restore PostgreSQL only to the authorized recovery target/procedure and re-compare records/files before promotion.

Render application rollback does not roll the persistent disk backward. Disk snapshot restore is a separate, destructive operator action.

No C-09 repository change introduces a database migration.