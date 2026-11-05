# JobGrid Chrome extension, foundation pilot

This directory includes the EXT-01–03 foundation, EXT-05 disposable session probe, EXT-26–28 account-bound worker/ATS route classifier, EXT-29–32 development-only page observation, and EXT-33–36 current-tab and popup flows for the 50-step roadmap in `development.md` §9. **The release extension is not yet a functioning history tracker.** The release shell does not request host permissions, install content scripts, make network calls, track navigation or save visits. The bridge is injected only by the development worker after an explicit trusted tab connection. The backend supports session/check/visit/apply/forget, but the packaged release popup is inert, so no automatic tracking or application submission is enabled. Full onboarding, page observation, confirmation UI and Chrome/OAuth pilot remain future work.

## Environment and trust

- **Selected release frontend origin:** https://csv-website-steel.vercel.app. This exact Vercel origin is identified in `docs/C09_STAGING_OPERATIONS.md` (October 2026 evidence). The frontend uses its same-origin `/api` proxy to the Render backend. The release owner must revalidate the origin and OAuth session before distributing any pilot.
- **Live Chrome/OAuth acceptance: NOT VERIFIED.** No controlled real-user session or extension bridge handshake has been demonstrated by EXT-01–03. The `/crm/browser-memory/session` route is now implemented, but its real Chrome/production OAuth handshake still requires acceptance.
- **Local disposable frontend/API pair:** `http://localhost:5173` (Vite with `/api` proxy configured for the test backend, if needed) and `http://localhost:8000` (FastAPI with a disposable SQLite/test database and `TEST_AUTH=true` only for local development). These are **development fixtures**, not approved remote sites or release settings. Do not use production accounts or data.
- **Account expectation:** One explicitly selected, signed-in JobGrid tab for one server-resolved account. Keep a JobGrid tab open. Switching users, missing tab or logout suspends future tracking until a deliberate reconnect. Neither the extension nor tests store auth tokens or session cookies.
- **Supported optional ATS hosts:** `boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co`. The future automatic check only applies to exact supported job-detail routes, never arbitrary browsing. No site is enabled at installation. The development worker supports an explicit per-host opt-in command, but the release popup does not expose it yet.
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


## Development-only public ATS observation (EXT-29–32)

The release manifest.json remains **inert**, with no background worker or
registered content scripts. The development worker offers an internal,
**popup-sender-only** protocol for later onboarding and disposable tests:

- ext30:site-status: {type,version:1,request_id:UUID,host} returns
  opted_in and permission_granted for one of the three exact ATS hosts.
- ext30:site-opt-in: the same envelope plus enabled:boolean. Enabling
  requires an existing selected JobGrid account and Chrome's explicit optional
  host-permission approval. Revoking/disabling unregisters that host's
  dynamic script. No grant is requested on install, restart, navigation,
  or from a job page.
- ext32:tab-status: {type,version:1,request_id:UUID,tab_id} returns the
  selected account's *prior check* and save_state only for the same live URL.
  It is not a public page API.

For enabled hosts, job-candidates.js is registered with an exact HTTPS
origin, allFrames:false and persistAcrossSessions:false. It is passive
until the worker asks it to extract **public, visible headings** on an exact
Greenhouse or Lever job-detail URL. It never reads form fields, entered
answers, applicant identities, page body text, cookies or credentials. Title
and employer are bounded, untrusted **editable candidates**, not guaranteed
company identity, and can be null. No ATS tenant slug is an employer.

On a supported, opted-in top-level navigation the development worker waits
500 ms, validates the URL and selected account, extracts public candidates
and sends one authenticated /check through the existing isolated JobGrid
tab bridge. It retains the complete pre-write result before attempting
/visit. The idempotent visit endpoint safely replays existing visits without resetting their first timestamp; an earlier CSV click alone does not prove a durable external visit. A failed/ambiguous visit is
reported as save_unknown, **never** as successfully saved. The original
visited/applied/company match warning is preserved for future UI rendering.
Stale tab, revoked permission, disconnected account and failed checks cause
**no** automatic visit write. No automatic apply is ever performed.

Per-host opt-in persists in chrome.storage.local. Current-tab check
warnings are bounded and kept only in trusted chrome.storage.session, then
cleared on disconnect/reconnect. The worker does not restore a signed-in
connection after suspension. The development manifest now opens popup.dev.html for connection, pause,
manual checking and read-only warnings. The release popup remains inert, and
the EXT-37–40 confirmation UI is available only in this development popup. Permission pilots remain separate; the auto-observation path was first exercised by a trusted
development harness, not by a regular installed end user.

Run cd extension && npm test for isolated candidate privacy, permission,
navigation and check-before-write regressions. Tests use synthetic pages and
accounts. They do **not** establish real Chrome optional-permission UX,
deployed OAuth, end-to-end app availability, accessible warning UI or store
readiness. Disable the development extension to stop observation. No backend
schema migration, API contract, paid service or production rollout is part
of EXT-29–32.


## Development-only popup and session lifecycle (EXT-33–36)

Load a disposable copy of extension/ with manifest.dev.json as manifest.json.
Open one signed-in JobGrid tab. Use **Connect one JobGrid tab** in the dev
popup to approve only the exact JobGrid frontend origin and connect to the
server-resolved account. Keep exactly one matching JobGrid tab open. The
release manifest still opens the no-script popup.html and has no worker.

- **Check current tab** is an explicit, read-only activeTab gesture for a public
  HTTPS page, including unsupported job sites. It rejects local/private hosts,
  IP hosts, userinfo, credential-like query keys and fragment URLs, never
  injects a content script on the page, does not grant the page API access and
  does not record a visit. The worker rechecks the selected account before
  showing the original check result. The popup cannot select an arbitrary API
  origin.
- The worker-only ext34:stage-apply and ext34:pending-apply commands maintain
  at most 20 session-only, 15-minute pending drafts. An unchanged draft reuses
  its UUID. Any changed employer, title or URL gets a new UUID; account
  revalidation, reconnect, disconnect and tab navigation clear stale drafts.
  These are not application submissions. The dev popup does **not** expose
  an Apply button. Editable confirmation and real submission are EXT-38–39.
- **Pause checks** stops automatic ATS checks and manual checking, clears
  current-tab warnings, pending drafts and badge evidence. Resume rechecks the
  selected server account. **Disconnect** clears session-only state and badges
  without deleting previously saved JobGrid visits or applications.
- Badges mean **A** = definite applied URL, **V** = previously visited, and
  **?** = possible application or employer-history evidence. Badges are scoped
  to tabs and removed on navigation, pause, permission revocation and
  disconnect. They are warnings, not a verified saved-visit receipt.
- popup-state.js derives separate definite applied, possible, visited,
  company-history, incomplete-search and no-match warnings from the
  **pre-write** /check facts. popup.dev.js adds untrusted titles/employers only
  with textContent, never HTML. Missing or failed results are not interpreted
  as "not applied". The manual-check state is labeled "not saved".

### Message contracts and verification

All commands require the exact packaged popup sender, protocol v1 and a UUID
request_id. ext33:current-tab-check takes no payload. ext34:stage-apply takes
tab_id, company and title, and derives the checked URL inside the worker.
ext34:pending-apply and ext34:clear-pending take tab_id. ext35:set-paused
takes paused:boolean; ext35:status takes no payload. All are internal
extension messages, never page messages, new backend routes or public APIs.

Run cd extension && npm test. The relevant regressions are in
tests/auto-memory.test.mjs and tests/popup-state.test.mjs. They simulate
tab navigation, session changes, badges, public URLs and hostile text.
Manual Chrome optional permissions, production OAuth, service-worker
suspension and screen-reader interaction are separate pilot acceptance gates,
not established by these VM tests. Unload the dev extension or revert the
feature branch to roll back. No migration, new service or paid resource is
required.

## Development popup: EXT-37–40

The development popup now renders distinct partial, offline, authorization,
rate-limited, timeout and unsupported states. No failed check is shown as a
definite absence of applications. Editable employer/title fields require
account, URL and explicit confirmation before any application is saved. The
worker retains a stable 15-minute pending UUID for safe **user-triggered**
lost-response retries without automatic reposting. The successful server
receipt is displayed without modifying the original pre-visit warning.

Pause and disconnect require confirmation; the typed `FORGET VISITS` action
deletes only the selected cookie-account's external visit records, never
applications or CSV clicks. Open JobGrid is a fixed-origin
`/applications` link. The release manifest remains inert.

Full user steps, field/transport contracts, privacy effects, tests, rollback
and acceptance limitations: [EXT-37–40 popup guide](../docs/EXT37_40_POPUP_CONFIRMATION.md).

To validate locally: `cd extension && npm test`. The automated tests are
not evidence of real Chrome permissions, OAuth, extension store acceptance or
deployed production behavior.


## Local Chromium integration and safety acceptance (EXT-41–44)

The acceptance harness in frontend/tests/extension.spec.ts opens a disposable
persistent Chromium profile with the development worker and the local Vite
proxy/FastAPI server. It covers real cookie-authenticated /check, /visit and
explicit /apply requests; first-visit versus revisit warnings; cross-account
isolation; hostile page/postMessage attempts; keyboard-focused popup fields;
offline errors; per-tab navigation/opt-out; and browser restart requiring a
fresh connection. Each test uses synthetic accounts/jobs and cleans up the
profile. Do not point it at a deployed account or production database.

Start a disposable backend with TEST_AUTH=true, ENVIRONMENT=test, a test
database and FRONTEND_URL=http://localhost:5173. From frontend/, run
npx playwright test tests/extension.spec.ts --project=chromium.
The test config starts Vite and its local /api proxy. Separately run
cd extension && npm test for isolated worker/permission contracts.

The harness changes only its *temporary* copied manifest to pregrant
localhost and a synthetic Lever origin. The committed manifests are
unchanged. This does **not** establish normal Chrome optional permission
prompts, real installed-popup/tab behavior, a true service-worker suspension,
real grant revocation, deployed OAuth or a screen-reader audit. Those gates
are still open. Uninstall the development extension to stop testing. Saved
server history is unaffected by uninstalling it. No release or store
distribution is implied by a passing automated run.


### Manual acceptance still required before checking EXT-41–44 complete

Run only in a disposable Chrome user profile with a copied **development**
extension, local Vite/FastAPI, test-auth enabled and an isolated test database.
Do not load an installed release extension or use a personal browser profile,
real job application, or deployed account. Keep a record of Chrome version,
extension/dev backend SHA, test DB identifier, case ID, expected/actual result
and sanitized screenshot or short video. Never upload cookies, application
history, private profile data or complete job URLs as QA evidence.

1. **EXT-41, real Chrome launch and persistence.** Confirm Chrome's
   browser-owned JobGrid host-permission prompt before connecting. In the
   disposable JobGrid tab, sign in to synthetic account A. Open an opted-in
   synthetic Lever job: first navigation must show the *pre-save* unvisited
   result, later navigation must show **Visited before**. Record one explicit
   application; revisit the canonical job URL and verify **Already applied**
   with unchanged timestamp. Delete only the synthetic CSV source row,
   reload, and verify the application and separate external visit remain.
2. **EXT-42, account/hostile-page boundary.** Keep a synthetic job tab open,
   switch the JobGrid tab from A to synthetic account B between a check and
   an attempted apply, and confirm the write is rejected and no private A
   history is shown. Test an untrusted job-page script and iframe that send
   forged page messages and inspect the page DOM/storage. They must never
   receive private matches or write another account's records.
3. **EXT-43, actual popup accessibility.** Keyboard-only (Tab, Shift+Tab,
   Enter, Space) check and edit the employer/title fields, stage, cancel
   confirmation, pause/resume, cancel/confirm Forget visits, and disconnect.
   Use a screen reader in the *real extension popup* to verify associated
   field labels, meaningful focus after invalid fields, and a single
   announcement for loading, applied, possible, empty, error, paused and
   manual-only states. At Chrome 200% zoom and increased OS text size, no
   necessary control may be clipped, inaccessible or understandable only
   by badge color.
4. **EXT-44, genuine MV3 and permission lifecycle.** Use
   chrome://extensions to stop/inspect the JobGrid service worker with a
   pending, unresolved synthetic apply. Wake/reconnect deliberately and
   confirm the selected account and current URL are rechecked; no apply
   may auto-replay. Test offline read, offline write, reload, SPA
   pushState navigation, tab closure and granted-host revocation *while a
   check is in flight*. Results/badges from stale URL, account or grant
   must be ignored or cleared, and the backend must have no unintended
   writes. Restart the entire disposable browser and verify no private
   session results or pending actions are retained.

A green headless Playwright run is not evidence that these four manual
walkthroughs passed. Leave the EXT-41–44 issue checkboxes open unless the
actual expected/observed results and environment are recorded. If an assertion
fails, do not merge or widen permissions. Record the exact case and use the
ticket's defined stop/architect-decision process before runtime changes.


## Lookup performance and privacy diagnostics (EXT-45)

The isolated benchmark in backend/tests/test_browser_memory_matches.py seeds
10,000 synthetic owner-specific visits, 521 applied company rows and a second
account. It verifies the owner/hash unique index and the disposable database
query plan, then times 30 authenticated HTTP checks through FastAPI TestClient,
including validation, owner resolution, rate counting and serialization. The first
HTTP check is recorded separately; it is not a process or database cold start. Nearest-rank warm p95 must be no greater than 2,000 ms;
matches must be bounded to 20, old definite URLs must survive the dense
possible-match scan, and foreign visits must stay hidden.

Run the benchmark in a disposable backend with project requirements installed:

    cd backend
    DATABASE_URL=sqlite:///:memory: python -m pytest tests/test_browser_memory_matches.py -q -s

PostgreSQL is also exercised by CI. Inspect the aggregate EXT-45 benchmark
line in actual test output for backend dialect, 10,000 visits, 30 samples,
separate cold time, measured warm p95 and index-plan result. Recorded CI evidence on 2026-11-05 (PostgreSQL on Ubuntu, Python 3.12):
10,000 visits, 30 warm samples, measured warm p95 **14.0 ms**,
separate cold lookup **21.6 ms**, query plan **index**.
Source: https://github.com/anmolsansi/CSV_Website/actions/runs/41991907712 .
No Chrome cold-start timing is inferred from this backend run. The extension worker's
8-second timeout is separate from backend warm latency. Diagnostics may
report action, outcome, count and rounded durations, but must never expose
raw URLs/query strings, cookies, account labels, private company/title
fields or application data. The test checks synthetic payload sentinels
against captured application logs; it does not certify all production logs.

## CI and reproducible inactive pilot archive (EXT-46–47)

The existing CI workflow retains the frontend build, backend compile,
PostgreSQL tests, and full Playwright Chromium suite. It adds a separate
Node 22 extension-contract job with JUnit requiring nonzero tests and zero
failures/skips. The local Vite/FastAPI E2E job separately executes the six
persistent-profile extension acceptance tests before the full suite, with
JUnit minimum collection enforced. It loads the real development worker in
bundled Chromium using disposable synthetic accounts and temporarily
pregranted local-only fixture hosts, not a deployed account.

Once Node, Chromium and PostgreSQL tests pass, a gated job builds and
SHA-256/verifies an inert versioned pilot ZIP and retains it as a GitHub
Actions artifact for seven days. It never uploads a store listing.

Local commands from the repository root:

    node --test extension/tests/*.test.mjs
    cd frontend && npm ci && npx playwright install --with-deps chromium && npm run test:extension

The frontend test requires a disposable TEST_AUTH=true backend at
localhost:8000, with the local Vite /api proxy enabled by Playwright.
Do not treat successful headless tests as real Chrome optional-permission,
screen-reader, MV3 suspension, or deployed OAuth acceptance.

Build and verify the release-shell ZIP:

    node extension/package.mjs
    cd extension/dist
    sha256sum -c *.sha256
    unzip -t jobgrid-pilot-v*.zip

Artifacts are named jobgrid-pilot-v<manifest-version>.zip and matching
.zip.sha256. Packaging includes only manifest.json and popup.html, in
stable sorted order with fixed timestamps and reproducible SHA-256.
The test rejects unsafe permissions, localhost/dev hosts, secret
sentinels, executable scripts, source symlinks and unexpected files.

IMPORTANT: The release ZIP is intentionally **inactive**. It has no
background worker, content scripts, network bridge or automatic tracking,
and cannot check/save/apply to real jobs. Development-only functionality
must not be promoted without the pending external Chrome/OAuth gates.

### Privacy, unpacked install, updates and removal

Use a disposable Chrome user profile only. After SHA verification, unzip
to a fresh directory, open chrome://extensions, enable Developer mode,
choose Load unpacked, and select the folder with manifest.json. The
popup must show Not connected yet and No browsing is tracked by this
shell. There should be no host-permission or account prompt on install.
This proves only that the inactive package loads.

For an update, disable/remove the previous test installation, unpack
a separately verified version into a new folder, load that new folder,
and record the installed ZIP version/checksum separately from the
frontend/backend SHA. To pause the inactive shell, disable it in Chrome.
For the separate development extension, use its confirmed Pause checks
control or disable it under chrome://extensions. Choose Remove to uninstall.

Uninstalling clears extension-controlled browser state, **not** server
visits or applications previously saved by a development install.
The development popup's confirmed Forget visits deletes only the
selected account's external visits and does not delete applications,
CSV click history or imported rows. Keep the expected account visible
before any destructive step. Do not use actual personal accounts,
job applications or production backend data during these checks.

A production extension activation, store submission or rollout is
explicitly outside this ZIP. Unproven Chrome permissions, worker
suspension, accessibility and OAuth gates remain open.
