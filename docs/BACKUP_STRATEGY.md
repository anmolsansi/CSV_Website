# Backup & Recovery Strategy

## Overview

JobGrid uses PostgreSQL with automated daily backups, WAL-based point-in-time recovery, and offsite S3 storage. This document covers backup procedures, retention policies, restoration steps, and disaster recovery.

---

## 1. Daily Automated Backups

### Cron Setup

```bash
# /etc/cron.d/jobgrid-backup — runs at 02:00 UTC daily
0 2 * * * postgres /opt/jobgrid/scripts/backup.sh >> /var/log/jobgrid/backup.log 2>&1
```

### backup.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/opt/jobgrid/backups/daily"
S3_BUCKET="s3://jobgrid-backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_NAME="${POSTGRES_DB:-csvapp}"
FILENAME="${DB_NAME}_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

# Create compressed dump
pg_dump "$DB_NAME" | gzip > "${BACKUP_DIR}/${FILENAME}"

# Upload to S3
aws s3 cp "${BACKUP_DIR}/${FILENAME}" "${S3_BUCKET}/daily/${FILENAME}" \
  --storage-class STANDARD_IA \
  --sse AES256

# Prune local backups older than 3 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +3 -delete

echo "[$(date -Iseconds)] Backup completed: ${FILENAME}"
```

---

## 2. Retention Policy

| Frequency | Retention | Storage Class |
|-----------|-----------|---------------|
| Daily | 7 most recent | S3 Standard-IA |
| Weekly (Sunday) | 4 most recent | S3 Glacier Instant Retrieval |
| Monthly (1st) | 12 most recent | S3 Glacier Deep Archive |

### Pruning Script

```bash
#!/usr/bin/env bash
set -euo pipefail

S3_BUCKET="s3://jobgrid-backups/postgres"

# Daily: keep last 7
aws s3 ls "${S3_BUCKET}/daily/" | sort | head -n -7 | awk '{print $4}' | \
  xargs -I {} aws s3 rm "${S3_BUCKET}/daily/{}"

# Weekly: keep last 4
aws s3 ls "${S3_BUCKET}/weekly/" | sort | head -n -4 | awk '{print $4}' | \
  xargs -I {} aws s3 rm "${S3_BUCKET}/weekly/{}"

# Monthly: keep last 12
aws s3 ls "${S3_BUCKET}/monthly/" | sort | head -n -12 | awk '{print $4}' | \
  xargs -I {} aws s3 rm "${S3_BUCKET}/monthly/{}"
```

---

## 3. WAL Archiving (Point-in-Time Recovery)

Enable continuous WAL archiving for granular recovery.

### PostgreSQL Configuration (postgresql.conf)

```
wal_level = replica
archive_mode = on
archive_command = 'aws s3 cp %p s3://jobgrid-backups/wal/%f --sse AES256'
restore_command = 'aws s3 cp s3://jobgrid-backups/wal/%f %p'
```

### Recovery to Specific Timestamp

```bash
# 1. Stop PostgreSQL
systemctl stop postgresql

# 2. Create recovery signal
touch /var/lib/postgresql/data/recovery.signal

# 3. Set recovery target in postgresql.auto.conf
cat >> /var/lib/postgresql/data/postgresql.auto.conf << 'EOF'
restore_command = 'aws s3 cp s3://jobgrid-backups/wal/%f %p'
recovery_target_time = '2025-06-19 14:30:00 UTC'
EOF

# 4. Start PostgreSQL — it will replay WAL to the target time
systemctl start postgresql
```

---

## 4. Restoration Procedures

### Full Restore from Backup

```bash
#!/usr/bin/env bash
set -euo pipefail

TARGET_DB="${1:-csvapp}"
BACKUP_FILE="${2:-latest}"

# Download latest if "latest" specified
if [ "$BACKUP_FILE" = "latest" ]; then
  BACKUP_FILE=$(aws s3 ls s3://jobgrid-backups/daily/ | sort | tail -1 | awk '{print $4}')
  aws s3 cp "s3://jobgrid-backups/daily/${BACKUP_FILE}" "/tmp/${BACKUP_FILE}"
  BACKUP_FILE="/tmp/${BACKUP_FILE}"
fi

# Terminate active connections
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${TARGET_DB}' AND pid <> pg_backend_pid();"

# Drop and recreate database
dropdb --if-exists "$TARGET_DB"
createdb "$TARGET_DB"

# Restore
gunzip -c "$BACKUP_FILE" | psql "$TARGET_DB"

echo "Database ${TARGET_DB} restored from ${BACKUP_FILE}"
```

### Verify Restoration

```bash
# Row counts
psql -d csvapp -c "
  SELECT 'csv_rows' AS tbl, COUNT(*) FROM csv_rows
  UNION ALL SELECT 'job_tracks', COUNT(*) FROM job_tracks
  UNION ALL SELECT 'users', COUNT(*) FROM users
  UNION ALL SELECT 'audit_events', COUNT(*) FROM audit_events;
"

# Check latest record timestamps
psql -d csvapp -c "
  SELECT MAX(created_at) AS latest_csv FROM csv_rows;
  SELECT MAX(updated_at) AS latest_track FROM job_tracks;
"
```

---

## 5. Backup Integrity Testing

Run weekly to verify backups are restorable.

```bash
#!/usr/bin/env bash
set -euo pipefail

TEST_DB="csvapp_integrity_test"
LATEST=$(aws s3 ls s3://jobgrid-backups/daily/ | sort | tail -1 | awk '{print $4}')

echo "Testing backup: ${LATEST}"

aws s3 cp "s3://jobgrid-backups/daily/${LATEST}" "/tmp/${LATEST}"
createdb --if-not-exists "$TEST_DB"
gunzip -c "/tmp/${LATEST}" | psql -q "$TEST_DB"

# Verify table structure
TABLES=$(psql -t -A -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'" "$TEST_DB")
if [ "$TABLES" -lt 5 ]; then
  echo "FAIL: Expected >=5 tables, found ${TABLES}"
  exit 1
fi

# Verify non-empty critical tables
ROWS=$(psql -t -A -c "SELECT COUNT(*) FROM users" "$TEST_DB")
echo "Users table: ${ROWS} rows"

dropdb "$TEST_DB"
rm "/tmp/${LATEST}"
echo "Integrity test passed"
```

---

## 6. S3 Backup Structure

```
s3://jobgrid-backups/postgres/
├── daily/
│   ├── csvapp_20250619_020000.sql.gz
│   ├── csvapp_20250620_020000.sql.gz
│   └── ...
├── weekly/
│   ├── csvapp_20250615_020000.sql.gz
│   └── ...
├── monthly/
│   ├── csvapp_20250601_020000.sql.gz
│   └── ...
└── wal/
    ├── 000000010000000000000001
    └── ...
```

### S3 Lifecycle Configuration

```json
{
  "Rules": [
    {
      "ID": "DailyTransition",
      "Filter": { "Prefix": "daily/" },
      "Status": "Enabled",
      "Transitions": [
        { "Days": 30, "StorageClass": "GLACIER" }
      ],
      "Expiration": { "Days": 90 }
    },
    {
      "ID": "WalLifecycle",
      "Filter": { "Prefix": "wal/" },
      "Status": "Enabled",
      "Expiration": { "Days": 30 }
    }
  ]
}
```

---

## 7. Disaster Recovery Runbook

### Severity 1: Total Database Loss

1. **Assess**: Confirm database is unrecoverable (disk failure, corruption).
2. **Provision**: Create new RDS instance or EC2 PostgreSQL host.
3. **Restore**: Run full restore from latest daily backup.
4. **Apply WAL**: If WAL archiving is enabled, replay WAL logs to desired point-in-time.
5. **Update config**: Point `DATABASE_URL` to new host.
6. **Verify**: Run integrity tests, check application health.
7. **Monitor**: Watch error rates and latency for 24 hours.

### Severity 2: Data Corruption

1. **Isolate**: Stop application writes immediately.
2. **Identify**: Determine corruption extent and time range.
3. **Restore**: Spin up a temporary instance, restore from pre-corruption backup.
4. **Export**: pg_dump the clean data from the temporary instance.
5. **Import**: Import into the production database (targeted INSERT or full restore).
6. **Validate**: Compare row counts and recent records.

### Severity 3: Accidental Deletion

1. **Pause**: Put application in read-only mode if possible.
2. **Query WAL**: Use `pg_waldump` to identify the deletion timestamp.
3. **Point-in-time restore**: Restore to just before the deletion occurred.
4. **Reconcile**: Merge any data created between deletion and restoration.

### Contact & Escalation

| Role | Contact | When |
|------|---------|------|
| On-call Engineer | PagerDuty rotation | First responder |
| DBA | #dba Slack channel | Corruption or performance |
| Engineering Lead | Direct escalation | Severity 1 incidents |

---

## 8. Monitoring

- **Backup age alert**: CloudWatch alarm if latest backup is > 48 hours old.
- **WAL lag alert**: Alert if WAL archival lags > 1 hour.
- **Restore test**: Automated monthly restore to a staging environment.
- **S3 integrity**: Enable S3 object integrity checks with SHA-256.
