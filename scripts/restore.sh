#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${JOBGRID_COMPOSE_FILE:-docker-compose.prod.yml}"
DB_SERVICE="${JOBGRID_DB_SERVICE:-db}"
BACKEND_SERVICE="${JOBGRID_BACKEND_SERVICE:-backend}"
DB_USER="${JOBGRID_DB_USER:-postgres}"
DB_NAME="${JOBGRID_DB_NAME:-csvapp}"
HEALTH_ATTEMPTS="${JOBGRID_RESTORE_HEALTH_ATTEMPTS:-60}"
HEALTH_INTERVAL_SECONDS="${JOBGRID_RESTORE_HEALTH_INTERVAL_SECONDS:-1}"
ASSUME_YES=false
EXPECTED_SHA256="${JOBGRID_EXPECTED_BACKUP_SHA256:-}"

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        echo "ERROR: sha256sum or shasum is required to verify backup integrity." >&2
        return 1
    fi
}

usage() {
    cat <<'EOF'
Usage: scripts/restore.sh [--yes] [--expected-sha256 HEX] <backup-file.sql.gz>

Environment overrides:
  JOBGRID_COMPOSE_FILE
  JOBGRID_DB_SERVICE
  JOBGRID_BACKEND_SERVICE
  JOBGRID_DB_USER
  JOBGRID_DB_NAME
  JOBGRID_EXPECTED_BACKUP_SHA256
  JOBGRID_RESTORE_HEALTH_ATTEMPTS
  JOBGRID_RESTORE_HEALTH_INTERVAL_SECONDS
EOF
}

BACKUP_FILE=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes|-y)
            ASSUME_YES=true
            shift
            ;;
        --expected-sha256)
            if [ "$#" -lt 2 ]; then
                echo "ERROR: --expected-sha256 requires a value." >&2
                exit 2
            fi
            EXPECTED_SHA256="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        -*)
            echo "ERROR: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [ -n "$BACKUP_FILE" ]; then
                echo "ERROR: only one backup file may be supplied." >&2
                usage >&2
                exit 2
            fi
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

if [ -z "$BACKUP_FILE" ]; then
    usage
    echo ""
    echo "Available backups:"
    ls -lh "$PROJECT_ROOT"/backups/csvapp_*.sql.gz 2>/dev/null || echo "  No backups found."
    exit 1
fi

case "$BACKUP_FILE" in
    /*) ;;
    *) BACKUP_FILE="${PROJECT_ROOT}/${BACKUP_FILE}" ;;
esac

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE" >&2
    exit 1
fi

if [ ! -s "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file is empty: $BACKUP_FILE" >&2
    exit 1
fi

gzip -t "$BACKUP_FILE"

if [ -z "$EXPECTED_SHA256" ] && [ -f "${BACKUP_FILE}.sha256" ]; then
    EXPECTED_SHA256="$(awk 'NR == 1 {print $1}' "${BACKUP_FILE}.sha256")"
fi

ACTUAL_SHA256="$(sha256_file "$BACKUP_FILE")"
if [ -n "$EXPECTED_SHA256" ] && [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
    echo "ERROR: backup checksum mismatch." >&2
    echo "Expected SHA-256: $EXPECTED_SHA256" >&2
    echo "Actual SHA-256:   $ACTUAL_SHA256" >&2
    exit 1
fi

echo "=== JobGrid Database Restore ==="
echo "Backup file: $BACKUP_FILE"
echo "Backup SHA-256: $ACTUAL_SHA256"
echo "Compose file: $COMPOSE_FILE"
echo "Database service: $DB_SERVICE"
echo "Database name: $DB_NAME"
echo ""

cd "$PROJECT_ROOT"

if [ "$ASSUME_YES" != "true" ]; then
    read -r -p "This will overwrite database '$DB_NAME'. Continue? (y/N) " REPLY
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

echo "[1/4] Stopping backend..."
docker compose -f "$COMPOSE_FILE" stop "$BACKEND_SERVICE"

echo "[2/4] Restoring database..."
gunzip -c "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T "$DB_SERVICE"     psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME"
echo "      Restore complete."

echo "[3/4] Starting backend..."
docker compose -f "$COMPOSE_FILE" start "$BACKEND_SERVICE"

echo "[4/4] Waiting for backend health check..."
HEALTHY=0
for i in $(seq 1 "$HEALTH_ATTEMPTS"); do
    if docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE"         curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        HEALTHY=1
        echo "      Backend is healthy."
        break
    fi
    sleep "$HEALTH_INTERVAL_SECONDS"
done

if [ "$HEALTHY" -ne 1 ]; then
    echo "ERROR: backend did not become healthy after restore." >&2
    echo "Inspect logs: docker compose -f $COMPOSE_FILE logs $BACKEND_SERVICE" >&2
    exit 1
fi

echo "RESTORE_BACKUP_FILE=$BACKUP_FILE"
echo "RESTORE_BACKUP_SHA256=$ACTUAL_SHA256"
echo "RESTORE_DATABASE=$DB_NAME"
echo "RESTORE_HEALTH=ok"
echo "=== Restore complete ==="
