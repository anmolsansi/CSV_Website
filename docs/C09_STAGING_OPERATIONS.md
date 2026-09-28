# C-09 Staging Operations Evidence

This document records repository/provider preparation for `C-09 — Prepare staging and prove durable operations` from `development.md`.

It deliberately distinguishes **repository-ready** work from **live external proof**. A local/CI pass is never converted into a staging PASS when a real provider target, credential, restart, recovery action, controlled account, or operator decision has not actually been exercised.

## Source and ownership

- Tracking issue: #172
- Pull request: #173
- Base branch: `main`
- Work branch: `c09-staging-durable-operations`
- Intake / previous known-good SHA: `cd1150384483d8296eacf5affdec56880c8ec871`
- Candidate SHA: record the exact final PR head in private release evidence after the branch is fixed
- Deployment owner: release operator with authorized Vercel, Render, Supabase, OAuth, and controlled-inbox access

## User-selected infrastructure constraint

C-09 must use **zero-dollar infrastructure**. Paid Render compute and persistent disks are explicitly out of scope unless the user makes a future separate billing decision.

The selected topology is:

- Vercel Free for the React/Vite frontend
- Render Free for the FastAPI backend
- Supabase Free PostgreSQL for application data
- private Supabase Storage for durable document bytes

Render Free local storage is ephemeral, so durable application bytes must never depend on it. `/tmp/jobgrid-document-cache` is transient staging/cache only.

## Actual provider/runtime evidence collected during C-09

### Database

Connected Supabase project:

- project: `jobgrid`
- region: Singapore (`ap-southeast-1`)
- project status at inspection: healthy
- PostgreSQL: 17.6
- Alembic revision: `018`
- server-reported max connections: 60
- active connections observed during inspection: 7

No database password, connection URL, access key, secret, or service-role credential is recorded here.

### Backend

Actual connected Render service:

- service: `jobgrid-api`
- region: Singapore
- URL: `https://jobgrid-api.onrender.com`
- branch: `main`
- auto deploy: enabled
- instances: 1
- plan: Free
- live deploy SHA at inspection: `cd1150384483d8296eacf5affdec56880c8ec871`

C-09 intentionally keeps that service on Free.

Repository contract after the zero-dollar pivot:

- Python 3.12
- `plan: free`
- one instance
- `/health` process liveness
- `/ready` database + private-object-storage readiness
- `DOCUMENT_STORAGE_BACKEND=s3`
- private bucket name `jobgrid-documents`
- Render local `/tmp/jobgrid-document-cache` used only as disposable cache/staging
- external/destructive workers disabled until controlled activation

### Object storage

Selected provider: Supabase Storage on the existing Free project.

Live action completed during C-09:

- private bucket `jobgrid-documents` created on the existing `jobgrid` project
- bucket `public=false`
- bucket file-size limit set to 10 MiB, matching JobGrid's application upload limit
- no paid project, branch, disk, or storage resource was created

Supabase Free currently includes 1 GB of Storage. JobGrid preserves its 100 MiB per-account document quota and the C-09 storage audit reports an early warning at 900 MB aggregate object usage.

The production adapter uses Supabase's S3-compatible endpoint. Required server-only inputs are:

- S3 endpoint
- region
- bucket
- access-key ID
- secret access key

Generated Supabase S3 access keys have broad bucket access and bypass RLS. They must remain in Render secrets and never appear in the frontend, repository, logs, screenshots, or public evidence.

The current connected Supabase integration does not expose S3 access-key generation, so that credential-generation step remains an explicit dashboard/operator action.

### Frontend

GitHub contains successful historical Vercel deployment status for this repository, but the currently connected Vercel account did not expose the JobGrid project during C-09 inspection. The active JobGrid frontend project/URL remains an external evidence item rather than an invented value.

## Status vocabulary

- **PASS**: the exact checkpoint was demonstrated with concrete evidence.
- **REPOSITORY-READY**: code/config/runbook support exists, but live provider execution remains.
- **BLOCKED**: a required target, credential, controlled account, or operator decision is unavailable.

## C-09 checkpoint status

### C-09.01 — providers, URLs, owner, SHAs, runtimes

**Status: REPOSITORY-READY / partially BLOCKED**

Recorded:

- actual Supabase project/runtime/database revision/capacity observation
- actual Render service/URL/region/plan/instance count/live SHA
- previous known-good SHA
- Python 3.12 backend runtime
- zero-dollar topology decision

Blocked:

- actual active JobGrid Vercel frontend URL
- final candidate SHA until the branch is fixed

### C-09.02 — durable private document storage

**Status: REPOSITORY-READY / partial live provider proof**

Implemented on the branch:

- Render remains Free
- no Render persistent disk
- filesystem/S3 storage abstraction in `backend/app/services/document_storage.py`
- production Blueprint selects S3-compatible private storage
- existing opaque document `storage_key` contract is preserved
- existing document upload/download/list/link/delete behavior continues through the adapter
- ZIP backup export/restore remains compatible because its storage calls resolve through the same adapter
- local filesystem remains supported for development/tests
- S3 cache loss is covered by regression tests
- `/ready` checks the active private-storage backend
- `c09_storage_audit.py` verifies ready-document size/hash integrity and aggregate capacity without exposing object names

Live proof completed:

- private Supabase bucket exists and is non-public
- 10 MiB provider-side file-size limit is configured

Blocked until server-only S3 credentials are generated/configured:

- real S3 readiness on Render
- real upload/download against the bucket
- Render spin-down/restart/redeploy durability proof
- real ZIP export using remote document bytes

### C-09.03 — production-mode configuration

**Status: REPOSITORY-READY / BLOCKED final storage/frontend/OAuth secrets**

Repository safeguards:

- `ENVIRONMENT=production`
- `TEST_AUTH=false`
- Render-generated `APP_SECRET_KEY`
- database/frontend/CORS/OAuth values remain provider-managed
- S3 endpoint/region/access credentials remain provider-managed secrets
- bucket stays private
- S3 credentials are server-only
- production cookies remain Secure/SameSite=None through the existing contract

Known backend origin:

```text
https://jobgrid-api.onrender.com
```

Blocked:

- generated S3 access-key pair and exact endpoint entered into Render secrets
- active JobGrid frontend origin
- real OAuth provider configuration/test identity

### C-09.04 — maintenance/reminder execution

**Status: REPOSITORY-READY**

Render Free cannot scale beyond one instance, so the web service is the only possible scheduler owner.

C-09 keeps execution disabled until deliberate staging activation:

- `RUN_MAINTENANCE_JOBS=false`
- `RUN_REMINDER_WORKER=false`
- `REMINDER_EMAIL_DELIVERY_ENABLED=false`
- `JOB_URL_CHECKS_ENABLED=false`
- `AUTO_ARCHIVE_AFTER_DAYS=0`
- `AUTO_PURGE_AFTER_DAYS=0`

Existing concurrency/restart protections remain:

- maintenance uses a PostgreSQL advisory lock plus process-local lock
- reminder claims use row locking and persisted leases
- expired sending leases recover to explicit unknown state instead of blind resend

Render Free blocks common SMTP ports 25/465/587, so C-10 email acceptance must use a supported HTTP email API or another explicitly supported transport if email delivery is required from Render Free.

### C-09.05 — migrations, capacity, readiness, rollout compatibility

**Status: REPOSITORY-READY / partial live evidence**

Observed on Supabase:

- Alembic revision `018`
- PostgreSQL 17.6
- max connections 60
- 7 active connections at inspection

Repository rollout contract:

- one backend instance
- Alembic executes before routes register
- migration failure prevents successful startup
- `/ready` requires database connectivity and private storage availability
- `/health` remains lightweight liveness
- remote object bytes survive loss of Render's local cache by design

C-10 must still exercise the actual deployed candidate and prior compatible application build.

### C-09.06 — synthetic staging account and controlled external accounts

**Status: BLOCKED**

Required before external acceptance:

- nonempty synthetic JobGrid account
- controlled OAuth test identity
- controlled email destination/provider if email is tested

No production/private user data belongs in public evidence.

### C-09.07 — backup/recovery objectives

**Status: REPOSITORY-READY / BLOCKED operator decisions and rehearsal**

Portable account recovery already has a complete ZIP path with document bytes.

Environment disaster recovery must protect both:

- PostgreSQL data
- Supabase Storage objects

The existing Docker Compose `scripts/backup.sh` / `scripts/restore.sh` are database-only and do not protect object bytes.

Before C-10 recovery rehearsal:

1. take a private logical PostgreSQL backup
2. copy/inventory the private Storage bucket through the S3 protocol or another supported Storage export path
3. restore to disposable staging
4. compare schema revision, record counts, relationships, object counts, sizes, and hashes

Blocked operator decisions:

- RPO
- RTO
- private off-platform backup destination
- retention policy

### C-09.08 — health/observability and induced failure

**Status: REPOSITORY-READY / BLOCKED live induction**

Runbook checks cover:

- Render service + `/ready`
- database/storage readiness component codes
- document size/hash integrity
- aggregate Supabase Storage consumption vs free-tier headroom
- worker logs/maintenance health
- reminder delivery history/logs
- backup/recovery evidence

A safe induced-failure procedure must be executed only after the real S3 credentials are configured.

### C-09.09 — release evidence

**Status: REPOSITORY-READY**

Use the existing release validator:

```bash
python scripts/smoke_jobgrid.py --self-test-release-acceptance
python scripts/smoke_jobgrid.py --release-evidence "$JOBGRID_RELEASE_EVIDENCE_FILE"
```

The real evidence file remains private. Validator success with BLOCKED gates never means staging accepted.

## Zero-dollar constraints to keep visible

This architecture has operational limits:

- Render Free can cold-start after idle spin-down.
- Render Free local files are disposable.
- Render Free has free-instance, build, and outbound-bandwidth quotas.
- Supabase Free has database, Storage, egress, and other plan quotas.
- Supabase Storage S3 credentials are high-privilege server credentials.
- S3 object versioning is not provided by Supabase Storage, so deletion/recovery planning matters.

The correct response to a free-tier limit is to reduce/archive usage or explicitly revisit architecture. Do not silently enable a paid plan.

## Repository validation required before merge

The final fixed candidate must pass:

- focused zero-dollar C-09 readiness/manifest tests
- S3 adapter/cache-loss tests
- document/backup recovery regressions
- full backend test matrix
- frontend production build
- Chromium/real-API browser suite
- Alembic/migration checks
- C-06 browser-timezone matrix
- C-07 SQLite release matrix
- secret/diff review

## External completion procedure

After repository CI is green, C-09 becomes externally complete only when the release operator:

1. generates the Supabase server-only S3 access-key pair and records the exact endpoint/region privately
2. sets those values in Render secrets without exposing them
3. syncs/deploys `jobgrid-api` while keeping `plan: free`
4. verifies `/ready`
5. uploads and downloads a synthetic document and records its SHA-256
6. runs `c09_storage_audit.py`
7. loses the Render local cache through restart/spin-down and proves the document remains downloadable
8. redeploys the same candidate and repeats the proof
9. exports a complete ZIP and verifies the remote document bytes are included
10. records the real Vercel frontend origin
11. agrees RPO/RTO and private backup destination/retention
12. rehearses database + object recovery against disposable staging
13. prepares the private release-evidence file for C-10

Until those actions are executed, the honest C-09 state is **repository-ready with external provider actions remaining**, not staging-accepted.
