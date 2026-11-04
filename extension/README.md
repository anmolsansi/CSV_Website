# JobGrid Chrome extension, foundation pilot

This directory includes the EXT-01–03 foundation, EXT-05 disposable session probe, and EXT-26–28 account-bound worker and ATS route classifier for the 50-step roadmap in `development.md` §9. **It is not a functioning history tracker yet.** The release shell does not request host permissions, install content scripts, make network calls, track navigation or save visits. The bridge is injected only by the development worker after an explicit trusted tab connection. The backend supports session/check/visit/apply/forget, but the packaged release popup is inert, so no automatic tracking or application submission is enabled. Full onboarding, page observation, confirmation UI and Chrome/OAuth pilot remain future work.

## Environment and trust

- **Selected release frontend origin:** https://csv-website-steel.vercel.app. This exact Vercel origin is identified in `docs/C09_STAGING_OPERATIONS.md` (October 2026 evidence). The frontend uses its same-origin `/api` proxy to the Render backend. The release owner must revalidate the origin and OAuth session before distributing any pilot.
- **Live Chrome/OAuth acceptance: NOT VERIFIED.** No controlled real-user session or extension bridge handshake has been demonstrated by EXT-01–03. The `/crm/browser-memory/session` route is now implemented, but its real Chrome/production OAuth handshake still requires acceptance.
- **Local disposable frontend/API pair:** `http://localhost:5173` (Vite with `/api` proxy configured for the test backend, if needed) and `http://localhost:8000` (FastAPI with a disposable SQLite/test database and `TEST_AUTH=true` only for local development). These are **development fixtures**, not approved remote sites or release settings. Do not use production accounts or data.
- **Account expectation:** One explicitly selected, signed-in JobGrid tab for one server-resolved account. Keep a JobGrid tab open. Switching users, missing tab or logout suspends future tracking until a deliberate reconnect. Neither the extension nor tests store auth tokens or session cookies.
- **Supported optional ATS hosts:** `boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co`. The future automatic check only applies to exact supported job-detail routes, never arbitrary browsing. No site is enabled at installation.
- **Trust invariant:** `extension/config.js` owns the exact configured release HTTPS frontend origin. Both the release manifest and isolated bridge must agree with it. The manifest requests no host access at install. The popup cannot enter arbitrary API servers. No write comes from the page or from a session read.

## Install the shell

1. Open `chrome://extensions` in a **disposable Chrome profile** and enable Developer mode.
2. Select **Load unpacked**, then the repository's `extension/` directory, which contains `manifest.json`.
3. Open the JobGrid extension toolbar popup. It should display **Not connected yet** and **No browsing is tracked by this shell**.
4. Confirm Chrome lists no site access granted and that the extension has not connected to JobGrid. Unload the extension to roll back. There is no backend migration or account-data change in these three tickets.

`manifest.dev.json` is a **development-only alternative** containing one localhost optional host pattern. For local Chrome tests, copy the directory to a disposable temp directory, replace only that copy's `manifest.json` with `manifest.dev.json`, and overlay its public `APP_ORIGIN` and bridge `TRUSTED_ORIGIN` with the **same** exact local `http://localhost:5173` origin. Use `parseTrustedOrigin(value, { allowLocal: true })` for the test origin. Never edit or distribute the release source with localhost entries. A dev manifest must not be included in any release ZIP; release packaging is a later EXT ticket.

## Session bridge contract (EXT-03)

The isolated `jobgrid-bridge.js` does not auto-run. The EXT-26 development worker injects it **only after** the user grants the exact JobGrid frontend host and explicitly selects an authenticated app tab. Its internal message envelope is `{version:1,request_id:UUID,kind,account_id?,payload}` (maximum 8192 UTF-8 bytes). No external sender or page-to-extension relay is supported. Only fixed same-origin `/api/crm/browser-memory` routes are allowed. `GET /session` uses the existing browser cookie without reading or copying it. Before another route, the bridge rechecks the session account against `account_id`; for writes it sends fixed browser/expected-account headers. Responses and errors return only to the extension's internal runtime, never to the page DOM. The bridge has an eight-second timeout and safe 401, rate-limit, and malformed-response results.

The fixed route mapping is `session → GET /session`, `check → POST /check`, `visit → POST /visit`, `apply → POST /apply`, and `forget_visits → DELETE /visits`. The backend session, check, visit, apply and forget endpoints are now implemented by EXT-04 and EXT-14–24. The bridge is **transport only**: it does not authorize writes by itself. The EXT-26–27 development worker enforces popup-only apply/forget and selected-tab lifecycle with stale-result cancellation. Navigation-only automatic visits and site opt-ins remain EXT-29–35 scope. A failed/absent session produces an unavailable error, never a claim that no application exists.

## Local validation and limitations

```bash
node --test extension/tests/config.test.mjs
node --test extension/tests/manifest.test.mjs
node --test extension/tests/bridge.test.mjs
# or: cd extension && npm test
```

The tests use synthetic origins, accounts and responses, with no network or production database. They assert origin spoofing rejection, manifest permission hygiene, internal-message validation, exact route/method/header contracts, and safe HTTP errors. They do **not** prove a live deployed OAuth cookie, actual extension transport in Chrome, or server endpoint availability. A real Chrome load check is separate from checking manifest JSON. Do not mark extension tracking, store listing or external release accepted on the basis of these tests.

If the deployment origin changes, update the public config, release manifest and bridge origin together, record the approved release decision, then rerun the three tests. Do not widen `host_permissions`, use extension-readable tokens or add wildcard CORS to work around sign-in failures. No new dependencies, database migration, paid resource or server credential is required for EXT-01–03.

## Disposable real-browser account probe (EXT-05)

The **development manifest only** registers `background.js`. Its legacy `ext05:session-probe` remains read-only. EXT-26 adds internal popup-only `ext26:connect`, `ext26:command`, and `ext26:disconnect` with explicit tab and account binding. It requires the optional exact app host grant and exactly one matching JobGrid tab, injects `jobgrid-bridge.js` in that tab's isolated world and forwards only a session GET. There is no automatic permission request, persistence, job-page tracking or application write. The production `manifest.json` does not run this worker.

From a disposable `backend/` server with `TEST_AUTH=true`, `ENVIRONMENT=test` and a test-only database:

```bash
cd frontend
npm ci
npx playwright install chromium
npx playwright test tests/extension.spec.ts --project=chromium
```

The browser test launches a temporary persistent Chromium profile, copies the real extension source into a temporary directory, installs the dev manifest in that copy, and replaces public origin constants there with `http://localhost:5173`. Because headless Chromium cannot approve a browser-owned optional permission prompt, the temporary fixture manifest alone pregrants the exact localhost test host. The checked-in dev and release manifests retain optional-only access. The fixture then signs in to two synthetic users via the local Vite `/api` proxy, logs out and closes the app tab. The proxy is enabled by Playwright's `JOBGRID_LOCAL_API_PROXY=1` server environment and forwards only to local FastAPI at port 8000. Do not use production cookies or accounts in this test.

This automated test does **not** prove the Chrome optional permission approval UX. That must be manually verified in an unrestricted disposable Chrome profile before accepting EXT-05. The expected positive response is `{protocol_version:1,account_id:<server-owned-id>,account_label:"JobGrid account <id>"}`. Sign-out returns `not_authenticated`; closing the tab returns `unavailable`. Browser environments that block extensions or grants cannot establish this acceptance gate. Never work around that by adding broad install-time permissions or disabling cookie security.

## Data boundary (EXT-06)

Alembic 019 adds owner-owned `job_visits` and `browser_apply_receipts`. Neither is populated by this probe. Visited pages are not imported CSV URLs, saved jobs or applications. Since EXT-22–24, visits are included in optional checksummed `job_visits_v1` metadata in v2 JSON/ZIP exports and restored to the authenticated destination account. Receipts are operational and must not be backed up. See `docs/JOBGRID_BUILD_GUIDE.md` for schema, migration, tests and rollback details.

## Development-only command safety and ATS routes (EXT-25–28)

The EXT-26 worker requires a packaged popup sender and an explicitly selected, exact-origin JobGrid tab. It rejects forged sender/extra route/header/oversized packets, sends only fixed-route protocol-v1 messages through the isolated bridge and checks the server-owned account. Popup confirmation is required for apply and visit forgetting. Site candidates cannot perform writes. The EXT-27 worker also invalidates results on app-tab navigation/removal or account change and limits replies to eight seconds with no automatic retry or private offline cache. Worker restarts require a fresh connection.

`site-rules.js` recognizes only exact HTTPS Greenhouse and Lever job-detail paths and treats unknown/listing/apply/token-bearing URLs as manual-only. It never identifies a company from the ATS slug or fetches pages. User-visible UI, automatic visit tracking and ATS observation remain EXT-29–40 scope.

Validate with `node --test extension/tests/*.test.mjs` and disposable backend tests documented in `docs/JOBGRID_BUILD_GUIDE.md`. These fixtures do not replace manual Chrome permission or live OAuth acceptance.
