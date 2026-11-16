# P0: Render Free login-throttling recovery ($0)

**Decision:** On November 16, 2026, the owner explicitly selected **$0** and the existing [JobGrid Render service](https://dashboard.render.com/web/srv-dalu7u3l550s73ch5lu0), ID `srv-dalu7u3l550s73ch5lu0`. This supersedes the paid-compute proposal in the previous version of this runbook. No hosting upgrade, paid service, keepalive monitor, origin change, or database migration is authorized.

**Scope:** Reduce accidental traffic and keep Render gateway throttling from being misrepresented as an incorrect password or a logout. **This cannot eliminate provider-generated 429s on Render Free.** The service will still sleep after 15 minutes without inbound traffic and may take around a minute to wake. Render documents lower inbound rate limits on Free, and it can reject requests to mitigate abuse. See https://render.com/docs/free and https://render.com/docs/troubleshooting-deploys.

## Current architecture and evidence

- Vercel frontend: `https://csv-website-steel.vercel.app`; `frontend/vercel.json` rewrites `/api/:path*` to `https://jobgrid-api.onrender.com/:path*`.
- Render backend: `jobgrid-api` Free service in **Job Grid** workspace, Singapore, service ID `srv-dalu7u3l550s73ch5lu0`.
- Database: PostgreSQL on Supabase; private document storage via existing gateway.
- `render.yaml` retains `plan: free`, disabled background jobs, one instance and existing health check. `backend/tests/test_c09_staging_readiness.py` continues enforcing $0.
- A previous login 429 had `x-render-routing: hibernate-rate-limited`, a Render routing-layer signal for **that** response. A simultaneous `/api/auth/me` 429 cannot be caused by the backend email-login rate guard because `/auth/me` does not use it.
- The GitHub/Render connector has access to a different Render workspace. Attempting to read this actual service ID yields 404. **A dashboard URL by itself does not grant API access**, so live provider settings are not verified. Do not modify an unrelated service.

## Code behavior for the Free tier

### Initial session check

`frontend/src/App.jsx` calls `api.me()` to establish session state. Previously all failures were treated as a logout, which could push people into login while Render was rejecting requests. After this change:

- HTTP 401/403: treat as logged out and show existing login screen.
- HTTP 429: do **not** mark the user logged out. Show a separate accessible service-connection screen, a visible retry delay, and a **manual** Retry connection control.
- Other failed session checks/network failures: show service unavailable, leaving account state unknown.
- Retry is never automatic. When Render provides a valid `Retry-After` up to 3600 seconds, honor it. With no valid header, the UI applies a 60-second manual retry cooldown on session 429. When the user clicks, make **one GET** for `/auth/me`. Cancel stale UI updates if the component effect is cleaned up.

### Email login requests

`frontend/src/pages/Login.jsx` prevents concurrent form submissions via a ref guard. A 429 disables the sign-in button for bounded `Retry-After` seconds, or 60 seconds if no valid header. The app never auto-retries any email-login, registration, password-reset, or other authentication POST. The error text distinguishes the specific `hibernate-rate-limited` signal, the backend's known JSON password-attempt limit, and an unattributed 429. No credentials are logged.

`frontend/src/api/authAvailability.js` owns the pure classification helpers, with zero added dependencies.

### Explicit non-goals

No bypassing Render's limits, unauthorized keepalive pings, polling, paid compute, altered database data, changed rate-guard security limits, new service or backup, Vercel route change, credential exposure, OAuth redirect change, and no claim of always-on hosting.

## Safe diagnostics

From the repository root, once per investigation:

```bash
python3 scripts/render_edge_probe.py
python3 -m unittest discover -s scripts/tests -p 'test_render_edge_probe.py' -v
cd frontend
node --test unit/auth-availability.test.mjs
npm run build
```

The first command makes exactly one anonymous GET to direct Render `/health` and one to Vercel `/api/health`. It does not POST, poll, log credentials, or read response bodies. A 200 does not certify login. Do not repeat it rapidly.

| Result | Interpretation |
| --- | --- |
| 429 and `x-render-routing: hibernate-rate-limited` | Render routing throttling for this response |
| 429 without this header | Source unknown; inspect response and provider events |
| JSON `detail: Too many attempts. Try again later.` | Application email-auth limit, independent of provider |
| Health 200 | One point-in-time routing check, not always-on or login proof |
| 503/timeouts | Investigate startup, deployment, or upstream dependencies |

## Acceptance and operations at $0

1. Access the owner's **Job Grid** Render workspace and check [the exact service](https://dashboard.render.com/web/srv-dalu7u3l550s73ch5lu0) remains Free, linked to the expected repository, branch, region and URL. In Billing > Monthly Included Usage, examine Free instance hours and bandwidth/pipeline usage. Confirm no quota-based suspension. Do not share credentials or secrets.
2. For one actual failed sign-in, save only status, content-type, `x-render-routing`, `retry-after`, `cf-cache-status`, provider request timestamp and sanitized event entries. Never paste email/password/session cookie into issues.
3. Run the Node helper tests and existing backend probe tests. Run `npm run build`, Playwright `frontend/tests/render-free-session-recovery.spec.ts`, and normal required GitHub CI. Tests must demonstrate the UI does not mark 429 as logout or auto-repeat login POST.
4. Deploy through an approved PR/production release. The repository can auto-deploy `main` to Vercel and Render, so **review both provider auto-deploy gates** before merging, even though this change is frontend-only. Keep the service, `plan: free` and every secret unchanged.
5. After deployment, test a legitimate account once through Vercel. If Render returns 429, verify the UI displays a connection issue, honors a bounded manual retry delay, and eventually lets the user log in when the upstream becomes available. Test 401 still displays normal login.
6. Observe normal traffic for an agreed window. Check hosting status, failed-request headers and whether calls are rejected by Render or the app. If Free capacity remains insufficient, document an **unresolved platform limitation** and decide whether accepting occasional failures is compatible with a $0 budget. Do not mark that as fixed or promise zero future 429s.
7. Rollback frontend changes to the previous verified deployment/commit if new UI introduces a regression; retain backend/database/objects. Rollback restores old UX, not Free-plan capacity.

## Constraints and user-facing expectation

Render Free is appropriate for a personal project or demo with occasional cold-start delays. **No honest no-cost plan can promise all legitimate logins will always succeed on the first request or that Render 429s will never occur.** The deliverable is recovery, less request pressure, correct diagnosis, and preserved $0 compute. Provider-account access and actual production smoke evidence are still mandatory before closing [P0 #210](https://github.com/anmolsansi/CSV_Website/issues/210).

## Separate backend client-identity hardening

The email-auth SQL limiter has a separate security concern from Render edge
throttling. See [AUTH_PROXY_RATE_LIMIT.md](AUTH_PROXY_RATE_LIMIT.md) for
trusted ingress CIDRs, `--no-proxy-headers`, the fail-closed default,
targeted tests and a separately gated paid-hosting option. This does not
change the $0 decision or solve upstream Render Free limits.
