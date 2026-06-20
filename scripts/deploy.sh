#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== JobGrid Production Deployment ==="
echo ""

# Check for .env.prod
if [ ! -f "$PROJECT_ROOT/backend/.env.prod" ]; then
    echo "ERROR: backend/.env.prod not found."
    echo "Copy backend/.env.prod.example to backend/.env.prod and fill in values."
    exit 1
fi

cd "$PROJECT_ROOT"

echo "[1/5] Building frontend..."
docker compose -f docker-compose.prod.yml run --rm frontend npm run build
echo "      Frontend build complete."
echo ""

echo "[2/5] Starting services..."
docker compose -f docker-compose.prod.yml up -d --build
echo ""

echo "[3/5] Waiting for database to be ready..."
for i in $(seq 1 30); do
    if docker compose -f docker-compose.prod.yml exec -T db pg_isready -U postgres -d csvapp >/dev/null 2>&1; then
        echo "      Database is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Database did not become ready in time."
        docker compose -f docker-compose.prod.yml logs db
        exit 1
    fi
    sleep 2
done
echo ""

echo "[4/5] Running alembic migrations..."
docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head
echo "      Migrations complete."
echo ""

echo "[5/5] Running health checks..."
MAX_RETRIES=10
RETRY_INTERVAL=5
for i in $(seq 1 $MAX_RETRIES); do
    if docker compose -f docker-compose.prod.yml exec -T nginx curl -sf http://localhost:80/ >/dev/null 2>&1; then
        echo "      Frontend: OK"
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "      WARNING: Frontend health check failed after $MAX_RETRIES attempts."
    fi
    sleep "$RETRY_INTERVAL"
done

for i in $(seq 1 $MAX_RETRIES); do
    if docker compose -f docker-compose.prod.yml exec -T nginx curl -sf http://localhost:80/health >/dev/null 2>&1; then
        echo "      Backend:   OK"
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "      WARNING: Backend health check failed after $MAX_RETRIES attempts."
    fi
    sleep "$RETRY_INTERVAL"
done
echo ""

echo "=== Deployment complete ==="
echo "Services:"
docker compose -f docker-compose.prod.yml ps
