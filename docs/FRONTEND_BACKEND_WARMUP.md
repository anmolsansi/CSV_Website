# Early Render backend warm-up on JobGrid entry

## Decision

On a new visit to **https://csv-website-steel.vercel.app/**, a browser starts
one anonymous GET to **https://jobgrid-api.onrender.com/health** from the HTML
`<head>` before React executes. No `/auth/me`, login request, or authenticated
page data request is made until that health request returns HTTP 200.

This is **visitor-triggered**, not a keepalive service. There are no background
timers that ping Render and no automatic health retries. One refresh starts a
new visit and therefore a new health request.

On `localhost` / `127.0.0.1` the startup probe instead goes to
`http://localhost:8000/health` for reliable local development and CI. Other
unrecognized hosts skip this production-only start gate, so a preview
deployment cannot inadvertently wake production Render.

The request uses `GET`, CORS mode, `credentials: omit`, no custom headers,
`cache: no-store`, and an abort deadline of 90 seconds. Render Free can take
about a minute to cold-start. Only response status and a visible Retry-After
value are consumed. No cookies, authentication, or response bodies are sent to
browser-console diagnostics.

## User experience

- HTTP 200: mount the app, then perform the existing authenticated session
  check and normal navigation.
- The startup screen displays a **02:00 → 00:00 countdown** measured
  from the earliest HTML health request, updating once a second. On HTTP 200
  the app proceeds immediately, without waiting for the countdown.
- HTTP 429: show the backend startup screen, preserve unknown session state,
  and allow **manual retry** at the end of the 120-second window. A longer
  visible `Retry-After` takes precedence.
- Non-200 and network/CORS/timeout failure: keep the app gated with a
  meaningful unverified connection message. Its retry button follows the
  same 120-second window, even when the health probe timed out after 90 seconds.
- The `/auth/me` connection-retry page and the authenticated app-wide
  **Reload page** warning display the same countdown from **02:00 to 00:00**
  before enabling their buttons. These windows start when the failures occur.
- The countdown is calculated against a fixed timestamp and does not reset
  if the tab is backgrounded. Reaching zero **never** causes an automatic
  retry, reload, login, or extra Render request.
- React `StrictMode` double-mount cannot duplicate the initial wake GET:
  the HTML creates the promise exactly once, and the React gate observes it.
- The existing `/auth/me` error UI and its manual recovery remain unchanged.

**Important:** HTTP 200 from `/health` confirms only process liveness, not
database or storage readiness. It cannot promise `/auth/me` will succeed.
Render may reject the health request at its routing layer. Such a 429 might
also be missing CORS headers, in which case the browser cannot read its status
and the UI labels it as unverified, not as confirmed healthy. This cannot
bypass Render Free routing limits, prevent cold starts, or guarantee a
working login. The root cause of persistent `hibernate-rate-limited` responses
must still be investigated in Render's dashboard and support channels.

## Verification

From `frontend`:

```bash
npm ci
npm run build
node --test unit/*.test.mjs
npx playwright test tests/backend-startup.spec.ts tests/render-free-session-recovery.spec.ts --project=chromium
```

The focused browser suite verifies exact request ordering, one initial GET,
no session request during wake, a visible 120-second countdown, manual 429
recovery, and no flood on an unreachable endpoint. The frontend unit suite
covers formatting, zero-floor behavior, and longer provider Retry-After windows. The full Playwright suite and standard GitHub
CI remain release gates.

## Operational boundaries

- Existing Render service remains Free, with no paid upgrades, keepalive
  monitors, deployments to the backend, new auth bypasses, or database changes.
- New visitors send one additional public GET to Render. At high traffic
  that **increases** request volume and might worsen routing throttling.
- Requests are direct cross-origin browser requests. The backend must return
  appropriate `Access-Control-Allow-Origin` for the Vercel site. If a CORS
  failure persists even when `/api/health` is HTTP 200 through the Vercel
  rewrite, the correct production fix is to verify the explicitly configured
  backend `CORS_ORIGINS` or redesign the probe through the existing proxy,
  not to use `mode: no-cors` and pretend an opaque response proves health.
- Roll back by reverting the frontend PR / promoting the prior verified
  Vercel deployment. Do not change Render, Supabase, credentials, or proxy
  configuration to roll back.
