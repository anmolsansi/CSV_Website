# C-09 Recovery Policy and Rehearsal — 2026-10-03

This addendum records the operator-approved recovery objectives and the recovery evidence collected while completing `C-09 — Prepare staging and prove durable operations`.

It deliberately distinguishes **portable account recovery** from **operator disaster recovery**. The complete JobGrid ZIP is valid portable recovery evidence, but it is not by itself a substitute for a PostgreSQL plus private-Storage environment restore.

## Approved recovery policy

Approved by the release operator on 2026-10-03:

- **RPO:** 24 hours
- **RTO:** 4 hours
- **Backup cadence:** daily
- **Retention:** 7 daily copies plus 4 weekly copies
- **Off-platform destination:** private owner-only Google Drive folder dedicated to JobGrid backups
- **Operational owner:** release operator / account owner
- **Coverage:** PostgreSQL logical recovery data plus matching private document bytes and integrity hashes
- **Zero-dollar constraint:** do not create a paid Vercel, Render, Supabase, or backup resource without explicit approval

The first verified complete ZIP snapshot was copied to the private off-platform destination without changing its bytes. Provider metadata confirmed the copy is not shared and has only owner access. No Drive file ID, owner email, credential, session value, or private document content is committed here.

## Portable recovery rehearsal

Source snapshot:

- complete authenticated JobGrid ZIP
- archive SHA-256: `98e402938b4fe73e6c8a25ff5102ba5209760b89bc8b839598e1ee111648f413`
- metadata schema revision: `2.13.0`
- backup format version: `2.0`
- identity rule version: `ccr-identity-1`

The immutable backup was restored into an isolated disposable local staging target consisting of a private logical database and a private object directory. This target was separate from production and contained no outbound side-effect configuration.

Observed source/restored logical record counts:

- CSV rows: 264 / 264
- URL history: 264 / 264
- audit events: 1 / 1
- user profile: 1 / 1
- document versions: 1 / 1
- all other represented sections: expected and restored counts matched
- total represented logical records: 531 / 531

Integrity comparison:

- source canonical content SHA-256: `62e5250463ce2a68cb8b2970c9c400327c4acbee36a9e3b0715273d34d402fc4`
- restored canonical content SHA-256: `62e5250463ce2a68cb8b2970c9c400327c4acbee36a9e3b0715273d34d402fc4`
- relationship references checked: 531
- unresolved relationship references: 0
- restored private objects: 1
- restored private-object bytes: 188
- restored document SHA-256: `d122b005b21a6e34f4d53e2fcfd8bd387f31c6dc3e4209a9a01f01ecd48124ad`
- object size/hash mismatches: 0
- measured local restore + verification time: 0.069425 seconds

This proves the already-versioned portable backup can reconstruct the nonempty synthetic account and exact document bytes in an isolated target.

## Private release-evidence handoff

A private release-evidence JSON file was generated outside the repository and validated against the existing `scripts/smoke_jobgrid.py` release-evidence contract.

Validator result:

- `staging_restore_content_comparison`: PASS
- `deployment_smoke_and_rollback`: PASS
- `oauth_real_provider_not_dev_login`: BLOCKED for the C-10 logout/cookie-clear portion
- `smtp_received_not_merely_queued`: BLOCKED because outbound email remained deliberately disabled during C-09
- `rollback_preserves_user_history`: BLOCKED because the previous-application-revision rollback is a C-10 exercise
- structurally failed gates: 0
- `staging_accepted`: false
- `released`: false

The evidence file and validation summary are stored only in the private off-platform backup location. Public repository evidence contains only sanitized hashes, counts, states, and blocker descriptions.

## Operator-disaster-recovery gate

The repository backup strategy requires a separate operator-disaster-recovery rehearsal in addition to the portable ZIP exercise:

1. capture PostgreSQL with an approved provider backup or compatible logical backup;
2. inventory/copy the matching private Storage objects through S3 or another supported Storage export path;
3. restore both layers into a separate disposable environment;
4. compare schema revision, nonempty record counts, normalized relationships, object counts, sizes, and hashes;
5. measure recovery against the approved RPO/RTO.

That provider-level restore is **not yet claimed as PASS**. The connected Supabase account currently exposes no existing disposable development branch. Creating a branch or project requires a provider cost check and explicit operator cost confirmation. Until that authorization is completed, C-09.07 remains partially proven rather than silently converting portable recovery into environment-disaster-recovery evidence.

## Already completed C-09 operational evidence

Separate C-09 evidence already proves:

- actual Vercel, Render, and Supabase production topology and deployed SHAs;
- real controlled Google OAuth login and a nonempty synthetic account;
- authenticated 188-byte document upload/download with exact SHA-256;
- private Storage metadata and aggregate audit consistency;
- document survival across an actual Render instance replacement/cache loss;
- complete ZIP inclusion of the exact remote document bytes;
- reminder expired-lease recovery across a deliberately enabled/restarted worker while email delivery stayed disabled, followed by cleanup and restoration to the normal disabled worker configuration;
- a safe induced document-storage readiness failure visible through direct Render `/ready` and Vercel `/api/ready` while `/health` remained healthy, followed by successful restoration;
- the synthetic document remained available after that recovery.

C-09 should remain open only for evidence that its own written contract genuinely requires and that has not yet been exercised. C-10-only gates remain explicit handoff blockers rather than C-09 failures.
