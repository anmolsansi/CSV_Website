# C-09 Staging Operations Evidence

Updated: **2026-10-03**

This document is the focused evidence record for `C-09 — Prepare staging and prove durable operations` from `development.md`. It separates demonstrated provider evidence from remaining external gates. A green local suite or repository merge is never treated as proof of an external action that was not actually exercised.

## Source and ownership

- Tracking issue: #172
- Original implementation PRs: #173 and #174, merged
- Current continuation PR: #178
- Current continuation branch: `c09-live-acceptance-probe`
- Current main baseline incorporated into the branch: `07b8ec2fab0169b614c122b09941527dcb8da549`
- Render service: `jobgrid-api` (`srv-dalu7u3l550s73ch5lu0`)
- Release operator: account owner with authorized Vercel, Render, Supabase, OAuth, and controlled-test-account access
- Infrastructure constraint: zero-dollar-first. Do not silently upgrade Vercel, Render, or Supabase to a paid plan.

## Selected topology

- Vercel Free: React/Vite frontend
- Render Free: FastAPI backend
- Supabase Free PostgreSQL: application database
- Supabase private Storage: durable document bytes
- Supabase Edge Function `jobgrid-storage`: private server-to-server Storage gateway
- Render `/tmp/jobgrid-document-cache`: disposable cache/staging only

`render.yaml` is authoritative for the backend manifest. It selects:

```text
DOCUMENT_STORAGE_BACKEND=gateway
DOCUMENT_STORAGE_GATEWAY_URL=https://hzcycquvfkqwbqrbvnhe.supabase.co/functions/v1/jobgrid-storage
DOCUMENT_STAGING_DIR=/tmp/jobgrid-document-cache
```

Paid Render disks and new S3 access keys are not prerequisites for this selected topology.

## Versioned gateway source

The deployed gateway source is now stored in this repository:

- `supabase/functions/jobgrid-storage/index.ts`
- `supabase/functions/jobgrid-storage/README.md`

The README records the deployment, authentication, database-password rotation, verification, and rollback procedure without exposing secrets.

Private gateway calls use a derived `x-jobgrid-storage-token`. Render and the Edge Function independently derive the same SHA-256 value from the current database password plus the domain separator `jobgrid-storage-v1:`. The raw database password is never sent to the gateway.

The Edge Function intentionally has platform JWT verification disabled because it implements this custom server-to-server authentication. Its only unauthenticated operation is the fixed C-09 synthetic canary. That operation can touch only `_ops/c09-durability-canary.txt` and cannot name or access user objects.

## Provider evidence collected on 2026-10-03

### Supabase database

Connected project:

- project: `jobgrid`
- project ref: `hzcycquvfkqwbqrbvnhe`
- region: Singapore (`ap-southeast-1`)
- status: `ACTIVE_HEALTHY`
- PostgreSQL: 17.6
- Alembic revision: `018`
- server-reported max connections: 60
- active connections observed during this execution: 13

No database URL, password, secret key, session, or private credential is recorded here.

### Supabase Storage

Live bucket evidence:

- bucket: `jobgrid-documents`
- `public=false`
- provider file-size limit: 10 MiB
- aggregate objects observed during the check: 1
- aggregate bytes observed during the check: 33

The one observed object is the fixed C-09 durability canary. No user document content or private object key was exposed in public evidence.

### Supabase Edge Function

`jobgrid-storage` was retrieved from the live project and its exact source was checked into the continuation branch.

During this execution the exact source was redeployed from the checked-in content:

- function status: `ACTIVE`
- version after reproducible redeploy: 17
- `verify_jwt=false`, preserving the custom-auth contract
- bundle SHA-256: `f534ab853950ff27827420a605d83cf453bcacbf7683712c18bc526eae0f718f`

The redeploy produced the same bundle hash as the previously active version 16.

### Render backend and redeploy durability

Backend origin:

```text
https://jobgrid-api.onrender.com
```

Live service configuration observed through Render:

- service: `jobgrid-api`
- service ID: `srv-dalu7u3l550s73ch5lu0`
- workspace: `Job Grid`
- plan: Free
- region: Singapore
- branch: `main`
- root directory: `backend`
- instances: 1
- auto deploy: enabled
- provider health check: `/health`

Before the explicit redeploy, the live deployment was SHA `c56cb83195ab1ac5cd691860c77cf1e85e1805dc`. The newer `main` SHA only contained documentation changes, so the backend runtime behavior was unchanged.

An explicit Render API redeploy was then executed:

- deploy ID: `dep-db0dteu0tbcc73fdhh30`
- deployed SHA: `07b8ec2fab0169b614c122b09941527dcb8da549`
- trigger: API
- started: `2026-10-03T10:53:47Z`
- status: `live`
- finished: `2026-10-03T10:55:16Z`
- new observed Render instance: `srv-dalu7u3l550s73ch5lu0-bbs2r`

This is an actual backend replacement, not only an HTTP wake-up.

The bounded live acceptance workflow at `.github/workflows/c09-live-acceptance-probe.yml` was rerun after the deploy completed. It passed at `2026-10-03T10:55:49Z` and verified:

- `/health` returns the established liveness contract
- `/ready` reports `database=ready`
- `/ready` reports `document_storage=ready`
- the Supabase durability canary reports `status=ready`
- the canary reports `state=verified`
- the canary remains exactly 33 bytes

Therefore the fixed Supabase object survived a real Render backend replacement and loss of the previous instance-local cache. This proves provider-level durable storage for the fixed canary. It does **not** substitute for the still-required authenticated JobGrid document upload/download and ZIP-byte proof.

An earlier probe on the same day observed one initial 30-second timeout before a retry succeeded. That was recorded as Render Free cold-start behavior rather than hidden. The post-redeploy verification completed without that timeout.

### Vercel frontend

GitHub's Vercel integration records the JobGrid project as:

- project name: `csv-website`
- project ID: `prj_oJERSKpABAhvWisTwHiuendqMNlI`
- team ID: `team_egcPPM96nH8NmGrz8zMUfPSQ`
- team slug: `openclawneutron-4687s-projects`
- main SHA `07b8ec2fab0169b614c122b09941527dcb8da549` has a successful Vercel deployment status

The currently connected Vercel integration can see the correct team but lists only `orderly-app`. Requests for the known JobGrid deployment return `403 forbidden`, with the connector explicitly reporting that the Vercel connection must be updated to authorize the deployment's project/team.

Therefore the active production frontend URL and actual-domain CORS/cookie/OAuth verification remain **BLOCKED on Vercel connector authorization**. Do not invent a production URL from an old preview alias.

## C-09 checkpoint status

### C-09.01 — provider inventory, URLs, owner, SHAs, runtimes

**Status: PARTIAL PASS**

Demonstrated:

- exact Render service ID, backend origin, plan, region, branch, health path, instance count and deployed SHA
- Supabase project, region, database version, migration revision, capacity observation
- Supabase Storage bucket and Edge Function
- Vercel JobGrid project/team IDs from GitHub deployment evidence
- zero-dollar topology
- gateway source and deployment procedure are versioned

Still required:

- active Vercel production frontend URL under an authorized Vercel connection
- final C-09 candidate SHA after the continuation PR passes CI and is merged/deployed

### C-09.02 — durable private document storage

**Status: PARTIAL PASS**

Demonstrated:

- durable bytes live in private Supabase Storage, not Render local storage
- live backend `/ready` can reach the configured storage gateway
- fixed durability canary created previously and remains readable today
- the canary survived an exact-source Edge Function redeploy
- the canary survived an explicit Render backend redeploy to a new instance
- bucket remains private and bounded by the 10 MiB provider upload limit

Still required for the checkpoint's full proof:

- authenticated synthetic JobGrid document upload and download with recorded SHA-256
- storage audit against that synthetic document
- repeat the authenticated document hash check after a Render restart/redeploy
- authenticated ZIP backup export proving exact remote document bytes are included

### C-09.03 — production configuration and actual domains

**Status: PARTIAL PASS**

Repository manifest keeps:

- `ENVIRONMENT=production`
- `TEST_AUTH=false`
- generated application signing secret
- private gateway storage
- external/destructive workers disabled by default

Live `/ready` proves the running backend has usable database and storage configuration.

Still required:

- verified active frontend origin
- CORS check against that origin
- cookie/HTTPS behavior from the real frontend
- OAuth callback configuration and controlled provider identity

### C-09.04 — one maintenance/reminder owner and restart behavior

**Status: REPOSITORY-READY**

Render Free is limited to one web-service instance, so the web service is the only in-process scheduler owner. External/destructive execution remains disabled by default:

```text
RUN_MAINTENANCE_JOBS=false
RUN_REMINDER_WORKER=false
REMINDER_EMAIL_DELIVERY_ENABLED=false
JOB_URL_CHECKS_ENABLED=false
AUTO_ARCHIVE_AFTER_DAYS=0
AUTO_PURGE_AFTER_DAYS=0
```

The repository already protects maintenance execution with PostgreSQL/process locking and reminder claims with persisted row locks/leases.

Still required: deliberately activate the controlled staging path and prove leases/claims across restart. That proof belongs with the real staging execution window and must not send unapproved email or URL traffic.

### C-09.05 — migrations, capacity, readiness, rollout compatibility

**Status: PARTIAL PASS**

Demonstrated:

- PostgreSQL 17.6
- Alembic revision 018
- max connections 60
- live `/ready` passes database + storage before and after an explicit backend redeploy
- one backend instance
- exact deployed backend SHA recorded
- migration startup logs observed on the replacement instance
- migration failure blocks successful startup under the existing backend contract

Still required: verify the selected frontend and backend revisions together after Vercel project authorization is restored.

### C-09.06 — synthetic staging accounts and controlled external accounts

**Status: BLOCKED**

Required before C-10:

- nonempty synthetic JobGrid account
- controlled OAuth identity
- controlled email destination/provider if delivery is exercised

Do not use production/private user data as public release evidence.

### C-09.07 — backup/recovery objectives and rehearsal

**Status: BLOCKED ON OPERATOR DECISIONS / EXTERNAL REHEARSAL**

Portable account ZIP recovery exists and includes document bytes. Environment disaster recovery still needs an explicit plan protecting both PostgreSQL and private Storage objects.

Required decisions/evidence:

- RPO
- RTO
- backup schedule
- retention
- private off-platform backup destination
- operational owner
- database + object backup
- restore into disposable staging
- measured recovery time and comparison of schema revision, record relationships/counts, object counts/sizes/hashes

The existing database-only backup scripts do not satisfy this requirement by themselves.

### C-09.08 — health, observability, and induced failure

**Status: PARTIAL PASS**

The live probe provides an operator-visible check for liveness, database readiness, durable storage readiness, and the fixed storage canary. The storage audit additionally covers document integrity/capacity without publishing object names.

Still required: execute a deliberately safe induced failure and confirm the operator can see it, then restore normal operation.

### C-09.09 — release evidence handoff

**Status: REPOSITORY-READY / BLOCKERS EXPLICIT**

The existing release validator remains the acceptance mechanism. Public evidence must contain only safe states, SHAs, run IDs, hashes, counts, deploy IDs, and blocker descriptions. Secrets and private user data stay out of the repository.

C-09 must remain open until the external items below are completed.

## Remaining external closure actions

1. Run an authenticated synthetic JobGrid document upload/download, record the SHA-256, run `backend/scripts/c09_storage_audit.py`, and repeat the hash/audit across a controlled Render restart or redeploy.
2. Export an authenticated complete ZIP and verify its document bytes match the synthetic document hash.
3. Re-authorize the Vercel connection for JobGrid project `prj_oJERSKpABAhvWisTwHiuendqMNlI` under team `team_egcPPM96nH8NmGrz8zMUfPSQ`. Record the real production frontend URL and verify HTTPS/API/CORS/cookies/OAuth callback behavior.
4. Prepare controlled synthetic/OAuth/email test accounts.
5. Agree and record RPO/RTO, backup schedule, retention, private off-platform destination, and owner. Rehearse database + object recovery into disposable staging and record measured recovery results.
6. Execute a safe induced failure and confirm the operator signal is visible.
7. Prepare the private release-evidence file and run the existing validator.

## Rollback

Application/gateway rollback must not delete or recreate durable data.

- Backend: redeploy the previous compatible application SHA, preserving PostgreSQL and the private bucket.
- Gateway: redeploy the previous known-good `supabase/functions/jobgrid-storage/index.ts` source as a new Edge Function version with the same custom-auth setting.
- Database: do not automatically downgrade schema. Verify compatibility with the previous application before rollback.
- Storage: keep the bucket and all objects unchanged during ordinary code rollback.

After any rollback, verify `/health`, `/ready`, the durability canary, authenticated document download, and application history before resuming release activity.
