# Verified email/password login

This is an opt-in authentication alternative to Google/Apple/Microsoft OAuth.
Nothing changes for existing users until **both** feature flags are enabled.

## Architecture and security

- Backend: /auth/email/register, /verify, /login, /forgot, /reset.
- New account records are created **only after mailbox verification**. Registration for an existing email never overrides or links a password to an OAuth account.
- Existing OAuth users may select "Forgot password?" to receive a one-time password setup link **at their already registered email address**. Their original account and data remain intact.
- Passwords use Argon2id. Only password hashes are stored.
- Verification/reset tokens are cryptographically random, stored as SHA-256 hashes, single-use and expire after 30 minutes.
- Shared PostgreSQL/SQLite fixed-window counters restrict attempts per email and network peer; rate-limit responses have Retry-After. No client-side automatic retries.
- Session cookies retain the existing HttpOnly, Secure and SameSite policy. Authentication success responses set Cache-Control: no-store.
- Links carry tokens in URL fragments to keep secrets out of Vercel and CDN request logs.
- JSON-only requests and explicit Origin checks limit cross-site login attempts.

## Enable in production

1. Review PR, run database migration to head (revision 020), and verify that the database backup/recovery plan is current. Migration is additive.
2. Configure a working SMTP delivery service in Render using SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, and EMAIL_FROM. Never commit these values to Git. Verify SPF/DKIM/DMARC and test on a synthetic mailbox. Existing reminder email flags are independent.
3. Set EMAIL_PASSWORD_AUTH_ENABLED=true on Render **only after the migration and SMTP test**.
4. Set VITE_ENABLE_EMAIL_PASSWORD_AUTH=true on Vercel Production and rebuild the frontend. Vite variables are build-time, not runtime.
5. Test sign-up, verification, sign-in, wrong passwords, rate limiting, forgot/reset, pre-existing OAuth account, cookie policy and logout with controlled test accounts.
6. Do not disable Google OAuth until controlled acceptance confirms password auth works. A 429 imposed by Vercel/Render edge security may still affect /api/auth/email/* and must be investigated independently.

## Local testing

Install backend dependencies and run:
- cd backend && pytest tests/test_email_password_auth.py tests/test_production_config.py tests/test_schema_parity.py
- cd frontend && npm ci && npm run build

Production rollback: turn off frontend flag first, then backend flag. Keep additive schema and existing password credentials; do not downgrade a live database.
