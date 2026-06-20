import time
from collections import deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class _MetricsStore:
    def __init__(self, maxlen: int = 10_000):
        self.entries: deque = deque(maxlen=maxlen)
        self.total_count: int = 0
        self.error_count: int = 0

    def record(self, path: str, method: str, status_code: int, duration_ms: float):
        self.entries.append({
            "path": path,
            "method": method,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
        })
        self.total_count += 1
        if status_code >= 400:
            self.error_count += 1

    def snapshot(self):
        durations = [e["duration_ms"] for e in self.entries]
        durations_sorted = sorted(durations)
        n = len(durations_sorted)
        p50 = durations_sorted[int(n * 0.5)] if n else 0
        p95 = durations_sorted[int(n * 0.95)] if n else 0
        p99 = durations_sorted[int(n * 0.99)] if n else 0
        avg = round(sum(durations) / n, 2) if n else 0

        status_counts: dict[str, int] = {}
        method_counts: dict[str, int] = {}
        path_counts: dict[str, int] = {}
        for e in self.entries:
            key = str(e["status_code"])
            status_counts[key] = status_counts.get(key, 0) + 1
            method_counts[e["method"]] = method_counts.get(e["method"], 0) + 1
            path_counts[e["path"]] = path_counts.get(e["path"], 0) + 1

        return {
            "total_requests": self.total_count,
            "total_errors": self.error_count,
            "error_rate": round(self.error_count / self.total_count * 100, 2) if self.total_count else 0,
            "latency": {
                "p50_ms": p50,
                "p95_ms": p95,
                "p99_ms": p99,
                "avg_ms": avg,
            },
            "by_status": status_counts,
            "by_method": method_counts,
            "by_path": dict(sorted(path_counts.items(), key=lambda x: x[1], reverse=True)[:50]),
            "window_entries": len(self.entries),
        }


metrics_store = _MetricsStore()


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        path = request.url.path
        if not path.startswith("/metrics"):
            metrics_store.record(path, request.method, response.status_code, duration_ms)
        return response
