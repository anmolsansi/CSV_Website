from __future__ import annotations

import argparse
import re
from pathlib import Path


def block(lines: list[str]) -> str:
    return "\n".join(lines) + "\n\n"


def apply_routes() -> None:
    rows_path = Path("backend/app/routers/rows.py")
    rows = rows_path.read_text()
    schema_import = "from ..schemas import ColumnPrefIn, RowDeleteIn\n"
    service_import = "from ..services.row_queries import RowQuery, build_row_query, order_row_query\n"
    if service_import not in rows:
        if schema_import not in rows:
            raise SystemExit("rows.py import anchor changed")
        rows = rows.replace(schema_import, schema_import + service_import, 1)

    start = rows.index("    sort_column = _safe_sort_column(sort_by)\n", rows.index("def list_rows("))
    end = rows.index("    row_ids = [r.id for r in rows]\n", start)
    replacement = block([
        "    query_params = RowQuery(",
        "        sort_by=sort_by,",
        "        sort_dir=sort_dir,",
        "        ats_group=ats_group,",
        "        location_group=location_group,",
        "        search_bucket=search_bucket,",
        "        decision=decision,",
        "        sponsorship_status=sponsorship_status,",
        "        fit_category=fit_category,",
        "        seniority_level=seniority_level,",
        "        work_model=work_model,",
        "        role_family=role_family,",
        "        salary_min=salary_min,",
        "        salary_max=salary_max,",
        "        q=q,",
        "        opened_only=opened_only,",
        "        unopened_only=unopened_only,",
        "        openable_only=openable_only,",
        "        has_error=has_error,",
        "        jd_missing=jd_missing,",
        "    )",
        "    query = build_row_query(db, user.id, query_params)",
        "    total_count = query.count()",
        "",
        "    rows = (",
        "        order_row_query(query, query_params, _safe_sort_column)",
        "        .offset((page - 1) * page_size)",
        "        .limit(page_size)",
        "        .all()",
        "    )",
    ])
    rows = rows[:start] + replacement + rows[end:]
    rows_path.write_text(rows)

    crm_path = Path("backend/app/routers/crm.py")
    crm = crm_path.read_text()
    schema_import = "from ..schemas import ApplyPilotResultIn, BulkFromRowsIn, BulkUpdateIn, JobTrackUpdateIn, SavedViewIn, SessionIn, SessionUpdateIn\n"
    service_import = "from ..services.row_queries import ApplicationQuery, build_application_query, order_application_query\n"
    if service_import not in crm:
        if schema_import not in crm:
            raise SystemExit("crm.py import anchor changed")
        crm = crm.replace(schema_import, schema_import + service_import, 1)

    filtered_start = crm.index("def filtered_query(")
    filtered_end = crm.index('@router.post("/from-row/{row_id}")', filtered_start)
    filtered = block([
        "def filtered_query(db, user_id, status=None, company=None, ats_group=None, search_bucket=None, quick_range=None, date_from=None, date_to=None, min_score=None, max_score=None, follow_up_due=False, opened_not_applied=False, q=None,",
        "                   location_group=None, decision=None, sponsorship_status=None, posted_age_min=None, posted_age_max=None,",
        "                   follow_up_today=False, follow_up_overdue=False, follow_up_none=False, has_error=False, jd_missing=False,",
        "                   date_applied_from=None, date_applied_to=None, applied_only=False):",
        "    \"\"\"Compatibility wrapper for callers migrated in later R2 tickets.\"\"\"",
        "    params = ApplicationQuery(",
        "        status=status, company=company, ats_group=ats_group, search_bucket=search_bucket,",
        "        quick_range=quick_range, date_from=date_from, date_to=date_to,",
        "        min_score=min_score, max_score=max_score, follow_up_due=follow_up_due,",
        "        opened_not_applied=opened_not_applied, q=q, location_group=location_group,",
        "        decision=decision, sponsorship_status=sponsorship_status,",
        "        posted_age_min=posted_age_min, posted_age_max=posted_age_max,",
        "        follow_up_today=follow_up_today, follow_up_overdue=follow_up_overdue,",
        "        follow_up_none=follow_up_none, has_error=has_error, jd_missing=jd_missing,",
        "        date_applied_from=date_applied_from, date_applied_to=date_applied_to,",
        "        applied_only=applied_only,",
        "    )",
        "    return build_application_query(",
        "        db, user_id, params, numeric_expression=num_expr, parse_datetime=parse_dt",
        "    )",
    ])
    crm = crm[:filtered_start] + filtered + crm[filtered_end:]

    apps_anchor = crm.index('@router.get("/applications")')
    apps_start = crm.index("    query = filtered_query(", apps_anchor)
    apps_end = crm.index("    options = db.query(JobTrack.ats_group)", apps_start)
    apps = block([
        "    if sort_by not in SORT_FIELDS:",
        "        sort_by = \"opened_at\"",
        "    query_params = ApplicationQuery(",
        "        status=status, company=company, ats_group=ats_group, search_bucket=search_bucket,",
        "        quick_range=quick_range, date_from=date_from, date_to=date_to,",
        "        min_score=min_score, max_score=max_score, follow_up_due=follow_up_due,",
        "        opened_not_applied=opened_not_applied, q=q, location_group=location_group,",
        "        decision=decision, sponsorship_status=sponsorship_status,",
        "        posted_age_min=posted_age_min, posted_age_max=posted_age_max,",
        "        follow_up_today=follow_up_today, follow_up_overdue=follow_up_overdue,",
        "        follow_up_none=follow_up_none, has_error=has_error, jd_missing=jd_missing,",
        "        date_applied_from=date_applied_from, date_applied_to=date_applied_to,",
        "        applied_only=applied_only, sort_by=sort_by, sort_dir=sort_dir,",
        "    )",
        "    query = build_application_query(",
        "        db, user.id, query_params, numeric_expression=num_expr, parse_datetime=parse_dt",
        "    )",
        "    total_count = query.count()",
        "    sort_by_is_computed = sort_by in (\"priority_score\", \"triage\")",
        "    if sort_by_is_computed:",
        "        rows = query.order_by(JobTrack.id.desc()).all()",
        "    else:",
        "        rows = (",
        "            order_application_query(query, query_params, num_expr)",
        "            .offset((page - 1) * page_size)",
        "            .limit(page_size)",
        "            .all()",
        "        )",
    ])
    crm = crm[:apps_start] + apps + crm[apps_end:]
    crm_path.write_text(crm)


def mark_complete() -> None:
    guide_path = Path("docs/JOBGRID_BUILD_GUIDE.md")
    guide = guide_path.read_text()
    marker = "## JG-005 account-scoped query contract"
    if marker not in guide:
        doc_lines = [
            marker,
            "",
            "`backend/app/services/row_queries.py` owns immutable `RowQuery` and `ApplicationQuery` inputs plus the shared SQLAlchemy predicate and ordering builders. Authenticated routes supply `user.id`; query DTOs never accept account identity from client input.",
            "",
            "`GET /rows` keeps its existing parameters, pagination envelope, filter options, stats, current numeric-sort adapter, and deterministic `CsvRow.id DESC` tie breaker. The applications list keeps its existing filter names, invalid-sort fallback, computed priority/triage handling, pagination envelope, and `JobTrack.id DESC` tie breaker.",
            "",
            "The legacy `filtered_query` function remains as a compatibility wrapper for export callers until JG-006 migrates export scope. JG-005 deliberately does not change export behavior or repair the known SQLite numeric expression limitation reserved for JG-018.",
            "",
            "Verification: `python -m compileall app`, `pytest tests/test_query_contracts.py -q`, and `pytest tests/ -q` from `backend`.",
        ]
        guide_path.write_text(guide.rstrip() + "\n\n" + "\n".join(doc_lines) + "\n")

    tracker_path = Path("docs/JOBGRID_REMAINING_IMPLEMENTATION_TICKETS_FULL.md")
    tracker = tracker_path.read_text()
    old = "- [ ] [JG-005 — Extract one account-scoped query builder without changing list behavior](#jg-005)"
    new = "- [x] [JG-005 — Extract one account-scoped query builder without changing list behavior](#jg-005)"
    if old not in tracker:
        raise SystemExit("JG-005 checklist anchor changed")
    tracker = tracker.replace(old, new, 1)
    start = tracker.index('<a id="jg-005"></a>')
    end = tracker.index('<a id="jg-006"></a>', start)
    section = tracker[start:end]
    section = section.replace("**Status:** PROPOSED / unchecked", "**Status:** COMPLETED / locally verified", 1)
    section = section.replace("- [ ]", "- [x]")
    pattern = re.compile(r"(#### Ticket intake result\n\n)\*\*.*?\*\*[^\n]*")
    section, count = pattern.subn(
        r"\1**COMPLETED / locally verified.** JG-005 extracted the shared account-scoped query contract, migrated the live row and application lists, and passed the focused query-contract regression suite plus the complete backend test suite. Staging and released status are not claimed by this local completion.",
        section,
        count=1,
    )
    if count != 1:
        raise SystemExit("JG-005 ticket intake anchor changed")
    tracker_path.write_text(tracker[:start] + section + tracker[end:])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("apply-routes", "mark-complete"))
    args = parser.parse_args()
    if args.action == "apply-routes":
        apply_routes()
    else:
        mark_complete()


if __name__ == "__main__":
    main()
