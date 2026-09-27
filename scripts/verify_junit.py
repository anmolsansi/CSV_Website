#!/usr/bin/env python3
"""Fail release CI when a JUnit report is empty or contains disallowed outcomes."""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


def _summary(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise ValueError(f"{path} does not contain a JUnit testsuite")

    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--label", default="release test report")
    parser.add_argument("--min-tests", type=int, default=1)
    parser.add_argument("--max-skips", type=int, default=0)
    args = parser.parse_args()

    if args.min_tests < 1:
        parser.error("--min-tests must be at least 1")
    if args.max_skips < 0:
        parser.error("--max-skips must be non-negative")
    if not args.report.is_file():
        raise SystemExit(f"{args.label}: missing JUnit report: {args.report}")

    try:
        summary = _summary(args.report)
    except (ET.ParseError, ValueError) as exc:
        raise SystemExit(f"{args.label}: invalid JUnit report: {exc}") from exc

    print(
        f"{args.label}: tests={summary['tests']} failures={summary['failures']} "
        f"errors={summary['errors']} skipped={summary['skipped']}"
    )

    problems: list[str] = []
    if summary["tests"] < args.min_tests:
        problems.append(
            f"expected at least {args.min_tests} tests, observed {summary['tests']}"
        )
    if summary["failures"]:
        problems.append(f"failures={summary['failures']}")
    if summary["errors"]:
        problems.append(f"errors={summary['errors']}")
    if summary["skipped"] > args.max_skips:
        problems.append(
            f"skipped={summary['skipped']} exceeds allowed {args.max_skips}"
        )

    if problems:
        raise SystemExit(f"{args.label}: rejected: " + "; ".join(problems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
