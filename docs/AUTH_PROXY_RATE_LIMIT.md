# JobGrid authentication rate limits through Render and Vercel

## Status and release gate

This is an application-code hardening change, **not a claim of resolved production
429s**. The default configuration ignores `X-Forwarded-For` and uses the socket
peer until the real Render ingress trust boundary is confirmed. An operator must
verify the actual network path before enabling the trusted-proxy setting.

As of November 16, 2026, the existing release decision in issue #210 remains
**Render Free, $0**. The request to consider paid always-on compute conflicts
with that earlier decision. No service was upgraded and `render.yaml` still
contains `plan: free`. The linked Render workspace does not expose the target
JobGrid service, ID `srv-dalu7u3l550s73ch5lu0`.

## Why this is needed

`backend/app/routers/email_auth.py` limits each action to 80 attempts per
peer and five per email per 15-minute database window. In a reverse-proxy
deployment the socket peer can be an ingress proxy instead of the original
client. Worse, Render's Python runtime documents `FORWARDED_ALLOW_IPS=*`;
Uvicorn normally accepts forwarded headers from any peer under that setting,
which permits IP spoofing if user input reaches those headers.

The application must **not** treat an arbitrary first `X-Forwarded-For`
address as trusted. Render also has its own upstream request limits that the
application cannot control. The earlier `x-render-routing:
hibernate-rate-limited` response was from Render, not from these SQL counters.

## Implementation and contracts

- `render.yaml`: Uvicorn starts with `--no-proxy-headers`. This ensures
  `request.client.host` is the actual connection peer rather than a value
  rewritten from forwarded request headers. Render's default environment
  variable therefore cannot silently alter the ASGI client address.
- `backend/app/config.py`: optional
  `EMAIL_AUTH_TRUSTED_PROXY_CIDRS`, a comma-separated list of exact trusted
  ingress CIDRs. Defaults to empty. Never set it to `*` or `0.0.0.0/0`.
- `backend/app/services/auth_client_ip.py`: accepts a forwarded chain only
  when the actual socket peer belongs to the configured ingress networks.
  Reads all `X-Forwarded-For` header occurrences, scans right-to-left, skips
  verified proxy hops and selects the first untrusted hop. That may be an
  intermediate proxy, not the user's home IP, but is the first defensible
  security boundary. On absent/malformed/oversized input or bad configuration,
  falls back to the socket peer. IPv4-mapped IPv6 normalizes to IPv4.
- `backend/app/routers/email_auth.py`: hashes the resolved peer identity
  into the **existing** shared SQL limiter. The action namespace, email-based
  limit, fixed 15-minute window, status code, response detail and Retry-After
  header are unchanged.
- No schema migration, new service, frontend API change, or credential
  exchange is needed. PostgreSQL remains the source of truth for rate counters.

## Operator setup: fail closed before enabling proxy trust

1. Inspect the **actual JobGrid Render service** and its deployed start
   command. Make sure the process really runs with `--no-proxy-headers`.
   Check that the service's Build & Deploy settings are consistent with the
   committed `render.yaml`. Do not change a different Render service.
2. Keep `EMAIL_AUTH_TRUSTED_PROXY_CIDRS` **unset** while diagnosing. This
   means all requests from one Render proxy may still share the peer cap,
   but spoofed forwarding headers cannot evade rate limiting.
3. With the hosting owner, confirm which trusted ingress component appends
   the rightmost XFF hop and obtain its verified **source IP CIDR(s)**. Do not
   infer trusted **inbound** proxy ranges from Render's outbound-IP list or
   from arbitrary addresses seen in a browser. Verify behavior for both
   Vercel-rewritten and direct `onrender.com` requests.
4. Only after confirming the network trust boundary, add the narrowest
   CIDR(s) as `EMAIL_AUTH_TRUSTED_PROXY_CIDRS` in the backend's private
   Render environment. Example **documentation addresses only**:
   `10.3.4.5/32,10.3.4.6/32`. These examples are **not Render's IPs**.
   Do not include broad public internet ranges.
5. Verify in staging using harmless requests and mocked auth in tests.
   Requests from two different clients behind the same verified ingress
   must count separately; different spoofed XFF prefixes from the same
   untrusted peer must NOT create new buckets. Invalid headers must fall
   back to the socket IP. Check the actual response headers for 429 before
   attributing it to SQL or Render.
6. If the ingress IPs are dynamic, unpublished, unverified, or headers
   are not appended reliably, **leave the setting empty**. The application
   remains fail-closed but per-client attribution remains incomplete.
   Escalate to a supported provider/proxy identity solution rather than
   guessing networks or trusting all headers.

No tests or dashboards should print raw email/password/session tokens. The
service should record counts of application 429s separately from provider 429s
using redacted metrics, not from auth response bodies.

## Verification

From a normal repository checkout with backend dependencies installed:

```bash
cd backend
pytest -q tests/test_auth_client_ip.py tests/test_email_password_auth.py tests/test_c09_staging_readiness.py
python -m compileall -q app
```

`tests/test_auth_client_ip.py` covers untrusted peers, rightmost-untrusted
chain selection, multiple forwarding headers, IPv4/IPv6, oversize or malformed
input, and invalid trust settings. Email-auth tests cover separate 80-attempt
peer buckets behind a trusted proxy, the unchanged five-attempt email cap,
HTTP 429 and Retry-After.

These test fixtures simulate a known good ingress. **They do not verify the
unavailable JobGrid Render account.** Before release, run the normal backend
CI matrix and protected staging acceptance, then check production only
after an approved deployment.

## Always-on hosting alternative (separate owner/billing gate)

If the owner explicitly replaces the existing $0 constraint, upgrade the
**existing** Render web service instead of creating a new service:

1. In the correct JobGrid workspace, open
   https://dashboard.render.com/web/srv-dalu7u3l550s73ch5lu0
   and confirm repository `anmolsansi/CSV_Website`, branch `main`,
   region `singapore`, backend URL and database configuration.
2. Under its instance/compute settings, compare **Free** with the
   current paid **Starter** price, listed by Render as **$7/month** as of
   this runbook. Verify the actual checkout price and billing terms in
   your account. A paid compute instance is a separate choice from a paid
   Render workspace plan.
3. Review any Blueprint management: if `render.yaml` controls the
   instance plan, changing it to `plan: starter` must happen in a separate
   reviewed infrastructure change together with the provider-side change.
   Avoid drift or creating a second service. Keep `numInstances: 1`,
   disabled background jobs and the existing durable Supabase gateway.
4. After the owner authorizes costs and deploy, verify `/health`,
   `/ready`, a single valid login, cookie behavior, normal 401 logout
   behavior, and 429 recovery through the Vercel rewrite. Watch logs
   and provider events. Never run automatic login POST retries.
5. Roll back via the service's compute-plan setting and matching
   infrastructure configuration if necessary. Downgrade may restore
   Free spin-downs and rate limits. The database and storage stay put.

No paid change has been approved or executed in this implementation.
Paid capacity improves availability but does **not** remove the
application's anti-brute-force limits or all possible provider throttling.

## Safe rollback for this code

If unexpected auth or OAuth regressions occur, revert the application
PR and restore the previously verified Render start command through an
approved deployment. Revert `EMAIL_AUTH_TRUSTED_PROXY_CIDRS` to empty first
if attribution or trust is in doubt. The SQL rate-limit table, users,
sessions, PostgreSQL data and document storage must not be reset.
