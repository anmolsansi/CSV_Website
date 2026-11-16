# P0: Render edge throttling on the JobGrid login path

**Status (2026-11-16):** Diagnosis and a bounded, read-only probe are prepared. **Provider remediation and live acceptance are blocked**, not complete. Primary tracking: [GitHub issue #210](https://github.com/anmolsansi/CSV_Website/issues/210).

## Failure boundary and evidence

The production browser uses `https://csv-website-steel.vercel.app/api/*`. `frontend/vercel.json` rewrites this to `https://jobgrid-api.onrender.com/*`. The backend is the existing FastAPI service `jobgrid-api`, Render service ID `srv-dalu7u3l550s73ch5lu0` in workspace **Job Grid**, Singapore. `render.yaml` currently declares `plan: free` and `numInstances: 1`. `backend/tests/test_c09_staging_readiness.py` deliberately enforces this zero-dollar contract.

The reported login failure was HTTP 429 on `POST /api/auth/email/login`, and an unauthenticated `GET /api/auth/me` also failed with 429. A prior response recorded `x-render-routing: hibernate-rate-limited` and `content-type: text/plain; charset=utf-8`. That header is evidence of Render routing throttling on **that response**. It does not prove that every subsequent 429 has the same cause. The FastAPI email-login limiter does **not** guard `/auth/me`.

Render documents 15-minute idle spin-down for Free web services, roughly minute-long spin-up, and lower inbound request-rate limits than paid compute. Render's general abuse/DDoS protections can still produce 429 on paid plans. See [Free limitations](https://render.com/docs/free), [429 troubleshooting](https://render.com/docs/troubleshooting-deploys), and [Blueprint plan IDs](https://render.com/docs/blueprint-spec).

**Access blocker:** the currently connected Render workspace is not `Job Grid`; reading service `srv-dalu7u3l550s73ch5lu0` returned 404. Do not create another service or modify the similarly named services in the accessible account.

## Architect decision and alternatives

**Needs Architect Decision:** The existing [C-09 deployment record](C09_STAGING_OPERATIONS.md) explicitly requires *zero-dollar-first* infrastructure and forbids silent upgrades. A permanent solution to the Free compute idle behavior and lower limits requires the owner to authorize a recurring compute cost or approve a different provider architecture.

| Option | Benefits | Limitations | Status |
| --- | --- | --- | --- |
| Upgrade existing Render web service to `0.5c-512mb` (often called Starter) | No origin, OAuth, cookie, database, or storage gateway migration; paid services don't spin down on idle and have higher inbound capacity | Ongoing bill, still subject to platform abuse controls; requires access to Job Grid | **Recommended after cost approval** |
| Migrate backend to an alternative always-on provider | Potentially different cost/reliability tradeoff | Needs new deployment, routing, cookies, callbacks, secret and recovery review | Not chosen |
| Stay on Render Free and add retries, keepalive pings, or higher app login limits | No direct paid-plan cost | Cannot guarantee preventing provider-level 429; keepalives are not a durable solution | Rejected as P0 closure |

Render lists entry paid compute at approximately **$7/month** at review time. Verify the workspace quote, billing terms, and taxes: https://render.com/pricing. No paid plan, redeploy, or billing setting was changed in this preparation PR.

## Safe diagnostic and verification

Run from the repository root on a machine with network access:

```bash
python3 scripts/render_edge_probe.py
python3 -m unittest discover -s scripts/tests -p 'test_render_edge_probe.py' -v
```

The probe makes **exactly one unauthenticated GET** each to direct Render `/health` and Vercel `/api/health`, with a bounded timeout. It does not submit credentials, POST, retry, poll, save response bodies, or print cookies or secrets. Output includes timestamp, status, selected capped response headers, and classification. Exit codes: `0` for both currently healthy, `2` when any 429 occurs, `3` otherwise inconclusive/unhealthy. A healthy point-in-time probe does **not** prove that login is fixed. Avoid aggressive repetition.

| Observed result | Meaning |
| --- | --- |
| 429 with `x-render-routing: hibernate-rate-limited` | Render-edge throttling confirmed for that response |
| 429 without that signature | Source not proven; inspect provider request logs and headers |
| Both health endpoints 200 | Basic routing healthy at that time, not authenticated acceptance |
| Direct 200, proxied non-200 | Investigate Vercel rewrite/proxy |
| 503 or network failure | Investigate cold-start or upstream failure; do not label as auth throttling |

## Paid-compute release runbook (explicit owner approval required)

1. Obtain access to **Job Grid** Render workspace. Inspect service `srv-dalu7u3l550s73ch5lu0`, confirming the linked repository, existing hostname, region, environment, deployed SHA, current plan, and whether its Blueprint synchronizes `render.yaml`. **Stop** if any identifier differs.
2. Capture non-secret baseline: `/health`, `/ready`, recent 429 headers, provider events, current Vercel routing, current plan, and reversibility. Do not put cookies, passwords, session tokens or API secrets in issues.
3. Obtain **explicit recurring-spend approval** based on the current provider quote, and record an architecture decision superseding C-09's zero-dollar assertion.
4. In an approved release branch, change `render.yaml` from `plan: free` to the Blueprint plan ID `plan: 0.5c-512mb`. Update `backend/tests/test_c09_staging_readiness.py`, `docs/repo_context.md`, C-09 cost notes and this runbook in the same controlled change. Keep region, instance count, URLs, secrets, Supabase storage gateway, CORS, OAuth, and disabled schedulers unchanged. The old zero-dollar test **will fail** until updated through this approved contract change.
5. Upgrade the **existing** Render service with verified Dashboard or Blueprint sync. Do not create a replacement service. Confirm the running plan, Render URL and billing activation time. Reconcile source and dashboard to avoid configuration drift.
6. Verify direct Render `/health` and `/ready` return HTTP 200, then Vercel `/api/health` and `/api/ready` return HTTP 200. Readiness must include database and private storage.
7. With only an authorized test account, verify one email sign-in, `/api/auth/me`, logout, and existing OAuth callback flow. Do not share credentials or stress-test login limits.
8. After at least 20 minutes without intentional inbound traffic, verify the backend remained running, then repeat a single authorized smoke. Capture any renewed provider-generated 429 with headers, and observe normal traffic for a target of 24 hours before accepting P0. Don't fabricate live results.
9. Close [issue #210](https://github.com/anmolsansi/CSV_Website/issues/210) only after hosted plan, routing, login, monitor evidence, and rollback readiness are independently verified.

## Rollback and scope boundaries

If the paid instance causes a regression, determine whether it's a code deploy or compute issue. Revert the compute plan via the verified provider path, and reconcile `render.yaml`, tests and docs. **Returning to Free restores the original throttling risk**, so it's a financial rollback, not a reliability fix. Deploy the previous compatible backend commit as needed. Do not downgrade PostgreSQL, delete private documents, move the URL, or change OAuth callback hosts.

This P0 does not change email/password attempt limits, `frontend/src/pages/Login.jsx`, the Vercel rewrite, user data, database migrations, or background jobs. Proxy-aware auth rate limits and UI error states belong to separate follow-ups. The diagnostic is **not** a hosting workaround.
