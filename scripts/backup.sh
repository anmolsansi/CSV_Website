#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${JOBGRID_COMPOSE_FILE:-docker-compose.prod.yml}"
DB_SERVICE="${JOBGRID_DB_SERVICE:-db}"
DB_USER="${JOBGRID_DB_USER:-postgres}"
DB_NAME="${JOBGRID_DB_NAME:-csvapp}"
BACKUP_DIR="${JOBGRID_BACKUP_DIR:-${PROJECT_ROOT}/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DAILY_KEEP="${JOBGRID_BACKUP_DAILY_KEEP:-7}"
WEEKLY_KEEP="${JOBGRID_BACKUP_WEEKLY_KEEP:-4}"
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
SKIP_PRUNE="${JOBGRID_BACKUP_SKIP_PRUNE:-false}"

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        echo "ERROR: sha256sum or shasum is required to record backup integrity." >&2
        return 1
    fi
}

mkdir -p "$BACKUP_DIR"

if [ -n "${JOBGRID_BACKUP_FILE:-}" ]; then
    DUMP_FILE="$JOBGRID_BACKUP_FILE"
    case "$DUMP_FILE" in
        /*) ;;
        *) DUMP_FILE="${PROJECT_ROOT}/${DUMP_FILE}" ;;
    esac
    mkdir -p "$(dirname "$DUMP_FILE")"
else
    DUMP_FILE="$BACKUP_DIR/csvapp_${TIMESTAMP}.sql.gz"
fi

echo "=== JobGrid Database Backup ==="
echo "Timestamp: $TIMESTAMP"
echo "Compose file: $COMPOSE_FILE"
echo "Database service: $DB_SERVICE"
echo "Database name: $DB_NAME"
echo "Creating backup: $DUMP_FILE"

cd "$PROJECT_ROOT"

docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE"     pg_dump -U "$DB_USER" -d "$DB_NAME" --clean --if-exists     | gzip > "$DUMP_FILE"

if [ ! -s "$DUMP_FILE" ]; then
    echo "ERROR: backup artifact is empty: $DUMP_FILE" >&2
    exit 1
fi

gzip -t "$DUMP_FILE"
BACKUP_SHA256="$(sha256_file "$DUMP_FILE")"
BACKUP_BYTES="$(wc -c < "$DUMP_FILE" | tr -d ' ')"
printf '%s  %s\n' "$BACKUP_SHA256" "$(basename "$DUMP_FILE")" > "${DUMP_FILE}.sha256"

echo "Backup bytes: $BACKUP_BYTES"
echo "Backup SHA-256: $BACKUP_SHA256"
echo "Checksum sidecar: ${DUMP_FILE}.sha256"

if [ "$SKIP_PRUNE" != "true" ]; then
    echo "Pruning daily backups (keeping configured history)..."
    ls -1t "$BACKUP_DIR"/csvapp_*.sql.gz 2>/dev/null |         tail -n +$((DAILY_KEEP * 7 + 1)) |         xargs -r rm -f

    echo "Pruning weekly backups (keeping configured history)..."
    ls -1t "$BACKUP_DIR"/csvapp_*.sql.gz 2>/dev/null |         awk 'NR % 7 == 0' |         tail -n +$((WEEKLY_KEEP + 1)) |         xargs -r rm -f
else
    echo "Backup pruning disabled for this rehearsal."
fi

if [ -n "$S3_BUCKET" ]; then
    echo "Uploading backup and checksum to S3: $S3_BUCKET"
    aws s3 cp "$DUMP_FILE" "s3://$S3_BUCKET/backups/$(basename "$DUMP_FILE")"         --storage-class STANDARD_IA
    aws s3 cp "${DUMP_FILE}.sha256" "s3://$S3_BUCKET/backups/$(basename "$DUMP_FILE").sha256"         --storage-class STANDARD_IA
    echo "S3 upload complete."
else
    echo "S3_UPLOAD: Set BACKUP_S3_BUCKET env var to enable S3 uploads."
fi

echo "BACKUP_FILE=$DUMP_FILE"
echo "BACKUP_SHA256=$BACKUP_SHA256"
echo "BACKUP_BYTES=$BACKUP_BYTES"
echo "=== Backup complete ==="
