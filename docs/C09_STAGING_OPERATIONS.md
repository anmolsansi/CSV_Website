# C-09 Staging Operations Evidence

This document records repository/provider preparation for `C-09 — Prepare staging and prove durable operations` from `development.md`.

It deliberately distinguishes **repository-ready** work from **live external proof**. A local/CI pass is never converted into a staging PASS when the paid service, real URL, controlled account, credential, inbox, restart, or recovery action has not actually been exercised.

## Source and ownership

- Tracking issue: #172
- Base branch: `main`
- Work branch: `c09-staging-durable-operations`
- Intake/main SHA: `cd1150384483d8296eacf5affdec56880c8ec871`
- Previous known-good application SHA at C-09 intake: `cd1150384483d8296eacf5affdec56880c8ec871` (C-08 merge)
- Candidate SHA: use the exact final PR head selected for external staging; record it in the private release evidence before provisioning/testing
- Deployment owner: release operator with authorized Vercel, Render, Supabase, OAuth, and controlled-inbox access

The candidate SHA is intentionally not hard-coded into this tracked document while the implementation branch is still moving. The final PR head and deployed provider IDs belong in the release evidence so a documentation-only follow-up commit does not recursively invalidate the recorded candidate.

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

Selected provider: Render, Singapore.

Repository contract after C-09:

- Python 3.12
- one `0.5c-512mb` web-service instance
- 1 GB persistent disk mounted at `/var/data`
- `DOCUMENT_STORAGE_DIR=/var/data/jobgrid-documents`
- Render readiness gate: `/ready`
- process liveness: `/health`
- external/destructive background work disabled until controlled activation

**Live Render service URL/status: BLOCKED.** The paid persistent-disk service is not provisioned through the currently connected tools. Repository changes do not authorize a paid upgrade.

### Frontend

Selected provider: Vercel, `frontend` project root.

**Actual JobGrid Vercel staging project/URL: BLOCKED.** The connected Vercel account inspected during C-09 does not currently expose a JobGrid project. Do not invent a staging URL.

### Browser/dashboard access

Browser automation was unavailable during this execution because the browser connector was not connected. This is not treated as evidence that the provider dashboards do or do not contain additional services.

## Checkpoint status

Status vocabulary for this document:

- **PASS** — the exact checkpoint was actually demonstrated with concrete evidence.
- **REPOSITORY-READY** — code/config/runbook support is implemented and tested, but the live provider action remains to be run.
- **BLOCKED** — a required external target, billing action, credential, controlled account, or operator decision is not available.

### C-09.01 — actual providers, URLs, owner, SHAs, runtimes

**Status: REPOSITORY-READY / BLOCKED live URLs**

Recorded:

- selected topology and owner role;
- intake/previous SHA;
- Supabase project/region/runtime/revision/capacity;
- intended Render and Vercel providers;
- Python 3.12 backend runtime.

Blocked:

- actual JobGrid Vercel staging URL;
- actual paid Render backend URL/service ID;
- final candidate SHA until the PR head is fixed.

### C-09.02 — private persistent document storage

**Status: REPOSITORY-READY / BLOCKED live durability proof**

Implemented:

- Blueprint can no longer represent C-09 staging as Render Free;
- 1 GB disk at `/var/data`;
- private document root `/var/data/jobgrid-documents`;
- one backend instance;
- `/ready` storage check;
- read-only `backend/scripts/c09_storage_audit.py` for aggregate DB/file reconciliation and disk capacity evidence.

Blocked until paid Render provisioning:

- synthetic upload on the actual disk;
- restart survival;
- redeploy survival;
- authenticated post-redeploy download/hash comparison;
- provider disk snapshot availability on the actual service.

### C-09.03 — production-mode configuration

**Status: REPOSITORY-READY / BLOCKED actual domains and provider credentials**

Repository safeguards:

- `ENVIRONMENT=production`;
- `TEST_AUTH=false`;
- Render-generated `APP_SECRET_KEY`;
- host-managed `DATABASE_URL`, frontend origin, CORS origin, OAuth callback base and provider credentials;
- production configuration already rejects local/non-HTTPS origin settings and insecure secrets;
- production cookies remain Secure/SameSite=None through the existing contract.

Blocked:

- actual frontend/backend staging origins;
- real OAuth provider configuration/test account.

### C-09.04 — designated maintenance/reminder execution

**Status: REPOSITORY-READY**

The single Render backend is the designated scheduler owner. C-09 keeps all potentially external/destructive jobs disabled in the Blueprint:

- `RUN_MAINTENANCE_JOBS=false`
- `RUN_REMINDER_WORKER=false`
- `REMINDER_EMAIL_DELIVERY_ENABLED=false`
- `JOB_URL_CHECKS_ENABLED=false`
- `AUTO_ARCHIVE_AFTER_DAYS=0`
- `AUTO_PURGE_AFTER_DAYS=0`

Existing durability/concurrency mechanisms were re-inspected:

- maintenance uses a PostgreSQL advisory lock in production plus a process-local lock;
- reminder claims use row locking plus persisted `lease_until` values;
- expired sending leases are recovered to an explicit unknown state instead of being blindly re-sent.

A real restart/delivery lifecycle remains C-10 evidence.

### C-09.05 — migrations, capacity, readiness, rollout compatibility

**Status: REPOSITORY-READY / partial live evidence**

Observed on actual Supabase project:

- migration revision `018`;
- PostgreSQL 17.6;
- max connections 60;
- 7 active at inspection.

Repository rollout contract:

- one backend instance;
- startup runs Alembic before routes are registered;
- migration failure prevents successful startup;
- `/ready` requires live DB connectivity and usable private document storage;
- `/health` remains the lightweight compatibility liveness route.

C-10 still must exercise candidate rollout and immediately previous application compatibility against the migrated disposable database.

### C-09.06 — synthetic staging accounts and controlled inbox

**Status: BLOCKED**

Required before external C-09 closure:

- nonempty synthetic JobGrid staging account;
- controlled OAuth test identity;
- explicitly authorized controlled SMTP inbox.

No production/private user data may be copied into public evidence.

### C-09.07 — backup schedule, retention, restore target, RPO/RTO

**Status: REPOSITORY-READY / BLOCKED operator decisions**

Document bytes:

- Render persistent disks currently receive automatic snapshots every 24 hours;
- current Render documentation states snapshots are available for at least seven days;
- disk snapshot restore is separate from application rollback and can discard changes newer than the snapshot.

Database:

- create a logical PostgreSQL dump before the C-10 restore/rollback rehearsal in addition to provider backup capability;
- never store private database backups in this public repository or public artifacts.

Blocked operator decisions:

- agreed business RPO;
- agreed business RTO;
- private off-platform logical-backup destination and retention.

The old Docker Compose `scripts/backup.sh`/`scripts/restore.sh` are explicitly database-only and are not complete cloud recovery evidence.

### C-09.08 — alerts/documented checks and induced failure

**Status: REPOSITORY-READY / BLOCKED live induction**

Documented in the cloud runbook:

- Render service + `/ready` for API health;
- `/ready` component codes for database/storage;
- `c09_storage_audit.py` for missing/corrupt file detection and disk free space;
- maintenance health/log checks;
- reminder delivery history/log checks;
- provider backup/snapshot checks.

A safe disposable-storage failure procedure is documented. It must be executed only after the staging service exists.

### C-09.09 — release evidence

**Status: REPOSITORY-READY**

Use the existing validator:

```bash
python scripts/smoke_jobgrid.py --self-test-release-acceptance
python scripts/smoke_jobgrid.py --release-evidence "$JOBGRID_RELEASE_EVIDENCE_FILE"
```

The real evidence file remains outside the repository. It must contain the fixed candidate SHA and exact PASS/FAIL/BLOCKED state. Validator success with BLOCKED gates is not staging acceptance.

Current external blockers to record:

- paid Render service/disk not yet provisioned and approved;
- actual Render staging URL unavailable;
- actual JobGrid Vercel staging project/URL unavailable through the connected account;
- controlled OAuth credentials/test identity unavailable;
- controlled SMTP inbox/authorization unavailable;
- private off-platform database-backup destination and agreed RPO/RTO unavailable.

## Repository validation required before merge

- focused C-09 readiness/manifest tests;
- full backend test matrix;
- frontend production build;
- Chromium/real-API browser suite required by repository CI;
- Alembic/migration checks;
- C-06 browser timezone matrix and C-07 release matrix where configured as required workflows;
- secret/diff review.

## External completion procedure

After the repository PR is green, C-09 can become externally complete only when the release operator:

1. explicitly approves the Render paid compute/disk cost;
2. provisions/syncs the Blueprint;
3. records actual Render/Vercel HTTPS URLs;
4. configures host secret values without copying them into GitHub;
5. verifies `/ready` on the fixed candidate;
6. creates the synthetic staging account and controlled external accounts;
7. uploads a synthetic document and records the aggregate storage audit;
8. restarts and redeploys the same candidate, reruns the audit, and verifies authenticated document download/hash;
9. records database and disk recovery points;
10. agrees RPO/RTO and private logical-backup destination;
11. induces the documented safe readiness/storage failure and confirms it is visible;
12. prepares the private release-evidence file for C-10.

Until those actions are actually executed, the honest C-09 state is **repository-ready with external blockers**, not staging-accepted.
