#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DAILY_KEEP=7
WEEKLY_KEEP=4
S3_BUCKET="${BACKUP_S3_BUCKET:-}"

mkdir -p "$BACKUP_DIR"

echo "=== JobGrid Database Backup ==="
echo "Timestamp: $TIMESTAMP"

cd "$PROJECT_ROOT"

# Create backup
DUMP_FILE="$BACKUP_DIR/csvapp_${TIMESTAMP}.sql.gz"
echo "Creating backup: $DUMP_FILE"

docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U postgres -d csvapp --clean --if-exists \
    | gzip > "$DUMP_FILE"

FILESIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "Backup size: $FILESIZE"

# Prune daily backups (keep last 7)
echo "Pruning daily backups (keeping last $DAILY_KEEP)..."
ls -1t "$BACKUP_DIR"/csvapp_*.sql.gz 2>/dev/null | \
    tail -n +$((DAILY_KEEP * 7 + 1)) | \
    xargs -r rm -f

# Prune weekly backups (keep last 4, one per week)
echo "Pruning weekly backups (keeping last $WEEKLY_KEEP)..."
ls -1t "$BACKUP_DIR"/csvapp_*.sql.gz 2>/dev/null | \
    awk 'NR % 7 == 0' | \
    tail -n +$((WEEKLY_KEEP + 1)) | \
    xargs -r rm -f

# Optional S3 upload
if [ -n "$S3_BUCKET" ]; then
    echo "Uploading to S3: $S3_BUCKET"
    aws s3 cp "$DUMP_FILE" "s3://$S3_BUCKET/backups/csvapp_${TIMESTAMP}.sql.gz" \
        --storage-class STANDARD_IA
    echo "S3 upload complete."
else
    echo "S3_UPLOAD: Set BACKUP_S3_BUCKET env var to enable S3 uploads."
fi

echo "=== Backup complete ==="
ls -lh "$BACKUP_DIR"/csvapp_*.sql.gz | tail -5
