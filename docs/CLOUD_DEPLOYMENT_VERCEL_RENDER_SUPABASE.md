# JobGrid Cloud Deployment: Vercel + Render + Supabase

Updated: **2026-10-03**

This runbook describes the selected zero-dollar-first deployment topology for JobGrid.

- Vercel Free: React/Vite frontend
- Render Free: FastAPI backend
- Supabase Free PostgreSQL: application database
- Supabase private Storage: durable document bytes
- Supabase Edge Function `jobgrid-storage`: private Storage gateway used by the backend

Render's local filesystem is ephemeral. Durable document bytes must never depend on it.

## Source of truth

Backend manifest:

- `render.yaml`

Frontend production routing:

- `frontend/.env.production`
- `frontend/vercel.json`

Storage gateway source and operations:

- `supabase/functions/jobgrid-storage/index.ts`
- `supabase/functions/jobgrid-storage/README.md`

Storage client and cache behavior:

- `backend/app/services/document_storage.py`
- `backend/app/__init__.py`

Operational evidence:

- `docs/C09_STAGING_OPERATIONS.md`
- `.github/workflows/c09-live-acceptance-probe.yml`
- `backend/scripts/c09_storage_audit.py`

## Production provider inventory

### Vercel

- project: `csv-website`
- project ID: `prj_oJERSKpABAhvWisTwHiuendqMNlI`
- team ID: `team_egcPPM96nH8NmGrz8zMUfPSQ`
- production origin: `https://csv-website-steel.vercel.app`
- current deployed application SHA observed for C-09: `07b8ec2fab0169b614c122b09941527dcb8da549`

### Render

- service: `jobgrid-api`
- service ID: `srv-dalu7u3l550s73ch5lu0`
- origin: `https://jobgrid-api.onrender.com`
- region: Singapore
- plan: Free
- instances: 1
- branch: `main`
- current deployed application SHA observed for C-09: `07b8ec2fab0169b614c122b09941527dcb8da549`

### Supabase

- project: `jobgrid`
- ref: `hzcycquvfkqwbqrbvnhe`
- region: Singapore (`ap-southeast-1`)
- PostgreSQL: 17.6
- observed Alembic revision: `018`
- Storage bucket: `jobgrid-documents`, private
- Edge Function: `jobgrid-storage`, version 17 during C-09 evidence collection

## Backend deployment

`render.yaml` keeps the backend on one Free instance in Singapore and uses:

```text
ENVIRONMENT=production
TEST_AUTH=false
DOCUMENT_STORAGE_BACKEND=gateway
DOCUMENT_STORAGE_GATEWAY_URL=https://hzcycquvfkqwbqrbvnhe.supabase.co/functions/v1/jobgrid-storage
DOCUMENT_STAGING_DIR=/tmp/jobgrid-document-cache
```

The start command is:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Provider liveness remains `/health`. C-09 release acceptance separately exercises `/ready`, which verifies PostgreSQL and durable private storage.

Keep these external/destructive paths disabled until a controlled staging window explicitly enables them:

```text
RUN_MAINTENANCE_JOBS=false
RUN_REMINDER_WORKER=false
REMINDER_EMAIL_DELIVERY_ENABLED=false
JOB_URL_CHECKS_ENABLED=false
AUTO_ARCHIVE_AFTER_DAYS=0
AUTO_PURGE_AFTER_DAYS=0
```

Production configuration fails closed if test auth is enabled, signing material is unsafe, production URLs are not public HTTPS, or CORS is not explicitly configured.

## Frontend deployment and API topology

The verified production Vercel project is `csv-website`, with stable production origin:

```text
https://csv-website-steel.vercel.app
```

Production builds use:

```text
VITE_API_URL=/api
```

`frontend/vercel.json` deliberately rewrites:

```text
/api/:path* -> https://jobgrid-api.onrender.com/:path*
```

The browser therefore uses same-origin JobGrid API URLs under the Vercel origin. The rewrite has Vercel rewrite caching disabled. Do not replace `/api` with a direct Render URL without re-reviewing CORS, OAuth callbacks, cookies, and release evidence.

Verified live production behavior on 2026-10-03:

- Vercel root returns HTTP 200 over HTTPS
- `https://csv-website-steel.vercel.app/api/health` returns the Render liveness contract
- `https://csv-website-steel.vercel.app/api/ready` returns database + document-storage readiness
- Vercel responses include HSTS
- direct Render CORS preflight accepts the exact Vercel production origin with credentials

## Supabase PostgreSQL

Render owns the application `DATABASE_URL` as a secret environment value. Do not commit it.

The backend automatically applies Alembic migrations for non-SQLite deployments before serving the application. Migration failure prevents successful startup.

## Durable private Storage

Bucket:

```text
jobgrid-documents
```

Required provider properties:

- private (`public=false`)
- 10 MiB per-file provider limit
- never exposed as a public document origin

JobGrid still enforces its application-level document quota separately.

### Why the gateway exists

The selected topology does **not** require Render persistent disks or separately generated Supabase S3 credentials.

FastAPI performs JobGrid authentication and ownership checks, then uses the private Supabase Edge Function gateway for object operations. The gateway holds the privileged Supabase Storage capability server-side.

Render's `/tmp/jobgrid-document-cache` is disposable cache/staging only. A cache miss downloads the durable object again through the gateway.

### Gateway authentication

Private requests include `x-jobgrid-storage-token`.

Render and Supabase derive the token independently as:

```text
sha256("jobgrid-storage-v1:" + database_password)
```

Render derives it from the password already present in `DATABASE_URL`. The Edge Function derives the expected value from server-side `SUPABASE_DB_URL`. The raw database password is never sent to the gateway.

Do not commit or log:

- database URLs/passwords
- derived gateway tokens
- Supabase service-role/secret keys
- OAuth secrets
- session cookies
- private document contents

See `supabase/functions/jobgrid-storage/README.md` for rotation and rollback.

## Gateway deployment

The checked-in Edge Function is the reproducible source of truth:

```text
supabase/functions/jobgrid-storage/index.ts
```

Deploy it to the `jobgrid` project as `jobgrid-storage` while preserving `verify_jwt=false`. That setting is intentional because the function implements its own constant-time server-to-server token check.

After deployment:

1. confirm the function is `ACTIVE`;
2. verify the private bucket is unchanged;
3. verify direct Render `/ready`;
4. verify Vercel `/api/ready`;
5. verify the fixed C-09 durability canary;
6. run an authenticated synthetic document upload/download/hash test;
7. run the storage audit.

The fixed unauthenticated canary can touch only `_ops/c09-durability-canary.txt`. It cannot name or operate on user objects.

## Readiness contracts

### `/health`

Process liveness:

```json
{"status":"ok"}
```

### `/ready`

Deployment readiness requires both:

- PostgreSQL connectivity
- configured private document storage connectivity

A healthy response exposes safe component states only. It must not include secrets, database URLs, provider exceptions, filesystem paths, or private object names.

## OAuth and cookies

OAuth provider credentials remain on Render only. `TEST_AUTH=false` is mandatory in production. Dev/test login never counts as real OAuth evidence.

The verified Google OAuth entrypoint is:

```text
https://csv-website-steel.vercel.app/api/auth/login/google
```

On 2026-10-03 it returned a Google authorization redirect whose `redirect_uri` was exactly:

```text
https://csv-website-steel.vercel.app/api/auth/callback/google
```

The OAuth state session cookie was verified to have:

- `HttpOnly`
- `Secure`
- `SameSite=None`

The reusable live probe validates these properties without logging the session-cookie value. A controlled provider identity is still required to prove full OAuth completion and authenticated return behavior.

## Live C-09 probe

`.github/workflows/c09-live-acceptance-probe.yml` checks public production/staging surfaces with bounded retries and safe assertions:

- direct Render `/health`
- direct Render `/ready`
- Vercel production root
- Vercel `/api/health`
- Vercel `/api/ready`
- exact-origin credentialed CORS preflight
- Google OAuth callback construction
- OAuth session-cookie security attributes
- Supabase fixed durability canary

Run `37120458368`, job `111195385350`, passed this expanded probe on 2026-10-03.

Render Free can cold-start after idle time. A timed-out first attempt followed by a successful bounded retry must remain visible in evidence. Do not reinterpret cold-start latency as storage corruption, and do not hide repeated failures.

## Render redeploy durability evidence

C-09 explicitly redeployed `jobgrid-api` through the Render API:

- deploy: `dep-db0dteu0tbcc73fdhh30`
- SHA: `07b8ec2fab0169b614c122b09941527dcb8da549`
- result: `live`

A replacement Render instance was observed and the post-redeploy live readiness/canary probe passed. This proves the fixed Supabase canary survives backend replacement and is not dependent on Render local cache.

It does not replace authenticated document-byte acceptance.

## Document durability acceptance

Full C-09 storage proof requires an authenticated synthetic JobGrid document, not only the fixed canary.

For the selected candidate:

1. complete a controlled OAuth login and use a synthetic/nonprivate JobGrid account;
2. upload a small synthetic document through JobGrid;
3. download it and record SHA-256;
4. run `backend/scripts/c09_storage_audit.py`;
5. force/observe loss of Render local cache or another controlled service replacement;
6. download again and confirm the same SHA-256;
7. repeat the storage audit;
8. export a complete authenticated ZIP backup;
9. verify the ZIP contains the exact document bytes/hash.

This proves durable bytes are independent of Render's ephemeral filesystem.

## Backup and disaster recovery

Portable user recovery and environment disaster recovery are different.

### Portable account recovery

The complete portable user backup is the authenticated ZIP bundle. It includes the composed metadata graph plus verified immutable document bytes obtained through the active storage adapter.

### Environment disaster recovery

A complete environment recovery package must protect both:

- PostgreSQL data
- private Supabase Storage objects

Before C-09 closes, record:

- RPO
- RTO
- backup schedule
- retention
- private off-platform destination
- operational owner

Then rehearse restore into disposable staging and compare:

- Alembic/schema revision
- nonempty record counts and relationships
- object count
- object sizes
- object SHA-256 values
- measured recovery time

The repository's database-only backup scripts are not sufficient for object recovery by themselves.

## Rollback

Code rollback must preserve durable data.

### Frontend rollback

1. promote or redeploy the previous compatible Vercel production deployment;
2. preserve the `/api` contract unless the backend/CORS/OAuth configuration is deliberately changed with it;
3. verify root, `/api/health`, `/api/ready`, and OAuth entrypoint.

### Backend rollback

1. redeploy the previous compatible backend commit;
2. keep the same PostgreSQL database and private bucket;
3. verify `/health`, `/ready`, login/session behavior, history, and document download.

### Gateway rollback

1. identify the previous known-good `supabase/functions/jobgrid-storage/index.ts` source;
2. redeploy it as a new Edge Function version with `verify_jwt=false`;
3. keep the bucket and objects unchanged;
4. verify `/ready`, durability canary, and authenticated document download.

Do not automatically downgrade the database schema to recover an application deployment.

## C-09 provider checklist

- [x] Supabase project healthy
- [x] PostgreSQL revision/capacity observed
- [x] private `jobgrid-documents` bucket exists
- [x] bucket file-size limit is 10 MiB
- [x] gateway source is versioned in the repository
- [x] gateway deployment/rotation/rollback procedure is documented
- [x] live gateway redeployed reproducibly from checked-in source
- [x] live Render `/health`, `/ready`, and fixed durability canary pass
- [x] explicit Render backend redeploy completed and canary survived replacement
- [x] active Vercel production project and URL verified
- [x] Vercel `/api` proxy to Render verified
- [x] exact-domain CORS wiring verified
- [x] production OAuth callback construction and cookie policy verified
- [ ] controlled real OAuth login completes successfully
- [ ] authenticated synthetic document upload/download/hash proof
- [ ] storage audit before/after controlled backend cache loss/replacement
- [ ] complete ZIP includes exact remote document bytes
- [ ] controlled synthetic/OAuth/email accounts ready
- [ ] RPO/RTO, backup schedule/retention/destination/owner agreed
- [ ] database + object recovery rehearsed to disposable staging
- [ ] scheduler/lease restart behavior exercised in controlled staging
- [ ] safe induced failure is operator-visible
- [ ] private release-evidence file validates for C-10 handoff

Do not mark C-09 complete until every required external item is demonstrated with concrete evidence.
