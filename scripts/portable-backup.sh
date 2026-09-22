#!/usr/bin/env bash
set -euo pipefail

: "${JOBGRID_BASE_URL:?Set JOBGRID_BASE_URL, for example https://jobgrid.example.com}"
: "${JOBGRID_SESSION_COOKIE:?Set JOBGRID_SESSION_COOKIE to the authenticated session cookie value}"

OUTPUT="${1:-jobgrid_backup_bundle_$(date -u +%Y%m%d_%H%M%S).zip}"

curl --fail --silent --show-error \
  --cookie "session=${JOBGRID_SESSION_COOKIE}" \
  "${JOBGRID_BASE_URL%/}/crm/backup/export/bundle" \
  --output "${OUTPUT}"

sha256sum "${OUTPUT}"
printf 'Wrote recoverable JobGrid bundle: %s\n' "${OUTPUT}"
