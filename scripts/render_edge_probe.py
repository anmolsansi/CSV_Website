"""Bounded, read-only diagnosis of the JobGrid Render/Vercel hosting path.

No credentials, POSTs, retries, response bodies or unbounded polling.
"""

import argparse
from datetime import datetime, timezone
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DIRECT_HEALTH = "https://jobgrid-api.onrender.com/health"
VERCEL_HEALTH = "https://csv-website-steel.vercel.app/api/health"


def _header(headers, name):
    # Even provider headers are untrusted. Do not log arbitrary values verbatim.
    value = headers.get(name, "") if headers else ""
    return str(value).replace("\r", "").replace("\n", "")[:80]


def probe(url, *, timeout=8, opener=urlopen):
    """Issue exactly one unauthenticated GET and report non-sensitive metadata."""
    request = Request(url, headers={"User-Agent": "jobgrid-edge-probe/1.0", "Cache-Control": "no-cache"}, method="GET")
    try:
        with opener(request, timeout=timeout) as response:
            status = response.status
            headers = response.headers
    except HTTPError as error:
        status, headers = error.code, error.headers
    except (URLError, OSError, TimeoutError) as error:
        return {"status": None, "error_type": type(error).__name__}
    return {
        "status": status,
        "x_render_routing": _header(headers, "X-Render-Routing"),
        "retry_after": _header(headers, "Retry-After"),
        "content_type": _header(headers, "Content-Type"),
    }


def diagnose(direct, vercel):
    results = [direct, vercel]
    if any(item.get("status") == 429 and item.get("x_render_routing", "").lower() == "hibernate-rate-limited" for item in results):
        return "confirmed_render_hibernation_throttle"
    if any(item.get("status") == 429 for item in results):
        return "unattributed_429_review_response_headers_and_provider_logs"
    if all(item.get("status") == 200 for item in results):
        return "healthy_at_probe_time_not_a_long_term_guarantee"
    return "inconclusive_check_deploys_readiness_and_provider_events"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=8, help="Per request timeout seconds, 1–15 (default 8)")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 15:
        parser.error("--timeout must be between 1 and 15 seconds")

    direct = probe(DIRECT_HEALTH, timeout=args.timeout)
    vercel = probe(VERCEL_HEALTH, timeout=args.timeout)
    classification = diagnose(direct, vercel)
    print(json.dumps({
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "direct_render_health": direct,
        "vercel_rewrite_health": vercel,
        "classification": classification,
        "note": "One GET per origin, no passwords, cookies or response bodies; does not verify login.",
    }, indent=2, sort_keys=True))
    return 0 if classification.startswith("healthy_at_probe_time") else 2 if any(x.get("status") == 429 for x in (direct, vercel)) else 3


if __name__ == "__main__":
    raise SystemExit(main())
