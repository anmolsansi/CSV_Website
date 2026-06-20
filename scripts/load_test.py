"""
Load testing script for JobGrid CSV Website.
Tests API performance with 10,000+ rows.

Usage:
    python scripts/load_test.py --base-url http://localhost:8000 --rows 10000
"""

import argparse
import csv
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_ROWS = 10000
BATCH_SIZE = 500


def create_test_csv(num_rows: int) -> io.StringIO:
    """Generate a CSV with num_rows test rows."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["url", "company", "title", "location", "salary", "ats_group", "search_bucket", "resume_match_score"])
    for i in range(num_rows):
        writer.writerow([
            f"https://example.com/jobs/{i}",
            f"Company {i % 500}",
            f"Software Engineer {i % 100}",
            ["Remote", "New York", "San Francisco", "Austin", "Seattle"][i % 5],
            f"{80000 + (i % 20) * 5000}",
            ["greenhouse", "lever", "workday", "taleo", "icims"][i % 5],
            ["ai", "web3", "fintech", "healthtech", "edtech"][i % 5],
            str(50 + (i % 50)),
        ])
    buf.seek(0)
    return buf


def measure_time(label: str):
    """Context manager that prints elapsed time."""
    class Timer:
        def __enter__(self):
            self.start = time.perf_counter()
            return self
        def __exit__(self, *args):
            self.elapsed = time.perf_counter() - self.start
            print(f"  {label}: {self.elapsed:.3f}s")
    return Timer()


def get_auth_cookie(base_url: str) -> dict:
    """Authenticate via dev login and return cookies."""
    resp = requests.post(
        f"{base_url}/auth/dev-login",
        json={"email": "loadtest@jobgrid.dev"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.cookies.get_dict()


def seed_data(base_url: str, cookies: dict, num_rows: int) -> dict:
    """Seed a batch of test data via CSV upload."""
    csv_buf = create_test_csv(num_rows)
    files = {"file": ("test.csv", csv_buf, "text/csv")}
    resp = requests.post(
        f"{base_url}/upload",
        files=files,
        cookies=cookies,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def test_get_rows(base_url: str, cookies: dict) -> dict:
    """Test fetching rows with pagination."""
    resp = requests.get(
        f"{base_url}/rows",
        params={"page": 1, "per_page": 100},
        cookies=cookies,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def test_filter_rows(base_url: str, cookies: dict) -> dict:
    """Test filtered queries."""
    resp = requests.get(
        f"{base_url}/rows",
        params={"page": 1, "per_page": 100, "ats_group": "greenhouse"},
        cookies=cookies,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def test_analytics(base_url: str, cookies: dict) -> dict:
    """Test analytics endpoint."""
    resp = requests.get(
        f"{base_url}/crm/analytics",
        cookies=cookies,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def test_export(base_url: str, cookies: dict) -> int:
    """Test CSV export."""
    resp = requests.get(
        f"{base_url}/rows/export",
        cookies=cookies,
        timeout=60,
    )
    resp.raise_for_status()
    return len(resp.content)


def run_concurrent_requests(base_url: str, cookies: dict, num_threads: int = 10) -> list:
    """Run concurrent read requests to simulate load."""
    results = []
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for i in range(num_threads):
            if i % 3 == 0:
                futures.append(executor.submit(test_filter_rows, base_url, cookies))
            elif i % 3 == 1:
                futures.append(executor.submit(test_analytics, base_url, cookies))
            else:
                futures.append(executor.submit(test_get_rows, base_url, cookies))

        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                results.append({"error": str(e)})
    return results


def main():
    parser = argparse.ArgumentParser(description="Load test for JobGrid API")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="Number of rows to generate")
    parser.add_argument("--concurrent", type=int, default=10, help="Concurrent request count")
    parser.add_argument("--skip-upload", action="store_true", help="Skip upload test")
    args = parser.parse_args()

    print(f"JobGrid Load Test")
    print(f"  Target: {args.base_url}")
    print(f"  Rows: {args.rows}")
    print(f"  Concurrent: {args.concurrent}")
    print()

    # Step 1: Authenticate
    print("1. Authenticating...")
    with measure_time("Auth"):
        try:
            cookies = get_auth_cookie(args.base_url)
            print(f"  Got cookies: {list(cookies.keys())}")
        except requests.ConnectionError:
            print(f"  ERROR: Cannot connect to {args.base_url}")
            print(f"  Make sure the backend is running: cd backend && uvicorn app.main:app --reload")
            sys.exit(1)

    # Step 2: Upload CSV
    if not args.skip_upload:
        print(f"\n2. Uploading {args.rows} rows...")
        with measure_time("Upload"):
            result = seed_data(args.base_url, cookies, args.rows)
            print(f"  Result: {result}")
    else:
        print("\n2. Skipping upload (--skip-upload)")

    # Step 3: Fetch rows
    print("\n3. Fetching rows (page 1, 100 per page)...")
    with measure_time("GET /rows"):
        data = test_get_rows(args.base_url, cookies)
        total = data.get("total", "?")
        print(f"  Total rows in DB: {total}")

    # Step 4: Filtered query
    print("\n4. Filtered query (ats_group=greenhouse)...")
    with measure_time("GET /rows (filtered)"):
        data = test_filter_rows(args.base_url, cookies)
        print(f"  Filtered results: {len(data.get('rows', []))}")

    # Step 5: Analytics
    print("\n5. Analytics endpoint...")
    with measure_time("GET /crm/analytics"):
        data = test_analytics(args.base_url, cookies)
        print(f"  Analytics keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")

    # Step 6: Export
    print("\n6. CSV export...")
    with measure_time("GET /rows/export"):
        size = test_export(args.base_url, cookies)
        print(f"  Export size: {size / 1024:.1f} KB")

    # Step 7: Concurrent load
    print(f"\n7. Concurrent load test ({args.concurrent} threads)...")
    with measure_time(f"Concurrent ({args.concurrent} requests)"):
        results = run_concurrent_requests(args.base_url, cookies, args.concurrent)
        errors = [r for r in results if isinstance(r, dict) and "error" in r]
        print(f"  Completed: {len(results) - len(errors)}/{len(results)}")
        if errors:
            print(f"  Errors: {len(errors)}")
            for e in errors[:3]:
                print(f"    - {e['error']}")

    print("\nLoad test complete!")


if __name__ == "__main__":
    main()
