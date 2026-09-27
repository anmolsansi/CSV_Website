from pathlib import Path

path = Path("development.md")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one occurrence, found {count}: {old[:120]!r}")
    text = text.replace(old, new, 1)


update_note = (
    "> **2026-09-27 C-01–C-03 closeout:** C-01, C-02, and C-03 are completed at the local/hosted-CI recovery-contract level. "
    "PR #159 supplied the atomic restore and complete composed ZIP recovery implementation; the C-01 closeout branch adds the missing three-interview Today cursor regression/fix and refreshes `docs/BACKUP_STRATEGY.md` to the current portable recovery contract. "
    "C-04 remains open for the broader mixed-source pagination contract (bounded interview candidate queries, cursor context/version hardening, and exhaustive mixed-source acceptance); this closeout does not claim C-04 complete.\n\n"
)
marker = "> **2026-09-24 update:** JG-001–JG-010 are completed and verified locally."
if update_note not in text:
    if marker not in text:
        raise SystemExit("top update marker not found")
    text = text.replace(marker, update_note + marker, 1)

replace_once(
    "Overall status: **Not completed — implementation exists across the roadmap, but recovery defects, queue pagination, test failures, and external acceptance remain.**",
    "Overall status: **Not completed — C-01–C-03 recovery foundation is closed, while C-04+ queue/time/CI/product/staging/release acceptance remains.**",
)

for old, new in (
    ("| 1 | Not completed | [C-01 — Preserve reproductions and freeze recovery contracts](#c-01) | None | JG-001–004, JG-023 |",
     "| 1 | Completed | [C-01 — Preserve reproductions and freeze recovery contracts](#c-01) | None | JG-001–004, JG-023 |"),
    ("| 2 | Not completed | [C-02 — Make every restore atomic](#c-02) | C-01 | JG-003, JG-056, JG-058, JG-064 |",
     "| 2 | Completed | [C-02 — Make every restore atomic](#c-02) | C-01 | JG-003, JG-056, JG-058, JG-064 |"),
    ("| 3 | Not completed | [C-03 — Deliver one complete recoverable backup](#c-03) | C-02 | JG-002, JG-004, JG-044, JG-056–058, JG-064 |",
     "| 3 | Completed | [C-03 — Deliver one complete recoverable backup](#c-03) | C-02 | JG-002, JG-004, JG-044, JG-056–058, JG-064 |"),
):
    replace_once(old, new)

for task in ("C-01", "C-02", "C-03"):
    replace_once(
        f"**Priority:** P1 prerequisite. **When:** before restore changes. **Owner:** backend implementer plus reviewer. **Status:** Not completed."
        if task == "C-01" else
        ("**Priority:** P1 data integrity. **When:** immediately after C-01. **Owner:** backend implementer. **Status:** Not completed."
         if task == "C-02" else
         "**Priority:** P1 recovery. **When:** after C-02 establishes transaction ownership. **Owner:** backend and frontend implementer. **Status:** Not completed."),
        f"**Priority:** P1 prerequisite. **When:** before restore changes. **Owner:** backend implementer plus reviewer. **Status:** Completed."
        if task == "C-01" else
        ("**Priority:** P1 data integrity. **When:** immediately after C-01. **Owner:** backend implementer. **Status:** Completed."
         if task == "C-02" else
         "**Priority:** P1 recovery. **When:** after C-02 establishes transaction ownership. **Owner:** backend and frontend implementer. **Status:** Completed."),
    )

# Mark only the C-01/C-02/C-03 numbered checkpoints. C-04 and later remain untouched.
for prefix, maximum in (("C-01", 9), ("C-02", 13), ("C-03", 15)):
    for index in range(1, maximum + 1):
        token = f"- [ ] {prefix}.{index:02d}"
        replacement = f"- [x] {prefix}.{index:02d}"
        replace_once(token, replacement)

c01_proof = (
    "**Completion evidence (2026-09-27):** The late-extension checksum/partial-restore and composed-ZIP metadata failures were preserved and repaired in PR #159, with durable regression coverage in `backend/tests/test_complete_backup.py`, `test_backup_contract.py`, and `test_document_backup.py`. "
    "The remaining independent reproduction, three scheduled interviews with `limit=2`, is now versioned in `backend/tests/test_interview_today.py`; continuation freezes the base queue `as_of`, applies the signed ordering boundary to interview items, and emits the next cursor from the final mixed-source item. "
    "`backend/app/backup_schemas.py::MODEL_FIELD_INVENTORY` is the persisted-data coverage table, and `docs/BACKUP_STRATEGY.md` records portable coverage, deliberate exclusions, compatibility, side-effect rules, and retry/reconciliation behavior. C-04 remains open for the broader bounded/context-aware mixed-source pagination acceptance.\n\n"
)
replace_once(
    "**Failure/retry:** fixtures must use fresh destinations or rolled-back test transactions. A prior failed restore may have polluted the destination; do not reuse it unknowingly. Never point tests at production.\n\n**Completion proof:** three independent baseline failures are reproduced, and the data-coverage/compatibility contract is reviewed.",
    "**Failure/retry:** fixtures must use fresh destinations or rolled-back test transactions. A prior failed restore may have polluted the destination; do not reuse it unknowingly. Never point tests at production.\n\n" + c01_proof + "**Completion proof:** three independent baseline failures are reproduced, and the data-coverage/compatibility contract is reviewed.",
)

c02_proof = (
    "**Completion evidence (2026-09-27):** PR #159 introduced `backend/app/services/backup_sessions.py` as the shared restore transaction/snapshot boundary. Base v1/v2, contacts/interviews/associations, import mappings, non-actionable F10 metadata, and bundle restore now participate in the caller-owned transaction instead of committing child layers independently. "
    "Preflight validates extensions before writes, verify-only is side-effect free, replay conflicts are checked, PostgreSQL account locking serializes competing restores, and late injected failures are re-queried from fresh sessions to prove no durable partial graph. Existing legacy readers remain supported.\n\n"
)
replace_once(
    "**Completion proof:** original checksum reproduction leaves zero imported records; every injected late failure preserves before/after counts and normalized content; successful full restores and retries pass on PostgreSQL and the supported SQLite path.",
    c02_proof + "**Completion proof:** original checksum reproduction leaves zero imported records; every injected late failure preserves before/after counts and normalized content; successful full restores and retries pass on PostgreSQL and the supported SQLite path.",
)

c03_proof = (
    "**Completion evidence (2026-09-27):** PR #159 made the ZIP exporter reuse the composed v2 metadata graph and shared snapshot, added manifest/member/hash validation, routed ZIP restore through the same composed metadata/transaction orchestration, and added failed-attempt file cleanup. "
    "`BackupRestore.jsx` distinguishes complete ZIP backup from records-only JSON and supports verify/apply for both. `backend/tests/test_document_backup.py` covers bytes/links round-trip, unsafe ZIP members, missing members, changed hashes, publish/write failure, final-commit rollback and retry; `test_complete_backup.py` proves later metadata extensions survive the bundle. "
    "`docs/BACKUP_STRATEGY.md` now documents the portable data categories, exclusions, version compatibility, limits, cross-resource crash/reconciliation boundary, retry procedure, and operator disaster-recovery distinction.\n\n"
)
replace_once(
    "**Completion proof:** a single supported user-facing backup path restores all portable metadata **and** document bytes. Metadata-only export is clearly labeled.",
    c03_proof + "**Completion proof:** a single supported user-facing backup path restores all portable metadata **and** document bytes. Metadata-only export is clearly labeled.",
)

path.write_text(text, encoding="utf-8")
print("development.md C-01/C-02/C-03 status updated")
