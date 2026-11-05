# EXT-37–40: Development popup checks and confirmed saves

This document describes the **development-only** Chrome MV3 popup. The release
`extension/manifest.json` remains inert. No automatic application submission,
production rollout, store approval, new backend route, or migration is part of
these four tickets.

## User flow

1. In a disposable Chrome profile, load a copy of `extension/` with
   `manifest.dev.json` installed as `manifest.json` (as described in
   `extension/README.md`). Open one signed-in JobGrid tab.
2. Click **Connect one JobGrid tab** and grant only the exact JobGrid app origin.
   The popup displays the account label and server-owned account ID. The
   connection remains in worker memory only and must be reestablished after
   service-worker restart.
3. Open a public HTTPS job-detail tab. On an explicitly opted-in ATS host the
   worker checks the page after navigation and records an idempotent visit.
   Otherwise select **Check current tab** for a manual, read-only check. Manual
   checks never record a visit.
4. Read the original `before_visit` evidence. **No matching history found**
   is *not* a guarantee that an application never existed. A partial lookup
   always shows an additional incomplete-search warning, even when stronger
   visited/applied evidence is present. Authentication, 403, rate-limited,
   timeout, unsupported, offline, and unavailable failures show dedicated
   states, never a false no-match result. On HTTP 429, the explicit
   Retry check button is disabled through the bounded Retry-After window.
   Expiry only reenables the button and never triggers a background request.
5. When a verified job is available, enter the employer and title. Both are
   mandatory, trimmed, and bounded at 320 and 500 characters. The popup does
   not guess them from the ATS slug, read form answers, or read page body text.
6. Click **Review application details**. The worker binds the exact checked
   URL, selected cookie-authenticated account, employer, and title to one
   session-only pending intent. Confirm the displayed account, URL, employer,
   and role, then click **Save application in JobGrid**. The popup never sends
   anything to the job site's application form.
7. The worker takes the frozen payload plus its stable UUID, verifies the
   selected account and current tab, and sends one explicit authenticated
   `POST /api/crm/browser-memory/apply` through the existing isolated bridge.
   Concurrent popup clicks coalesce. The server receipt is the source of truth.
   On confirmed success, the popup hides the form, shows a saved state and
   updates the tab badge without changing `before_visit` facts.
8. If a write response is lost, timed out or ambiguous, the popup says **Save
   result unknown**. It does not claim a successful save or automatically
   retry. Inspect JobGrid first. A deliberate retry in the same pending session
   reuses the original UUID and payload. A confirmed unknown write may also
   retain one private recovery UUID for up to 24 hours across worker
   suspension. Reconnect the same selected account, recheck that same public
   URL, review identical fields, and explicitly resubmit to reuse that UUID.
   Unconfirmed drafts still expire after 15 minutes. Changed account, fields,
   URL, pause, disconnect, successful save or expiry clear the recovery key.
   No automatic retry is permitted.

## Privacy controls

- **Pause checks** asks for confirmation, stops observations and clears
  pending drafts, warning state and badges. Resume rechecks the selected
  server-owned account.
- **Disconnect** asks for confirmation and clears extension-private state. It
  does **not** delete saved visits or applications.
- **Forget saved visits** displays the selected account and requires the exact
  text `FORGET VISITS` before an explicit
  `DELETE /api/crm/browser-memory/visits` through the fixed bridge. The backend
  deletes only external JobVisit records for the cookie owner. CsvRow click
  history, saved/imported jobs, JobTrack applications and receipts remain.
  Confirmed deletion clears stale local warnings and badges.
- **Open applications in JobGrid** navigates to the configured exact
  `APP_ORIGIN + '/applications'`. It never uses the untrusted job URL as a
  destination and uses `noopener noreferrer`.

## Implementation and contracts

- `extension/popup.dev.html` supplies accessible labels, status messages,
  editor fields, confirmations and the fixed destination.
- `extension/popup.dev.js` renders text with `textContent`, maps failures,
  stages one intent and sends the explicit confirmation. It never reads
  job-site DOM, cookies, passwords or application answers.
- `extension/popup-state.js` centralizes safe result/error copy.
- `extension/popup-apply.js` normalizes bounded form values and checks account,
  URL and pending intent consistency. This is a UI guard, not authorization.
- `extension/background.js` validates the exact popup sender, protocol v1,
  UUID and max 8192-byte packet. `ext39:submit-pending` accepts **only**
  `{type, version, request_id, tab_id}`; the worker supplies the URL,
  company, title, confirmation and original idempotency key. The existing
  `ext26:command` `forget_visits` request requires `confirmed:true` and
  strips that field before the fixed DELETE route. External pages cannot
  invoke either flow.
- `extension/jobgrid-bridge.js` retains exact-origin cookie auth, pre/post
  account rechecks, request deadlines, and fixed `/apply` and `/visits`
  routes. It now distinguishes 403 and observed offline transport failures.

## Verification and rollback

```bash
cd extension
npm test
# or from repository root:
node --test extension/tests/*.test.mjs
```

The tests cover partial results, all failure categories, field limits,
sender spoofing, account/URL changes, expired pending intents, concurrent
submissions, lost-response retry with one UUID, owner-only forgetting,
warning invalidation and fixed-origin links.

These isolated tests use mocks. They do **not** establish deployed OAuth,
real Chrome grant UX, persistent-profile screen-reader acceptance,
service-worker suspension, production DB migrations, or Chrome Web Store
approval. Those remain the later EXT-41–50 and earlier external acceptance
gates. Roll back by unloading the development extension or reverting this
feature branch. No new credentials, paid infrastructure or database change
is required.
