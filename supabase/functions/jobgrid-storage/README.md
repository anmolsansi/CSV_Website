# JobGrid private storage gateway

This directory is the source of truth for the deployed Supabase Edge Function named `jobgrid-storage`.

## Purpose

Render Free has an ephemeral filesystem. JobGrid therefore stores durable document bytes in the private Supabase Storage bucket `jobgrid-documents` and reaches it through this server-only Edge Function gateway.

The browser never calls the private document operations directly. FastAPI remains responsible for JobGrid authentication, authorization, ownership checks, metadata, and document API contracts.

## Authentication contract

Private gateway operations require the `x-jobgrid-storage-token` header.

The token is derived independently on both sides as:

```text
sha256("jobgrid-storage-v1:" + database_password)
```

- Render derives it at backend startup from the password in `DATABASE_URL` when `DOCUMENT_STORAGE_BACKEND=gateway` and no explicit gateway token is set.
- The Edge Function derives the expected value from the password in its server-side `SUPABASE_DB_URL`.
- The raw database password is never sent between Render and Supabase.
- Do not commit or log either the database URL/password or the derived token.

`verify_jwt` is intentionally disabled for this function because private operations use the custom constant-time token check above. The only unauthenticated operation is `GET ?action=c09-canary`, which can read/create exactly one fixed synthetic object: `_ops/c09-durability-canary.txt`. It cannot name or access user objects.

## Deployment

Project: `jobgrid` (`hzcycquvfkqwbqrbvnhe`)

Function: `jobgrid-storage`

Entrypoint: `supabase/functions/jobgrid-storage/index.ts`

Deploy the checked-in source as one function version. With an authenticated Supabase CLI, discover the exact current command first with `supabase functions deploy --help`, then deploy `jobgrid-storage` with JWT verification disabled to preserve the custom-auth contract. With the connected Supabase tool, deploy the file in this directory with `verify_jwt=false`.

Do not add S3 access keys, service-role keys, database URLs, passwords, or derived gateway tokens to this repository.

## Post-deploy verification

1. Confirm the function is `ACTIVE` and note its version privately.
2. Confirm the `jobgrid-documents` bucket is private and retains the 10 MiB per-file limit.
3. Run the live C-09 probe. It must verify:
   - `https://jobgrid-api.onrender.com/health` returns `{"status":"ok"}`.
   - `https://jobgrid-api.onrender.com/ready` reports both `database` and `document_storage` as `ready`.
   - the C-09 durability canary reports `status=ready`, `state=created|verified`, and `size_bytes=33`.
4. Run the storage audit and an authenticated synthetic document upload/download/hash check before release acceptance.

A Render Free cold start may exceed a single 30-second request. The live probe uses bounded retries so a successful retry is recorded without hiding the cold-start event.

## Database password rotation

The gateway token changes whenever the database password changes.

1. Rotate the Supabase database password using the normal provider procedure.
2. Update Render `DATABASE_URL` to the new connection string before treating the rollout as healthy.
3. Redeploy/restart `jobgrid-api` so it derives the new gateway token.
4. Confirm the Edge Function sees the matching current `SUPABASE_DB_URL` value.
5. Verify `/ready` and the durability canary.
6. If `/ready` reports document storage unavailable, stop release activity and reconcile the two database-password sources. Never work around a mismatch by publishing the bucket or weakening gateway authentication.

## Rollback

Gateway rollback is code rollback, not data rollback.

1. Identify the previous known-good repository commit for `index.ts`.
2. Redeploy that source as a new Edge Function version with `verify_jwt=false`.
3. Keep the existing private bucket and objects unchanged.
4. Verify `/ready`, the durability canary, and authenticated document download.
5. If the backend version also changed, redeploy the compatible previous backend commit while keeping the same database and bucket.

Never delete or recreate the bucket as part of an application or gateway rollback.
