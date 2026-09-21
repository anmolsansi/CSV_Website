# JG-024 Release Acceptance

This document is the evidence record and runbook for JG-024, Run staging login delivery restore and rollback acceptance.

Ticket implementation can be local-ready while external staging gates are BLOCKED. A blocked gate is never reported as PASS, staging-accepted, or released.

## Release state vocabulary

- **local-ready**: JG-024 scripts, evidence validation, repository CI, and synthetic acceptance regressions are green for the recorded source SHA.
- **staging-accepted**: every gate in the evidence file is PASS for the same staging release candidate.
- **released**: a staging-accepted candidate was actually deployed to production and post-deploy evidence was recorded. JG-024 tooling never infers this state automatically.

## Current execution record

- Tracking issue: #94
- Working branch: jg-024-release-acceptance
- Intake base SHA: 0e219a2d479424126868675c51d48d4332efc446
- Local implementation state: in progress until branch CI is green.
- Staging acceptance: **BLOCKED**.
- Production release: **NOT CLAIMED**.

External blockers in this repository-connected execution:

| Gate | Status | Owner | Missing dependency |
|---|---|---|---|
| Disposable staging DB restore rehearsal | BLOCKED | release operator | Authorized staging/disposable PostgreSQL runtime is not exposed through the repository connector |
| Real OAuth provider login/logout | BLOCKED | release operator | Staging OAuth credentials and controlled provider test account are unavailable |
| SMTP sandbox receipt | BLOCKED | release operator | Explicit sending authorization, SMTP sandbox credentials, and controlled inbox are unavailable |
| Deployed backend/frontend smoke | BLOCKED | release operator | Authorized staging deployment target and deployment credentials are unavailable |
| Old-code rollback rehearsal | BLOCKED | release operator | Authorized staging candidate plus previous application revision are unavailable |

These blockers are expected operational dependencies, not synthetic test passes.

## Evidence file

Create a JSON file outside the repository when running staging acceptance. Do not commit credentials, cookies, inbox contents, access tokens, or private job data.

Every gate requires status (PASS, FAIL, or BLOCKED), owner, environment, command, expected, and actual. BLOCKED also requires an exact blocker.

Validate it with:

~~~bash
cd /path/to/CSV_Website
python scripts/smoke_jobgrid.py --release-evidence /secure/path/jg024-evidence.json
~~~

The command exits nonzero when a gate is structurally invalid or explicitly FAIL. BLOCKED gates remain visible but do not become staging acceptance.

Run the built-in deterministic regressions with:

~~~bash
python scripts/smoke_jobgrid.py --self-test-release-acceptance
~~~

Required regression names:

- staging_restore_content_comparison
- oauth_real_provider_not_dev_login
- smtp_received_not_merely_queued
- rollback_preserves_user_history

The validator also requires deployment_smoke_and_rollback before staging_accepted=true.

## 1. Disposable PostgreSQL backup and restore

Use a disposable compose project or staging database. Never point this rehearsal at the only copy of production data.

Create a deterministic rehearsal backup without pruning:

~~~bash
JOBGRID_BACKUP_FILE=backups/jg024-rehearsal.sql.gz \
JOBGRID_BACKUP_SKIP_PRUNE=true \
JOBGRID_DB_NAME=csvapp \
./scripts/backup.sh
~~~

The backup script requires a nonempty gzip, verifies gzip integrity, prints byte count and SHA-256, and writes a .sha256 sidecar.

Before restoring, collect nonempty source counts and a deterministic content hash for the owned rehearsal data. At minimum include csv_rows and job_tracks. job_tracks contains durable application notes, dates, and the row reference used by this gate. Hash canonical query output, not screenshots.

Example pattern:

~~~bash
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U postgres -d csvapp -At -c 'SELECT row_to_json(t) FROM (SELECT * FROM csv_rows ORDER BY id) t' \
  > /tmp/jg024-csv-rows.jsonl

docker compose -f docker-compose.prod.yml exec -T db \
  psql -U postgres -d csvapp -At -c 'SELECT row_to_json(t) FROM (SELECT * FROM job_tracks ORDER BY id) t' \
  > /tmp/jg024-job-tracks.jsonl

cat /tmp/jg024-csv-rows.jsonl /tmp/jg024-job-tracks.jsonl | sha256sum
~~~

Restore only to the authorized disposable target. Noninteractive use is allowed only when the operator has already confirmed the target:

~~~bash
JOBGRID_DB_NAME=csvapp \
./scripts/restore.sh --yes backups/jg024-rehearsal.sql.gz
~~~

The restore script validates gzip and the sidecar checksum before writes, uses psql -v ON_ERROR_STOP=1, and exits nonzero if the backend never becomes healthy.

Repeat the same count and canonical hash queries after restore. A PASS requires:

- source row count > 0
- restored row count equals source row count
- source and restored content SHA-256 match
- recorded backup SHA-256 is valid

## 2. Additive migration and old-code rollback rehearsal

Use the same disposable staging candidate.

1. Record the current Alembic revision and user-history count/hash.
2. Back up the database.
3. Apply current additive migrations.
4. Start the immediately previous application revision against the migrated database.
5. Confirm it starts without dropping or rewriting new columns.
6. Exercise read-only login/application-history checks.
7. Restore the current application revision.
8. Re-run the user-history count/hash.

A PASS for rollback_preserves_user_history requires a nonzero before count, identical before/after counts and hashes, successful old-code startup, retained new columns, and successful return to current code.

Do not downgrade the schema merely to make old code start. The R7 rollback boundary is application rollback first, data retention first.

## 3. Real OAuth staging login/logout

This gate must use a configured Google, Microsoft, or Apple provider. /auth/dev-login is explicitly invalid evidence.

Record:

- provider
- used_dev_login=false
- successful provider callback
- authenticated GET /auth/me status 200
- production session cookie has Secure
- production session cookie has SameSite=None
- GET /auth/logout returns redirect status 302 or 303
- logout clears session_token

Do not record the cookie value or provider access token.

## 4. Authorized SMTP sandbox receipt

Only send after explicit authorization to a controlled sandbox address.

Trigger the existing weekly digest endpoint with staging SMTP configured. A response with status=logged is not delivery evidence.

A PASS requires:

- API reports status=sent
- recipient is a controlled sandbox
- the sandbox confirms the message was received
- a non-secret received message ID is recorded
- SHA-256 of the received subject and body are recorded

Do not commit the recipient address or message body.

## 5. Deployment smoke and rollback trigger

After an authorized staging backend/frontend deployment:

~~~bash
python scripts/smoke_jobgrid.py \
  --base-url https://staging-api.example.invalid \
  --cookie 'session_token=<redacted>' \
  --no-dev-login
~~~

For the evidence file, record the actual staging URL privately, backend /health status, frontend root status, the exact rollback trigger, and the operator command/process for restoring the previous application revision.

Recommended rollback trigger: any migration/startup failure, backend health failure, frontend smoke failure, authentication regression, restore mismatch, or durable-history mismatch.

## Example blocked evidence

~~~json
{
  "release_candidate": {
    "source_sha": "REPLACE_WITH_BRANCH_SHA",
    "environment": "staging",
    "owner": "release-operator"
  },
  "gates": {
    "staging_restore_content_comparison": {
      "status": "BLOCKED",
      "owner": "release-operator",
      "environment": "staging",
      "command": "not executed",
      "expected": "nonempty source and restored counts with identical SHA-256",
      "actual": "not executed",
      "blocker": "authorized disposable staging PostgreSQL runtime unavailable"
    },
    "oauth_real_provider_not_dev_login": {
      "status": "BLOCKED",
      "owner": "release-operator",
      "environment": "staging",
      "command": "not executed",
      "expected": "real provider callback, /auth/me 200, secure cookie, logout clears cookie",
      "actual": "not executed",
      "blocker": "staging provider credentials/test account unavailable"
    },
    "smtp_received_not_merely_queued": {
      "status": "BLOCKED",
      "owner": "release-operator",
      "environment": "staging",
      "command": "not executed",
      "expected": "authorized sandbox receives the digest",
      "actual": "not executed",
      "blocker": "sending authorization and sandbox inbox unavailable"
    },
    "rollback_preserves_user_history": {
      "status": "BLOCKED",
      "owner": "release-operator",
      "environment": "staging",
      "command": "not executed",
      "expected": "old code starts and durable history hash is unchanged",
      "actual": "not executed",
      "blocker": "authorized staging candidate and prior revision unavailable"
    },
    "deployment_smoke_and_rollback": {
      "status": "BLOCKED",
      "owner": "release-operator",
      "environment": "staging",
      "command": "not executed",
      "expected": "backend/frontend smoke pass with documented rollback trigger",
      "actual": "not executed",
      "blocker": "authorized staging deployment target unavailable"
    }
  }
}
~~~

## Security rules

- Never commit OAuth secrets, SMTP credentials, JWTs, session cookies, provider tokens, private inbox content, or production database URLs.
- Use synthetic/non-sensitive staging data for restore evidence.
- Store detailed evidence in an access-controlled location and commit only non-secret summaries.
- A missing external dependency is recorded as BLOCKED, never converted to PASS.


---

## JG-028 local F1 Today acceptance

This section records **local/repository acceptance only** for the F1 Today group. It does not convert the external staging OAuth, SMTP, restore, deployment, or rollback gates above into PASS.

Tracking issue: #106  
Working branch: `jg-028-today-acceptance`  
Status: **PASS — repository CI run #204**

### Deterministic expected-versus-observed contract

| Acceptance check | Expected result | Evidence | Current status |
|---|---|---|---|
| 60-action membership | 25 visible: 12 overdue, 8 due today, 5 undated | `test_fixed_fixture_membership_and_count_parity` | PASS — CI #204 |
| Include snoozed | 33 visible: 16 overdue, 12 due today, 5 undated | same regression | PASS — CI #204 |
| Queue SQL bound | 12 distinct sourced manual items still build with exactly 3 SELECTs | `test_no_n_plus_one_queue_queries` | PASS — CI #204 |
| PostgreSQL plans | real membership plans are index-backed; owner+due probe exposes the composite WorkItem index | `test_today_postgres_query_plans_use_owner_due_indexes` | PASS — CI #204 |
| Source deletion | source FK detaches while manual description/action remains | `test_today_source_detachment_preserves_manual_action` | PASS — CI #204 |
| Account timezone change | same UTC due instant moves into the correct local-day queue after timezone change | `test_today_timezone_change_recomputes_membership` | PASS — CI #204 |
| Backup/restore | destination owner reconstructs 25 visible / 33 including-snoozed counts with 8 destination-scoped overrides | `test_restore_reconstructs_today_items` | PASS — CI #204 |
| Saved-view full order | first 20 filtered/sorted rows span browse pages 1 and 2; replay creates 0 duplicates | `test_saved_view_page_two_uses_full_filtered_order_and_no_duplicate_actions` | PASS — CI #204 |
| Five-action persistence | confirmed complete/snooze/reschedule/from-view outcomes survive a fresh queue read; follow-up does not become applied | `test_five_action_workflow_no_lost_changes` | PASS — CI #204 |
| Browser work session | detail round-trip plus complete, snooze, reschedule, failure/retry survives reload | JG-028 case in `frontend/tests/today.spec.ts` | PASS — CI #204 |
| Preserved tab conflict behavior | blocked popups still record no false visit and successful tabs keep `window.opener=null` | existing `release-workflows.spec.ts` / application-memory coverage | PASS — CI #204 |

### Observed repository validation

GitHub Actions CI run **#204** validated commit `fd683d399e42b136ce704c3e86565cb4dfd57c82` on the JG-028 pull request:

- backend pytest: **367 passed**;
- Chromium Playwright: **141 passed**;
- frontend production build: **PASS**;
- backend compile check: **PASS**;
- preserved tab-helper/release workflow checks inside the E2E job: **PASS**.

An earlier run (#201) correctly rejected an over-specific PostgreSQL planner assertion after **366 tests passed and one JG-028 plan assertion failed**. The acceptance was corrected to record PostgreSQL's real cost-based queue plan while separately proving the owner/due composite index is eligible. No runtime query contract or schema was changed to make the test pass.

### Baseline and Today session record

The pre-Today workflow remains distributed across Job Links, Saved Views, Applications, and existing follow-up controls. JG-028 does **not** have a controlled human-session timing baseline for that workflow, so no speed percentage or time saving is claimed.

The deterministic Today browser session records these concrete observations:

- five intended work-session outcomes are exercised: inspect detail context, complete, snooze, reschedule, and recover a failed completion;
- eight Today control activations are required because snooze and reschedule each require explicit confirmation and the synthetic failure requires one retry;
- four mutations receive confirmed server success in that browser fixture;
- the synthetic failed mutation leaves its item visible until a successful retry;
- after reload, all confirmed removals remain removed and the detail-only item remains available.

The acceptance question is therefore whether actions are explicit, recoverable, and preserved across navigation/reload. It is **not** whether an unmeasured baseline was faster or slower.

### Rollback

JG-028 adds no migration. The only production-code change is bounded eager loading for Today manual-action source metadata. If that change must be reverted, persisted WorkItems, WorkItemOverrides, and JobTrack follow-up dates remain compatible. The existing F1 UI rollback remains disabling the Today route/navigation without deleting user data.
