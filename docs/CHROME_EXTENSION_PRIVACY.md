# JobGrid Job Memory — draft privacy disclosure

Prepared 2026-11-05 from main `569835c`, for EXT-49. **Draft for owner review;
not an approved public policy or store submission.** Publisher, policy/support
locations and operator retention commitments are not yet supplied. This draft
must be approved and made publicly available before an active distribution.

## What the current ZIP does

`jobgrid-pilot-v0.1.0.zip` is an inactive shell. It contains only `manifest.json`
and `popup.html`. It has no background worker, bridge, content scripts,
tracking, network calls, account connection or application-saving controls.
It displays “Not connected yet” and “No browsing is tracked by this shell.”
It declares permissions but does not exercise them or request optional hosts.
Do not describe it as a functioning job-history companion in a store listing.

Version: `0.1.0`. SHA-256:
`1c4e2cc5d428cec9d33596464da0c324e14deaf891be8f8f7049cd5eb4c566d1`.
Unpacked IDs depend on the installation path and are not a stable store ID.

## Separate development implementation

The following describes the checked-in **development** worker/popup, not
functionality activated in the release ZIP. A future active package requires
its own source/hash review and acceptance; do not apply these statements to
an unreviewed build.

After a person grants an exact site and separately opts in, the development
extension can recognize supported public job-detail pages on:

- `https://boards.greenhouse.io/*`
- `https://job-boards.greenhouse.io/*`
- `https://jobs.lever.co/*`

It extracts candidate public job title and employer metadata on qualifying
top-frame routes. A deliberate current-tab gesture also supports a validated
public HTTP(S) job page. This is not permission to collect general browsing
history. No history import, form-answer capture, application submission,
password/cookie reading, frame scraping or page-to-extension command relay
is implemented. Job titles and employers are untrusted candidates; a person
can edit them and must explicitly confirm an applied action. A visit is not
an application, and a possible employer match is not proof of an application.

The development extension uses one selected signed-in JobGrid tab and its
same-origin `/api` proxy. Current trusted release frontend configuration is
`https://csv-website-steel.vercel.app`; the development fixture manifest is
local-only. The browser attaches its existing session cookie to the app's
request. The extension does not read, export or store the cookie, provider
password, OAuth token or signing secret. An account switch, logout or missing
tab invalidates the connection; the server resolves the owner from the cookie.

## Information handled and why

| Information | Purpose and location in the development flow |
|---|---|
| Public job URL, employer and title candidates | Check the selected account's job/company memory; title/employer may be edited before explicit applied confirmation |
| Canonical job URL, hash, first visit time, owner relationship | Durable server visit memory; limited to 10,000 visits per account; not a general browser history database |
| Job URL, employer/title, applied time, track/lifecycle facts | Server application history created or reused only after explicit confirmation; original applied time and advanced status are preserved on replay |
| Account ID/limited label, selected app tab, check results | Account-bound connection and private warning results in trusted extension session context |
| Stable request UUID and pending apply payload | Recover an ambiguous confirmed save by deliberate same-key retry; at most one unresolved pending apply for up to 24 hours |
| Per-site opt-in and pause preference | Local browser preference storage; sites start off |
| Safe action/outcome/count/timing diagnostics | Operation and failure evidence; no raw URL/query, cookie, employer/title, form answers or private account label may be logged |

Canonicalization removes only specified tracking parameters (`utm_*`, `gclid`,
`fbclid`), default ports and fragments; meaningful path/query values remain.
A URL/hash may still identify a job and is treated as private account data.
The service validates private/unsafe URLs; it does not fetch arbitrary URLs
as a side effect of recording a visit or an application.

## Storage, access and transfers

The development extension uses `storage.local` for site/pause preferences and
trusted-extension `storage.session` for private account/request state. It does
not put private history in `storage.sync`. Success, disconnect and account
changes clear private pending state. A full browser restart clears browser
session storage. Worker suspension requires a fresh connection and validation;
there is no hidden keepalive, automatic apply replay or offline write queue.

The selected account's server is the durable source of visit/application facts.
Requests use the fixed trusted app origin, HTTPS in release configuration, and
existing cookie authentication; a page cannot supply the authoritative owner.
The documented hosting path uses Vercel, Render and private Supabase database/
storage services. This document does not establish current provider access,
processor terms, at-rest encryption configuration, staff access controls or
an approved retention schedule. The distribution owner must verify and disclose
those practices for the selected deployment before publishing the policy.

The extension code contains no advertising, data-broker export, analytics
collector or sale mechanism. Operator sharing/access and legal retention
commitments require owner confirmation; this draft makes no unverified promise
about private production operations or the wider JobGrid service.

## Pause, deletion, retention and backups

Pause or remove a site opt-in to stop future observation; revoking a host grant
unregisters that site's script. Disconnect clears the selected browser connection.
Disable or remove the extension through Chrome to stop it. Removing the current
inactive shell changes no server data. Removing a development installation clears
its extension browser state, not history already saved on the server.

The confirmed Forget visits action deletes **only the selected account's external
visit records**. It preserves applied/saved jobs, application events, CSV clicked
facts, import URL history and operational apply receipts. Repeating forget returns
zero. Account deletion cascades account-owned records and does not affect others.
The visit cap is a quota, not a time-based expiry or an automatic deletion promise.
No approved automatic server retention duration or off-platform backup schedule
has been established by EXT-49; the operator must supply these commitments.

A user-selected complete v2 ZIP or v2 JSON backup can include visit metadata.
Restoring an older backup may bring forgotten visits back. Complete ZIP includes
supported document bytes; records-only JSON does not. Apply receipts, cookies,
OAuth identities and server secrets are not portable backup data. Users and
operators must handle exported backups privately and manage their copies; an
extension uninstall or Forget visits does not erase exported/off-platform copies.

## Review and contact status

Publisher/distribution owner, stable store item ID, approved public policy URL,
approved support URL/contact and operator retention/access terms are **not
provided**. These are required decisions, not placeholder production identities.
Do not submit this draft, invent contact details or claim that store review has
approved it. Store preparation details are in the [extension README](../extension/README.md).

## Permission and host review for the distribution owner

| Manifest permission | Development purpose | Current inactive ZIP use |
|---|---|---|
| `storage` | Persist opt-in/pause preferences and bounded trusted session context | Not exercised |
| `activeTab` | Deliberate current-tab check/mark-applied gesture | Not exercised |
| `scripting` | Inject fixed bridge into selected app tab; register public metadata reader for granted/opted-in sites | Not exercised |
| Optional Greenhouse/Lever origins listed above | Read public metadata only on supported enabled detail pages | No grant requested; no script |
| Optional `https://csv-website-steel.vercel.app/*` | Communicate only through the selected signed-in app tab/proxy | No grant requested; no connection |

The release manifest requests no `tabs`, `history`, `cookies`, `<all_urls>`,
external messaging, arbitrary API host or localhost scope. A requested capability
still needs an honest necessity explanation: the inactive artifact does not
currently use the three required permissions. Do not certify them as necessary
for a functioning shipped feature or expand them to make a test pass. A changed
active candidate needs permission-minimization review, new package/hash and
actual Chrome/account acceptance before its listing answers can be finalized.

| Distribution field | Current verified status |
|---|---|
| Publisher legal/distribution identity and authorized submitter | NOT PROVIDED |
| Stable store item / extension ID | NOT PROVIDED; do not use a temporary unpacked-profile ID |
| Approved publicly accessible policy location | NOT PROVIDED; this repository draft is not an approved endpoint |
| Approved support/contact location | NOT PROVIDED; no contact mailbox or response promise is invented |
| Retention, backups, operator access and data-sharing commitments | Owner confirmation required for selected deployment |
| Store submission / review / approval | NOT PERFORMED / NOT CLAIMED |

### Review references

Reviewed 2026-11-05: Chrome's [privacy-fields guidance](https://developer.chrome.com/docs/webstore/cws-dashboard-privacy)
asks for a clear purpose, justification of declared permissions, remote-code
answers and accurate data-use disclosures. Its [User Data FAQ](https://developer.chrome.com/docs/webstore/program-policies/user-data-faq)
includes local processing in data handling and describes collection/use/sharing
and access/deletion/retention disclosures. These sources guide review; they do
not approve this draft or establish private operator practices.

## Recorded disclosure review (EXT-49.04)

Review scope: release `manifest.json`/`popup.html`, package allowlist/negative tests,
public configuration, development bridge/worker/storage contracts and the
composed backup/forget implementation at main `569835c`.

| Check | Result and limit |
|---|---|
| Release functionality versus statements | PASS for draft accuracy: inactive shell explicitly identified; no active check/apply claim |
| Exact permission/host enumeration | PASS: three named permissions and four exact optional HTTPS origins; localhost remains development-only |
| Local/session/private data distinction | PASS for source description; operator access, processors and retention still need approval |
| Forget, uninstall and older-backup behavior | PASS for source description; uninstall is not server erasure and restore may reintroduce visits |
| No form/cookie/history-import claim | Matches the extension boundaries and tests; existing app-cookie attachment is explicitly distinguished from cookie capture |
| Public privacy/support link resolution | BLOCKED: approved locations have not been supplied; no dummy endpoints were tested as real |
| Publisher/stable store identity | BLOCKED: not supplied; unpacked path-derived IDs are not substituted |
| Minimal functional package/permission necessity | BLOCKED FOR SUBMISSION: current shell does not use its declared required capabilities; active candidate/review required |
| Remote executable code | None in the release artifact; it contains no script at all. Development executable code is packaged locally, not remotely loaded |
| Package contents | Explicit two-file allowlist, deterministic checksum and independent ZIP decoder/negative tests; no profile/key/private history inputs |
| Listing, screenshots and public-policy approval | DRAFT / NOT ACCEPTED; owner must approve the exact functioning candidate and public disclosures |

Chrome's [listing guidance](https://developer.chrome.com/docs/webstore/cws-dashboard-listing)
identifies a store icon and at least one screenshot among the listing inputs.
No image of an unshipped active feature is presented as the current artifact.
Review those assets against the accepted candidate before preparing a store
upload. No store action was performed during this review.

The operator should not tick data-use certification boxes merely because this
source audit passed. The selected public policy, actual deployment practices,
minimal permissions, displayed feature claims and exact uploaded package must
agree. Missing external proof keeps EXT-49 acceptance open even though its
review documents have been prepared.
