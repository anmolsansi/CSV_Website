# JobGrid Cloud Deployment: Vercel + Render + Supabase

This runbook deploys JobGrid on a strict **zero-dollar-first** topology:

- **Vercel Free**: React/Vite frontend
- **Render Free**: FastAPI backend
- **Supabase Free**: managed PostgreSQL and private Storage

The backend remains the only application layer that authorizes JobGrid accounts and database access. Supabase Auth and Realtime are not required. Supabase Storage is used only for durable private document bytes because Render Free has an ephemeral filesystem.

## Zero-dollar boundary

This topology is designed to stay on free plans. It does not mean unlimited capacity.

Current provider constraints verified during C-09:

- Render Free provides one web-service instance and cannot attach a persistent disk. Its local filesystem is lost on restart, redeploy, and idle spin-down.
- Render Free spins down after 15 minutes without inbound traffic and has monthly free-instance, bandwidth, and build-pipeline limits.
- Supabase Free includes 1 GB of Storage. Exceeding a Free-plan quota can lead to notifications/grace/restrictions rather than being treated as unlimited capacity.
- JobGrid keeps its existing 100 MiB per-account document quota. `backend/scripts/c09_storage_audit.py` warns when total object storage approaches 900 MB so operators have headroom before the 1 GB free Storage quota.

Do not silently upgrade Render, Supabase, or Vercel to a paid plan. If a free quota becomes insufficient, the release owner must make a separate explicit architecture/billing decision.

## Repository deployment assets

- `/render.yaml` — Render Blueprint for the backend
- `/backend/.python-version` — pins Python 3.12
- `/frontend/vercel.json` — SPA fallback for React Router/deep links
- `/backend/app/services/document_storage.py` — filesystem/S3-compatible private-storage adapter
- `/backend/scripts/c09_storage_audit.py` — aggregate document integrity/capacity audit

## Deployment order

1. Keep/import the Vercel project with `frontend` as the project root.
2. Use the existing Supabase `jobgrid` project in Singapore.
3. In Supabase Storage, create a **private** bucket named `jobgrid-documents`.
4. In Supabase Storage S3 Configuration, enable S3 protocol access and generate a server-only access-key pair.
5. Copy the S3 endpoint and region plus the generated access-key ID/secret into Render secret environment values. Never put them in GitHub or Vercel frontend variables.
6. Sync/deploy the existing Render `jobgrid-api` service on the Free compute plan.
7. Verify `GET /ready` returns database and document-storage readiness.
8. Run the document upload/download and storage-audit durability checks.
9. Resolve the real frontend origin/CORS/OAuth configuration.
10. Continue with C-10 real-provider acceptance.

## Supabase PostgreSQL

Use Supabase as the managed PostgreSQL database through SQLAlchemy/Alembic.

Current C-09 provider evidence:

- project: `jobgrid`
- region: Singapore (`ap-southeast-1`)
- PostgreSQL: 17.6
- Alembic revision observed: `018`
- server-reported max connections observed: 60

For Render, use the Supabase Session Pooler connection string if the direct database hostname is not reachable over IPv4. Set the complete connection string only as Render `DATABASE_URL`.

The application runs Alembic at backend startup for non-SQLite databases. Migration failure prevents a successful application start.

## Supabase private document Storage

### Bucket

Create one bucket:

```text
jobgrid-documents
```

The bucket must remain private. Do not make it public to simplify downloads.

JobGrid already performs account authorization in FastAPI before document operations. The server-side S3 credentials are therefore infrastructure credentials, not browser credentials.

### S3 credentials

In Supabase Dashboard, open Storage → S3 Configuration. Enable the S3 protocol and generate an access-key pair intended only for server-side use.

Render requires these secret values:

```text
DOCUMENT_STORAGE_S3_ENDPOINT
DOCUMENT_STORAGE_S3_REGION
DOCUMENT_STORAGE_S3_ACCESS_KEY_ID
DOCUMENT_STORAGE_S3_SECRET_ACCESS_KEY
```

The checked-in bucket value is:

```text
DOCUMENT_STORAGE_S3_BUCKET=jobgrid-documents
```

Supabase documents the direct endpoint shape as:

```text
https://<project-ref>.storage.supabase.co/storage/v1/s3
```

Use the exact endpoint and region shown by the Supabase S3 configuration screen rather than reconstructing credentials from other project values.

Generated S3 access keys have broad Storage access and bypass RLS. Keep them only in Render secrets. Never expose them to frontend JavaScript, commit them, print them in CI, or include them in public evidence.

### Application storage contract

Production uses:

```text
DOCUMENT_STORAGE_BACKEND=s3
DOCUMENT_STAGING_DIR=/tmp/jobgrid-document-cache
```

`DOCUMENT_STAGING_DIR` is intentionally ephemeral. It contains only temporary upload/download cache material. Durable bytes live in Supabase Storage.

The application preserves the existing opaque `storage_key` database contract. Document metadata/checksums remain in PostgreSQL, while immutable bytes live in the private bucket.

Local tests/development may keep using the existing filesystem backend by omitting `DOCUMENT_STORAGE_BACKEND=s3` and configuring `DOCUMENT_STORAGE_DIR`.

## Render Free backend

The Blueprint keeps `jobgrid-api` on:

- Runtime: Python 3.12
- Region: Singapore
- Plan: Free
- Root: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Liveness: `/health`
- Deployment readiness: `/ready`
- Instances: one
- Auto-deploy: after repository checks pass

Do not attach a Render persistent disk. Free Render services cannot use one, and local files do not survive spin-down/restart/redeploy.

The current service URL recorded during C-09 is:

```text
https://jobgrid-api.onrender.com
```

### Required Render values

Host-managed values:

- `DATABASE_URL`
- `FRONTEND_URL`
- `CORS_ORIGINS`
- `OAUTH_REDIRECT_BASE`
- OAuth provider credentials when enabled
- the five S3 values listed above

Render generates `APP_SECRET_KEY` from the Blueprint. No secret value belongs in source control.

### Workers on Free Render

The single web-service process is the only possible scheduler owner because Free does not scale beyond one instance. C-09 keeps all potentially external/destructive execution disabled until explicitly exercised:

```text
RUN_MAINTENANCE_JOBS=false
RUN_REMINDER_WORKER=false
REMINDER_EMAIL_DELIVERY_ENABLED=false
JOB_URL_CHECKS_ENABLED=false
AUTO_ARCHIVE_AFTER_DAYS=0
AUTO_PURGE_AFTER_DAYS=0
```

Render Free also blocks common SMTP ports 25/465/587. A real C-10 email test therefore needs an HTTP email API or another explicitly supported delivery path. Do not claim SMTP delivery from Render Free if the provider transport cannot be reached.

## Readiness

### `/health`

Process liveness only:

```json
{"status":"ok"}
```

### `/ready`

Release/deployment readiness checks:

- PostgreSQL responds to `SELECT 1`
- the configured private storage backend is reachable
- for S3, credentials can access the configured private bucket

The response exposes only safe component states. It must never reveal a database URL, endpoint, bucket, access key, secret, filesystem path, or provider exception.

A missing/unreachable database or object store returns HTTP 503.

## Document durability verification

After the private bucket and Render secrets exist:

1. Upload a small synthetic resume through JobGrid.
2. Download it and record a local SHA-256.
3. Run:

```bash
cd backend
python scripts/c09_storage_audit.py
```

4. Confirm `status=PASS` and `capacity.backend=s3`.
5. Allow or force a Render restart/spin-down, then request the document again.
6. Run the audit again.
7. Redeploy the same candidate SHA, then repeat download and audit.
8. Confirm the file hash is unchanged after cache loss/restart/redeploy.

The test is specifically proving that Render's ephemeral `/tmp` cache is irrelevant to durable document availability.

## Backup and recovery

JobGrid has two distinct recovery layers.

### Portable account recovery

The complete portable path is the authenticated ZIP bundle:

```text
GET /crm/backup/export/bundle
POST /crm/backup/import/bundle?mode=verify_only|merge_missing
```

It contains the composed metadata graph plus verified immutable document bytes. JSON v2 remains metadata/records-only.

The S3 adapter preserves this contract. ZIP export materializes each private object through the storage adapter and verifies its size/hash. ZIP restore publishes immutable bytes through the same adapter. If the database transaction fails after a new object was published, rollback cleanup removes only objects created by that failed attempt where possible.

### Environment disaster recovery

Supabase database data and Supabase Storage objects are separate recovery concerns even though they are hosted by the same provider.

Before C-10 recovery rehearsal:

1. Produce a private logical PostgreSQL backup using an approved method.
2. Produce an S3 object inventory/copy using the Supabase S3 endpoint or another supported Storage export path.
3. Keep copies outside the public repository and outside the only environment being protected.
4. Restore into disposable staging.
5. Compare schema revision, nonempty record counts, relationships, document inventory, sizes, and SHA-256 values.

Do not treat `scripts/backup.sh` / `scripts/restore.sh` as complete cloud recovery. Those scripts cover PostgreSQL, not object bytes.

## Zero-dollar capacity monitoring

Run periodically:

```bash
cd backend
python scripts/c09_storage_audit.py
```

For S3 it reports aggregate object count/bytes and the configured zero-dollar warning threshold without printing object names.

Operational response:

- below 900 MB: normal
- approaching 900 MB: export/archive/delete deliberately before the 1 GB Supabase Free Storage limit becomes operationally risky
- never auto-upgrade a provider plan

The application-level 100 MiB per-account document quota remains an additional safeguard.

## Vercel frontend

Configure the project with:

- Root directory: `frontend`
- Framework: Vite
- Build: `npm run build`
- Output: `dist`

`frontend/vercel.json` supplies SPA fallback behavior.

`VITE_API_URL` may initially point directly at the Render HTTPS origin. If a Vercel `/api/*` reverse proxy is later configured, use `/api` and update backend CORS/OAuth configuration to match the final origin.

GitHub has recorded successful historical Vercel deployment status for this repository, but the currently connected Vercel account did not expose that JobGrid project during C-09 inspection. Record the actual active project and URL before C-10 rather than inventing one.

## OAuth

Keep OAuth credentials in Render only. Production cookies remain Secure/SameSite=None under the existing production configuration contract.

A real OAuth acceptance test requires the final HTTPS frontend/backend origins and a controlled provider test identity. Dev login never counts as OAuth evidence.

## Security rules

- Never commit database URLs, passwords, OAuth secrets, S3 credentials, SMTP/email API secrets, session cookies, private keys, user backups, or private document bytes.
- Keep `TEST_AUTH=false` in production.
- Keep the Supabase Storage bucket private.
- Do not expose S3 access keys to the frontend.
- Do not use a public object URL as authorization.
- FastAPI account ownership remains authoritative for document access.
- Keep external/destructive workers disabled unless deliberately activated for controlled acceptance.

## Rollback

Application rollback and data rollback are separate.

For application rollback:

1. Redeploy the previous known-good application SHA.
2. Keep the same PostgreSQL and private Storage configuration.
3. Verify `/ready`, login/session, reads/writes, document download, and history.

Do not delete or replace the private bucket as part of an ordinary application rollback.

## C-09 external verification checklist

- [ ] `jobgrid-documents` private bucket exists on the Supabase Free project
- [ ] S3 protocol is enabled
- [ ] server-only S3 credentials are stored in Render secrets
- [ ] Render service remains on Free
- [ ] `/ready` passes with PostgreSQL + S3
- [ ] synthetic document upload/download succeeds
- [ ] storage audit passes
- [ ] document survives Render cache loss/spin-down/restart
- [ ] document survives redeploy
- [ ] ZIP export contains exact document bytes
- [ ] recovery copy/inventory procedure is rehearsed against disposable staging
- [ ] active Vercel JobGrid URL is recorded
- [ ] RPO/RTO and private backup destination are recorded

Passing local/CI tests prepares these actions. It does not substitute for executing them against the actual free-tier providers.
