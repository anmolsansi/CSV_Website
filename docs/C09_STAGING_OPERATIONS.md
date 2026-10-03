# C-09 Staging Operations Evidence

Updated: **2026-10-03**

This document is the focused evidence record for `C-09 — Prepare staging and prove durable operations` from `development.md`. It separates demonstrated provider evidence from remaining external gates. A green local suite or repository merge is never treated as proof of an external action that was not actually exercised.

## Source and ownership

- Tracking issue: #172
- Original implementation PRs: #173 and #174, merged
- Current continuation PR: #178
- Current continuation branch: `c09-live-acceptance-probe`
- Current deployed application baseline: `07b8ec2fab0169b614c122b09941527dcb8da549`
- Render service: `jobgrid-api` (`srv-dalu7u3l550s73ch5lu0`)
- Vercel project: `csv-website` (`prj_oJERSKpABAhvWisTwHiuendqMNlI`)
- Supabase project: `jobgrid` (`hzcycquvfkqwbqrbvnhe`)
- Release operator: account owner with authorized Vercel, Render, Supabase, OAuth, and controlled-test-account access
- Infrastructure constraint: zero-dollar-first. Do not silently upgrade Vercel, Render, or Supabase to a paid plan.

## Selected topology

- Vercel Free: React/Vite frontend
- Vercel same-origin `/api/*` rewrite: forwards browser API traffic to Render
- Render Free: FastAPI backend
- Supabase Free PostgreSQL: application database
- Supabase private Storage: durable document bytes
- Supabase Edge Function `jobgrid-storage`: private server-to-server Storage gateway
- Render `/tmp/jobgrid-document-cache`: disposable cache/staging only

`render.yaml` is authoritative for the backend manifest. `frontend/vercel.json` is authoritative for the production frontend proxy. Production frontend builds use `VITE_API_URL=/api`.

## Versioned gateway source

The deployed gateway source is stored in this repository:

- `supabase/functions/jobgrid-storage/index.ts`
- `supabase/functions/jobgrid-storage/README.md`

The README records deployment, authentication, database-password rotation, verification, and rollback without exposing secrets.

Private gateway calls use a derived `x-jobgrid-storage-token`. Render and the Edge Function independently derive the same SHA-256 value from the current database password plus the domain separator `jobgrid-storage-v1:`. The raw database password is never sent to the gateway.

The Edge Function intentionally has platform JWT verification disabled because it implements this custom server-to-server authentication. Its only unauthenticated operation is the fixed C-09 synthetic canary. That operation can touch only `_ops/c09-durability-canary.txt` and cannot name or access user objects.

## Provider evidence collected on 2026-10-03

### Supabase database

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

- bucket: `jobgrid-documents`
- `public=false`
- provider file-size limit: 10 MiB
- aggregate objects observed during the check: 1
- aggregate bytes observed during the check: 33

The one observed object is the fixed C-09 durability canary. No user document content or private object key was exposed in public evidence.

### Supabase Edge Function

`jobgrid-storage` was retrieved from the live project and its exact source was checked into the continuation branch. The exact checked-in source was then redeployed:

- function status: `ACTIVE`
- version: 17
- `verify_jwt=false`, preserving the custom-auth contract
- bundle SHA-256: `f534ab853950ff27827420a605d83cf453bcacbf7683712c18bc526eae0f718f`

The redeploy produced the same bundle hash as the previously active version 16.

### Render backend and redeploy durability

Backend origin:

```text
https://jobgrid-api.onrender.com
```

Observed live service configuration:

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

An explicit Render API redeploy was executed:

- deploy ID: `dep-db0dteu0tbcc73fdhh30`
- deployed SHA: `07b8ec2fab0169b614c122b09941527dcb8da549`
- trigger: API
- started: `2026-10-03T10:53:47Z`
- finished: `2026-10-03T10:55:16Z`
- status: `live`
- replacement instance observed: `srv-dalu7u3l550s73ch5lu0-bbs2r`

This was an actual backend replacement, not only an HTTP wake-up. The post-redeploy live probe passed and verified `/health`, `/ready`, `database=ready`, `document_storage=ready`, and the same 33-byte canary with `state=verified`.

Therefore the fixed Supabase object survived a real Render backend replacement and loss of the previous instance-local cache. This proves provider-level durable storage for the fixed canary. It does **not** substitute for the still-required authenticated JobGrid document upload/download and ZIP-byte proof.

An earlier probe on the same day observed one initial 30-second timeout before a retry succeeded. That remains recorded as Render Free cold-start behavior rather than hidden.

### Vercel frontend and actual-domain wiring

The Vercel connection was re-authorized and the JobGrid project is now directly visible:

- project: `csv-website`
- project ID: `prj_oJERSKpABAhvWisTwHiuendqMNlI`
- team ID: `team_egcPPM96nH8NmGrz8zMUfPSQ`
- team slug: `openclawneutron-4687s-projects`
- production deployment ID: `dpl_4wgjX5mFE2JLQZ5vTtUAMwPe1zFo`
- deployment status: `READY`
- branch: `main`
- deployed SHA: `07b8ec2fab0169b614c122b09941527dcb8da549`
- production origin: `https://csv-website-steel.vercel.app`

The deployed frontend uses `VITE_API_URL=/api`. `frontend/vercel.json` rewrites `/api/:path*` to `https://jobgrid-api.onrender.com/:path*` and disables rewrite caching for API traffic.

Direct production checks succeeded:

- `https://csv-website-steel.vercel.app/` returns HTTP 200 over HTTPS
- `/api/health` returns the Render liveness contract
- `/api/ready` returns the same database + document-storage readiness contract as direct Render
- Vercel responses include HSTS

The live probe was expanded and run as GitHub Actions run `37120458368`, job `111195385350`. It passed at `2026-10-03T11:41:32Z` and additionally proved:

- a direct CORS preflight from `https://csv-website-steel.vercel.app` to Render is accepted with that exact `Access-Control-Allow-Origin`
- credentialed CORS is enabled
- `/api/auth/login/google` returns a Google OAuth redirect
- the generated callback is exactly `https://csv-website-steel.vercel.app/api/auth/callback/google`
- the OAuth session cookie is `HttpOnly`, `Secure`, and `SameSite=None`

The workflow intentionally does not print or persist the session cookie value.

## C-09 checkpoint status

### C-09.01 — provider inventory, URLs, owner, SHAs, runtimes

**Status: PASS for deployed provider inventory**

Demonstrated:

- exact Vercel project/team/deployment IDs, production origin, branch and deployed SHA
- exact Render service/deploy IDs, backend origin, plan, region, branch, health path, instance count and deployed SHA
- Supabase project, region, database version, migration revision, capacity observation, private bucket and Edge Function version/hash
- frontend and backend both run application SHA `07b8ec2fab0169b614c122b09941527dcb8da549`
- zero-dollar topology and operator ownership are explicit

PR #178 still carries the release evidence/workflow/source-tracking changes and must pass its own CI before merge, but that is not a missing provider identity.

### C-09.02 — durable private document storage

**Status: PARTIAL PASS**

Demonstrated:

- durable bytes live in private Supabase Storage, not Render local storage
- live backend `/ready` can reach the configured storage gateway
- fixed canary remains readable
- canary survived an exact-source Edge Function redeploy
- canary survived an explicit Render backend redeploy to a replacement instance
- bucket remains private and bounded by the 10 MiB provider upload limit

Still required:

- authenticated synthetic JobGrid document upload and download with recorded SHA-256
- storage audit against that synthetic document
- repeat the authenticated document hash/audit after controlled backend replacement/cache loss
- authenticated ZIP backup proving exact remote document bytes are included

### C-09.03 — production configuration and actual domains

**Status: PARTIAL PASS — infrastructure wiring proven; real account completion pending**

Demonstrated:

- production frontend origin is verified and HTTPS-only
- production frontend uses same-origin `/api`
- Vercel→Render proxy returns live health/readiness
- direct CORS accepts the exact Vercel production origin with credentials
- production startup is running with `TEST_AUTH=false`
- Google OAuth entrypoint generates the exact production callback URL
- session cookie flags are `HttpOnly`, `Secure`, `SameSite=None`

Still required:

- complete one real OAuth login with a controlled provider identity and verify authenticated return/session behavior

### C-09.04 — one maintenance/reminder owner and restart behavior

**Status: REPOSITORY-READY**

Render Free has one web-service instance, so the web service is the only in-process scheduler owner. External/destructive execution remains disabled by default:

```text
RUN_MAINTENANCE_JOBS=false
RUN_REMINDER_WORKER=false
REMINDER_EMAIL_DELIVERY_ENABLED=false
JOB_URL_CHECKS_ENABLED=false
AUTO_ARCHIVE_AFTER_DAYS=0
AUTO_PURGE_AFTER_DAYS=0
```

The repository protects maintenance execution with PostgreSQL/process locking and reminder claims with persisted row locks/leases.

Still required: deliberately activate the controlled staging path and prove leases/claims across restart without sending unapproved email or URL traffic.

### C-09.05 — migrations, capacity, readiness, rollout compatibility

**Status: PASS for current deployed application pair**

Demonstrated:

- PostgreSQL 17.6
- Alembic revision 018
- max connections 60
- one backend instance
- migration startup observed on the replacement Render instance
- migration failure blocks successful production startup under the existing backend contract
- Vercel frontend and Render backend are both deployed from SHA `07b8ec2fab0169b614c122b09941527dcb8da549`
- frontend `/api/ready` and direct backend `/ready` both report database + document storage ready

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

The live probe now checks Render liveness/readiness, Vercel production availability, Vercel→Render proxying, CORS, OAuth callback construction/cookie policy, and the Supabase storage canary.

Still required: execute a deliberately safe induced failure and confirm the operator signal is visible, then restore normal operation.

### C-09.09 — release evidence handoff

**Status: REPOSITORY-READY / BLOCKERS EXPLICIT**

The release validator remains the acceptance mechanism. Public evidence must contain only safe states, SHAs, run IDs, hashes, counts, deploy IDs, and blocker descriptions. Secrets and private user data stay out of the repository.

C-09 remains open until the external items below are completed.

## Remaining external closure actions

1. Complete a real OAuth login using a controlled provider identity and create/use a nonempty synthetic JobGrid account.
2. Upload a synthetic JobGrid document, download it, record SHA-256, run `backend/scripts/c09_storage_audit.py`, and repeat the hash/audit across controlled backend replacement/cache loss.
3. Export an authenticated complete ZIP and verify its document bytes match the synthetic document hash.
4. Prepare a controlled email destination/provider if delivery is exercised.
5. Agree and record RPO/RTO, backup schedule, retention, private off-platform destination, and owner. Rehearse database + object recovery into disposable staging and record measured recovery results.
6. Deliberately exercise the scheduler/lease restart path in the controlled staging window without enabling unapproved external traffic.
7. Execute a safe induced failure and confirm the operator signal is visible, then restore service.
8. Prepare the private release-evidence file and run the existing validator.

## Rollback

Application/gateway rollback must not delete or recreate durable data.

- Backend: redeploy the previous compatible application SHA, preserving PostgreSQL and the private bucket.
- Frontend: promote/redeploy the previous compatible Vercel production deployment while keeping the `/api` contract compatible with the backend.
- Gateway: redeploy the previous known-good `supabase/functions/jobgrid-storage/index.ts` source as a new Edge Function version with the same custom-auth setting.
- Database: do not automatically downgrade schema. Verify compatibility with the previous application before rollback.
- Storage: keep the bucket and all objects unchanged during ordinary code rollback.

After any rollback, verify the Vercel root, `/api/health`, `/api/ready`, direct Render `/ready`, the durability canary, OAuth entrypoint/cookie policy, authenticated document download, and application history before resuming release activity.
