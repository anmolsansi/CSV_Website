# Free email/password login setup: Brevo HTTPS API + Render Free

Email/password login is an opt-in alternative to the existing OAuth flow. Google remains enabled.
Render Free blocks outbound SMTP ports 25, 465 and 587. Use Brevo's HTTPS API on port 443 instead.

## Free limits
Brevo Free: 300 total emails per day (includes account verification and password resets).
No credit card required for the free tier. A verified sender and transactional sending
approval are prerequisites. Free tiers and acceptance rules may change over time.

## Step-by-step setup

1. **Create Brevo Free account:** https://www.brevo.com/. Complete any required verification
   and ensure transactional API sending is activated. Do not enable any paid plan/add-on.
2. **Verify a sender:** Brevo Settings > Senders, Domains & Dedicated IPs. A domain you own
   is recommended for SPF/DKIM/DMARC. If using a Gmail/Yahoo address, check the actual
   sending identity Brevo allows: free-mail senders may be rewritten/rejected.
3. **Create API key:** Brevo > SMTP & API > API Keys > Generate a new API key. Keep it
   secret. This is an **API key**, NOT a Brevo SMTP password.
4. **Configure Render environment (backend jobgrid-api)**:
   EMAIL_AUTH_TRANSPORT=brevo
   BREVO_API_KEY=(your private Brevo API key)
   BREVO_SENDER_EMAIL=(your Brevo-verified sender address)
   BREVO_SENDER_NAME=JobGrid
   EMAIL_PASSWORD_AUTH_ENABLED=false   # remain OFF until migration + send test
   FRONTEND_URL=https://csv-website-steel.vercel.app  # check your canonical frontend
   Never commit your API key, paste it into chat or set it as VITE_*.
   Legacy SMTP_HOST/SMTP_* credentials are not used for this auth flow.
5. **Database migration:** After snapshot/backup, apply Alembic revision 020 to the
   configured PostgreSQL DB using a trusted admin client/runner:
   cd backend && alembic current && alembic upgrade head && alembic current
   Check revision 020 and presence of password_credentials, email_action_tokens,
   email_auth_rate_limits. **Render Free does not provide interactive shell**; use
   your local machine with secure DB credentials and reachable network or an approved
   migration runner, not a public migration endpoint. Never run downgrade on live data.
6. **Preflight:** In Brevo's UI send a test transactional email with your sender.
   Confirm inbox delivery, including spam folder. A 201 from Brevo means accepted,
   not guaranteed delivered. If sending isn't activated, fix that before enabling auth.
7. **Enable backend:** Set EMAIL_PASSWORD_AUTH_ENABLED=true on Render, deploy and
   verify backend health and error logs. Keep TEST_AUTH=false in production.
8. **Enable frontend:** In Vercel project > Settings > Environment Variables set
   VITE_ENABLE_EMAIL_PASSWORD_AUTH=true for **Production**, then trigger a fresh
   main-branch redeploy. Vite values are compiled at build time.
9. **Acceptance tests:** Use a fresh mailbox to register, receive a verification
   message, verify, sign in, sign out, reset password; verify wrong passwords and
   expired tokens. Separately test existing Google account: "Forgot password?"
   creates a password for the same user only after mailbox control. Inspect
   login cookies and confirm no plaintext passwords, tokens or API keys in logs.
10. **Rollback:** Disable Vercel frontend flag and redeploy; disable Render backend
    flag. Keep additive database tables, never run a destructive downgrade.

## Configuration contract

- EMAIL_AUTH_TRANSPORT=smtp (default): existing SMTP transport for local/non-Render.
- EMAIL_AUTH_TRANSPORT=brevo: Brevo HTTPS API, fail closed unless BOTH BREVO_API_KEY
  and BREVO_SENDER_EMAIL are present.
- BREVO_SENDER_NAME defaults to JobGrid.
- EMAIL_PASSWORD_AUTH_ENABLED defaults to false.
- API call: POST https://api.brevo.com/v3/smtp/email, application/json, api-key header,
  with sender, to, subject and htmlContent; accepts HTTP 201.
- The feature deliberately does not alter digest/reminder email transports or billing.

## Tests

cd backend && pytest tests/test_email_password_auth.py tests/test_production_config.py tests/test_schema_parity.py
cd frontend && npm ci && npm run build

Do not remove Google OAuth to work around a 429; Vercel/Render edge throttling may
also affect email authentication and needs separate investigation.
