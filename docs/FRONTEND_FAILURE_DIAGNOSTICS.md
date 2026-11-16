# Frontend-wide availability, warning and error diagnostics

## Design and scope

All application pages and components use the shared Axios client in
`frontend/src/api/client.js` (including CRM imports and contacts). Its response
interceptor classifies and logs rejected HTTP requests once before returning the
original rejection to each caller. No caller gets a silently repeated request.

`frontend/src/api/authAvailability.js` distinguishes:

| Signal | Classification and behavior |
| --- | --- |
| 429 with `x-render-routing: hibernate-rate-limited` | Verified Render edge throttle for **that response**. Show a service warning. |
| 429 with exact FastAPI `detail: Too many attempts. Try again later.` | Application email-auth limit. Keep it on the login form, not in the global outage banner. |
| Other 429 | Unknown throttle. Do not attribute it to Render or the app. |
| 408 / 502 / 503 / 504 | Temporary unavailability. |
| 500+ | Server failure in the global warning and diagnostic log. Existing component-specific backend detail messages remain available to affected dialogs. |
| Network error without a response | Connection failure, not a definite outage of Render. |
| HTTP 401/403 | Preserve existing redirect/auth-state behavior. These aren't operational outages. |
| Validation 4xx | Preserve the page's existing field-level feedback. |
| Explicitly canceled Axios request | No outage warning or error log. |

`Retry-After` supports positive delta-seconds and HTTP-date formats, bounded to
1–3,600 seconds. If no valid value exists, 429 warnings use a 60-second UI cooldown.
On `/auth/me`, 429s and connection failures still leave the session **unknown**;
the app does not treat them as logout or automatically retry. Email-login POST
cannot be submitted concurrently, and no POST is automatically replayed.

The app shell displays one dismissible, accessible service warning above the
authenticated page for transient failures from **any endpoint**. It carries
general, non-sensitive text and an optional cooldown. Reload is manually initiated
and can lose unsaved edits, so users should first verify whether a failed change
was already committed. Other page-specific failures and validation messages
continue working. A single noisy backend request cannot force repeated logins.

## Logging coverage and privacy

- Every Axios API failure produces **one** local `console.warn` or
  `console.error` diagnostic with event type, known classification, HTTP status,
  method, coarse resource group and bounded retry delay. HTTP 401/403 are omitted
  to avoid normal logged-out traffic appearing as an outage.
- All `ToastProvider` warning/error toasts from pages and components are logged
  using only their severity, never their free-text message.
- Uncaught browser errors and unhandled promises are recorded by global listeners
  installed in `main.jsx`; React render failures use `ErrorBoundary`.
- The shared Axios client covers all API modules, including `imports.js`,
  `contacts.js`, and `openJobs.js`; no page-by-page login-specific
  interception or duplicated generic retry logic is needed.
- Diagnostics remain in the **browser console only**. They are not uploaded to
  Render, stored in localStorage, forwarded to a third party, or persisted.
  There is no extra paid service or automatic retry mechanism.
- Never log raw error objects, Axios config, full URLs, query parameters,
  headers, request/response bodies, credentials, emails, user content, exception
  messages or stack traces. Console event data uses a restricted resource group
  such as `crm` rather than a record ID or company path.
- **Limitation:** local form-validation failures displayed without using the
  shared API or ToastProvider are not automatically logged. Capturing arbitrary
  caught exceptions in every component would need explicit instrumentation, and
  blindly capturing all messages would risk exposing private job data.

## Verification

Run from `frontend`:

```bash
node --test unit/*.test.mjs
npm run build
npx playwright test tests/render-free-session-recovery.spec.ts tests/global-service-diagnostics.spec.ts --project=chromium
```

The new unit tests cover status and provider attribution, fixed and HTTP-date
`Retry-After`, 401/cancel exclusion, and log redaction. Playwright simulates
429 on Archive and 503 on Analytics. Run full backend/frontend CI before merge.

For a real failure, use Chrome DevTools Network to inspect **that request's**
status, response headers, and content type; Render Events/Logs can provide
corroboration. When `x-render-routing` is absent, do not label 429 as Render
hibernation. Avoid authentication retry floods during diagnosis.

## Release and rollback

This is a frontend-only change. Render Free remains `plan: free` and the
existing Render service, Supabase data, Vercel routing, cookies and auth limits
remain unchanged. GitHub merges may auto-deploy; confirm frontend and backend
providers' rollout policies before merging. Smoke-test a normal session and
one controlled failure after deployment. Revert the PR/previous verified
Vercel deployment to roll back the frontend behavior. Do not modify the
database, secret variables or hosting plan.
