#!/usr/bin/env bash
set -euo pipefail

: "${JOBGRID_BASE_URL:?Set JOBGRID_BASE_URL, for example https://jobgrid.example.com}"
: "${JOBGRID_SESSION_COOKIE:?Set JOBGRID_SESSION_COOKIE to the authenticated session cookie value}"

BUNDLE="${1:?Usage: portable-restore.sh <bundle.zip> [verify_only|merge_missing]}"
MODE="${2:-verify_only}"

case "${MODE}" in
  verify_only|merge_missing) ;;
  *) echo "Mode must be verify_only or merge_missing" >&2; exit 2 ;;
esac

curl --fail --silent --show-error \
  --cookie "session=${JOBGRID_SESSION_COOKIE}" \
  --form "file=@${BUNDLE};type=application/zip" \
  "${JOBGRID_BASE_URL%/}/crm/backup/import/bundle?mode=${MODE}"

printf '\nBundle %s completed.\n' "${MODE}"
