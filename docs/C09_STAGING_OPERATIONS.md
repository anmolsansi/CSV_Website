# C-09 Staging Operations Evidence

This document records repository/provider preparation for `C-09 — Prepare staging and prove durable operations` from `development.md`.

It deliberately distinguishes **repository-ready** work from **live external proof**. A local/CI pass is never converted into a staging PASS when the paid service configuration, controlled account, credential, inbox, restart, or recovery action has not actually been exercised.

## Source and ownership

- Tracking issue: #172
- Base branch: `main`
- Work branch: `c09-staging-durable-operations`
- Intake/main SHA: `cd1150384483d8296eacf5affdec56880c8ec871`
- Previous known-good application SHA at C-09 intake: `cd1150384483d8296eacf5affdec56880c8ec871` (C-08 merge)
- Candidate SHA: the exact final PR head selected for external staging, recorded in private release evidence after the branch is fixed
- Deployment owner: release operator with authorized Vercel, Render, Supabase, OAuth, and controlled-inbox access

The candidate SHA is intentionally not self-referenced in this tracked document while the branch is moving. The final PR head and deployed provider IDs belong in release evidence so a documentation-only follow-up commit cannot recursively invalidate the candidate.

## Actual provider/runtime evidence collected during C-09

### Database

Connected Supabase project evidence:

- project name: `jobgrid`
- provider: Supabase
- region: Singapore (`ap-southeast-1`)
- project status at inspection: healthy
- PostgreSQL server version: 17.6
- Alembic revision: `018`
- server-reported max connections: 60
- active connections observed during inspection: 7

No database password, connection URL, project secret, or service-role key is recorded here.

### Backend

Actual connected Render service:

- service: `jobgrid-api`
- provider/region: Render, Singapore
- public URL: `https://jobgrid-api.onrender.com`
- branch: `main`
- auto deploy: enabled
- instances: 1
- current compute plan: Free
- current health path: `/health`
- current live deploy SHA at inspection: `cd1150384483d8296eacf5affdec56880c8ec871`
- current live deploy status at inspection: live

The current service is **not C-09 durable** because it is still on Free compute with no persistent document disk. The C-09 branch changes the deployment contract to:

- Python 3.12
- one `0.5c-512mb` web-service instance
- 1 GB persistent disk mounted at `/var/data`
- `DOCUMENT_STORAGE_DIR=/var/data/jobgrid-documents`
- Render deployment readiness gate: `/ready`
- process liveness: `/health`
- external/destructive background work disabled until controlled activation

Repository changes do not authorize a paid upgrade. Because the actual service auto-deploys `main`, this branch must not be merged until the paid compute/disk change is explicitly approved.

### Frontend

Selected provider: Vercel, `frontend` project root.

**Actual JobGrid Vercel staging project/URL: BLOCKED.** The connected Vercel account inspected during C-09 did not expose a JobGrid project. Do not invent a staging URL and do not modify an unrelated Vercel project.

### Browser/dashboard access

The Opera browser connector reported that browser access was not connected during this execution. Provider facts above therefore come from the connected Render, Supabase, Vercel, and GitHub integrations rather than dashboard inference.

## Status vocabulary

- **PASS**: the exact checkpoint was demonstrated with concrete evidence.
- **REPOSITORY-READY**: code/config/runbook support exists, but live provider execution is still required.
- **BLOCKED**: a required target, billing action, credential, controlled account, or operator decision is unavailable.

## C-09 checkpoint status

### C-09.01 — providers, URLs, owner, SHAs, runtimes

**Status: REPOSITORY-READY / partially BLOCKED**

Recorded:

- Supabase project, region, server version, migration revision, and capacity observation
- actual Render service, URL, region, branch, instance count, live deploy SHA, and current plan
- previous known-good SHA and owner role
- intended Python 3.12 backend runtime

Blocked:

- actual JobGrid Vercel staging URL
- final candidate SHA until the PR head is fixed

### C-09.02 — private persistent document storage

**Status: REPOSITORY-READY / BLOCKED live durability proof**

Implemented on the branch:

- Blueprint cannot represent C-09 staging as Render Free
- 1 GB persistent disk at `/var/data`
- private document root `/var/data/jobgrid-documents`
- one backend instance
- `/ready` storage check
- read-only `backend/scripts/c09_storage_audit.py` for aggregate DB/file reconciliation and disk-capacity evidence

Blocked until paid Render provisioning:

- synthetic upload to the real persistent disk
- restart survival
- redeploy survival
- authenticated post-redeploy download/hash comparison
- confirmation of snapshots on the actual attached disk

### C-09.03 — production-mode configuration

**Status: REPOSITORY-READY / BLOCKED frontend origin and real OAuth**

Repository safeguards:

- `ENVIRONMENT=production`
- `TEST_AUTH=false`
- Render-generated `APP_SECRET_KEY`
- host-managed `DATABASE_URL`, frontend origin, CORS origin, OAuth callback base, and provider credentials
- production configuration rejects local/non-HTTPS origins and insecure secrets
- production cookies remain Secure/SameSite=None through the existing contract

Known backend origin: `https://jobgrid-api.onrender.com`.

Blocked:

- actual JobGrid frontend staging origin
- real OAuth provider configuration and controlled test identity

### C-09.04 — designated maintenance/reminder execution

**Status: REPOSITORY-READY**

The single Render backend is the designated scheduler owner. C-09 keeps external/destructive execution disabled in the Blueprint until controlled staging activation:

- `RUN_MAINTENANCE_JOBS=false`
- `RUN_REMINDER_WORKER=false`
- `REMINDER_EMAIL_DELIVERY_ENABLED=false`
- `JOB_URL_CHECKS_ENABLED=false`
- `AUTO_ARCHIVE_AFTER_DAYS=0`
- `AUTO_PURGE_AFTER_DAYS=0`

Existing restart/concurrency mechanisms were re-inspected:

- maintenance uses a PostgreSQL advisory lock in production plus a process-local lock
- reminder claims use row locking plus persisted `lease_until`
- expired sending leases recover to explicit unknown state instead of blind re-send

A real restart/reminder lifecycle remains C-10 evidence.

### C-09.05 — migrations, capacity, readiness, rollout compatibility

**Status: REPOSITORY-READY / partial live evidence**

Observed on the actual Supabase project:

- migration revision `018`
- PostgreSQL 17.6
- max connections 60
- 7 active connections at inspection

Repository rollout contract:

- one backend instance
- startup runs Alembic before routes register
- migration failure prevents successful startup
- `/ready` requires database connectivity and usable private document storage
- `/health` remains the lightweight compatibility liveness route

C-10 must still exercise deployment and previous-application compatibility against the migrated disposable database.

### C-09.06 — synthetic staging account and controlled inbox

**Status: BLOCKED**

Required before external C-09 closure:

- nonempty synthetic JobGrid staging account
- controlled OAuth test identity
- explicitly authorized controlled SMTP inbox

No production/private user data belongs in public evidence.

### C-09.07 — backup schedule, retention, restore target, RPO/RTO

**Status: REPOSITORY-READY / BLOCKED operator decisions**

Document bytes:

- current Render documentation states attached persistent disks receive automatic snapshots every 24 hours
- current Render documentation states snapshots are available for at least seven days
- disk snapshot restore is separate from application rollback and can discard newer file changes

Database:

- the connected Supabase project must have an explicit logical PostgreSQL dump before C-10 restore/rollback rehearsal
- Supabase Free does not provide the same accessible daily-backup contract as paid projects, so the project cannot rely on an assumed provider backup schedule
- logical backups must remain private and off the service being protected

Blocked operator decisions:

- agreed business RPO
- agreed business RTO
- private off-platform logical-backup destination and retention

The existing Docker Compose `scripts/backup.sh`/`scripts/restore.sh` are database-only and are not complete cloud recovery evidence. The application-level complete ZIP remains the portable account recovery path for supported records plus document bytes.

### C-09.08 — checks/alerts and induced failure

**Status: REPOSITORY-READY / BLOCKED live induction**

The cloud runbook documents checks for:

- Render service plus `/ready`
- database/storage component failure codes
- `c09_storage_audit.py` missing/corrupt-file detection and disk capacity
- maintenance health/logs
- reminder delivery history/logs
- backup/snapshot presence

A safe disposable storage-failure procedure is documented and must run only after the persistent staging service exists.

### C-09.09 — release evidence

**Status: REPOSITORY-READY**

Use the existing validator:

```bash
python scripts/smoke_jobgrid.py --self-test-release-acceptance
python scripts/smoke_jobgrid.py --release-evidence "$JOBGRID_RELEASE_EVIDENCE_FILE"
```

The real evidence file stays outside the public repository. It must contain the fixed candidate SHA and exact PASS/FAIL/BLOCKED state. Validator success with BLOCKED gates is not staging acceptance.

Current external blockers to record:

- paid Render compute plus persistent disk not yet approved/provisioned
- JobGrid Vercel staging project/URL unavailable through the connected account
- controlled OAuth credentials/test identity unavailable
- controlled SMTP inbox/authorization unavailable
- private off-platform database-backup destination plus agreed RPO/RTO unavailable

## Repository validation required before merge

- focused C-09 readiness/manifest tests
- full backend test matrix
- frontend production build
- Chromium/real-API browser suite required by repository CI
- Alembic/migration checks
- C-06 timezone matrix and C-07 release matrix where configured
- secret/diff review

## External completion procedure

After repository CI is green, C-09 becomes externally complete only when the release operator:

1. explicitly approves the paid Render compute/disk cost
2. provisions/syncs the Blueprint
3. records the actual JobGrid Vercel HTTPS origin
4. configures host secrets without copying them into GitHub
5. verifies `/ready` on the fixed candidate
6. creates the synthetic staging account and controlled external accounts
7. uploads a synthetic document and records the aggregate storage audit
8. restarts and redeploys the same candidate, reruns the audit, and verifies authenticated document download/hash
9. records database and disk recovery points
10. agrees RPO/RTO and private logical-backup destination
11. induces the documented safe readiness/storage failure and confirms it is visible
12. prepares the private release-evidence file for C-10

Until these actions are executed, the honest C-09 state is **repository-ready with external blockers**, not staging-accepted.
