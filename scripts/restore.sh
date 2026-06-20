#!/usr/bin/env bash
set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup-file.sql.gz>"
    echo ""
    echo "Available backups:"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    ls -lh "$PROJECT_ROOT"/backups/csvapp_*.sql.gz 2>/dev/null || echo "  No backups found."
    exit 1
fi

BACKUP_FILE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "=== JobGrid Database Restore ==="
echo "Backup file: $BACKUP_FILE"
echo ""

cd "$PROJECT_ROOT"

# Confirm
read -p "This will overwrite the current database. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo "[1/4] Stopping backend..."
docker compose -f docker-compose.prod.yml stop backend

echo "[2/4] Restoring database..."
gunzip -c "$BACKUP_FILE" | docker compose -f docker-compose.prod.yml exec -T db \
    psql -U postgres -d csvapp
echo "      Restore complete."

echo "[3/4] Starting backend..."
docker compose -f docker-compose.prod.yml start backend

echo "[4/4] Waiting for backend health check..."
for i in $(seq 1 20); do
    if docker compose -f docker-compose.prod.yml exec -T backend \
        curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "      Backend is healthy."
        break
    fi
    if [ "$i" -eq 20 ]; then
        echo "      WARNING: Backend did not become healthy in time."
        echo "      Check logs: docker compose -f docker-compose.prod.yml logs backend"
    fi
    sleep 3
done

echo ""
echo "=== Restore complete ==="
