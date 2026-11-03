# Dashboard filters

The Dashboard sends filter state to `GET /rows`. Filtering happens on the server before pagination, so the table, result count, and **Open top 5 unopened** all use the same filtered result.

## ATS group

`ats_group` limits rows to the selected ATS group, such as Ashby, Greenhouse, or Lever. Matching is case-insensitive.

## Unique company

Enable **Unique company** to keep at most one row for each known company in the current filtered result.

Company identity for this filter is intentionally simple and deterministic:

- `company_guess` is trimmed and compared case-insensitively.
- `Acme`, `ACME`, and ` acme ` are treated as the same company.
- The retained row is the first row for that company in the active Dashboard sort order.
- Rows with a blank or missing `company_guess` are not collapsed together because JobGrid cannot safely prove they belong to the same company.
- Deduplication runs after ordinary filters. For example, `ATS group = ashby` plus **Unique company** chooses one row per company from the Ashby matches, not from the full account dataset.

Wire parameter: `unique_company=true`.

## Confirmed USA

Enable **Confirmed USA** to keep only rows whose existing `is_usa_role` value is explicitly affirmative.

The accepted affirmative values are `true`, `yes`, and `1`, with surrounding whitespace and letter case ignored. Blank, missing, negative, or unknown values are excluded.

Wire parameter: `confirmed_usa=true`.

## Combining filters

The filters compose. For example, selecting:

- ATS group: `ashby`
- Unique company: enabled
- Confirmed USA: enabled

shows only USA-confirmed Ashby jobs, with at most one known-company row in the active sort order.

## Open top 5 unopened

**Open top 5 unopened** does not reuse only the rows currently visible on the page. It requests the first five server-side matches with the current Dashboard sort and filters, plus `unopened_only=true` and `openable_only=true`.

This means the same ATS, Unique company, Confirmed USA, search, location, sponsorship, and other active Dashboard filters constrain the five links that are opened.

## Implementation boundaries

- `frontend/src/pages/Dashboard.jsx` owns the controls and passes the active filter state to normal row loading and the top-five action.
- `frontend/src/api/queryParams.js` maps `uniqueCompany` to `unique_company` and `confirmedUsa` to `confirmed_usa`.
- `backend/app/routers/rows.py` exposes the two query parameters.
- `backend/app/services/row_queries.py` is the shared server-side row filtering implementation.

No database migration or new dependency is required. Both filters use existing `CsvRow` data.

## Verification

Focused backend coverage lives in `backend/tests/test_query_contracts.py`. Browser coverage for URL restoration, control state, and top-five forwarding lives in `frontend/tests/filter-export-parity.spec.ts`.

## Country and city

Country and City columns are stored as `location_country` and `location_city` (no new database migration). The import preview maps source headers `country`, `city`, and `job_location` to the existing fields automatically. The classic CSV upload also recognizes these aliases.

Dashboard Country and City dropdowns are independent, composable filters. Values are case-insensitive whole tokens separated by semicolons. For example, Country = United States matches `United States` and `Canada; United States` but not a partial country name. The option menus split multi-location fields so each individual choice appears once.

Use Group by → Country or City to group by the **full original field**. A job with multiple countries appears once under its combined label (for example, `Canada; United States`), and group totals reflect unique jobs rather than counting that job twice. Blank locations group as Unknown. Group counts, pagination, top-five actions, saved-view URLs, and filtered CSV/JSON exports share the same country/city filters.

Wire parameters: `location_country`, `location_city`, and `group_by=location_country|location_city`. Grouping is a dashboard display choice, not an exported CSV grouping operation.
