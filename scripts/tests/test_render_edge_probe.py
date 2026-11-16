"""Offline regression tests for the bounded Render edge diagnostic."""

import importlib.util
from email.message import Message
from pathlib import Path
import unittest
from urllib.error import HTTPError, URLError

MODULE_PATH = Path(__file__).resolve().parents[1] / "render_edge_probe.py"
spec = importlib.util.spec_from_file_location("render_edge_probe", MODULE_PATH)
probe_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe_module)


class FakeResponse:
    status = 200

    def __init__(self, headers=None, status=200):
        self.headers = Message()
        self.status = status
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TestEdgeProbe(unittest.TestCase):
    def test_single_anonymous_get_without_credentials(self):
        requests = []

        def fake_open(request, timeout):
            requests.append((request, timeout))
            return FakeResponse({"Content-Type": "application/json"})

        result = probe_module.probe(probe_module.VERCEL_HEALTH, opener=fake_open)
        self.assertEqual(200, result["status"])
        self.assertEqual(1, len(requests))
        request, timeout = requests[0]
        self.assertEqual("GET", request.get_method())
        self.assertEqual(8, timeout)
        self.assertIsNone(request.get_header("Cookie"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertNotIn("body", result)

    def test_render_hibernation_header_is_conclusive_for_that_response(self):
        headers = Message()
        headers["X-Render-Routing"] = "hibernate-rate-limited"
        headers["Content-Type"] = "text/plain"
        headers["Retry-After"] = "60"

        def fake_open(request, timeout):
            raise HTTPError(request.full_url, 429, "too many requests", headers, None)

        result = probe_module.probe(probe_module.DIRECT_HEALTH, opener=fake_open)
        self.assertEqual("60", result["retry_after"])
        self.assertEqual("confirmed_render_hibernation_throttle", probe_module.diagnose(result, {"status": 200}))

    def test_generic_429_does_not_claim_render_as_source(self):
        self.assertEqual("unattributed_429_review_response_headers_and_provider_logs", probe_module.diagnose({"status": 200}, {"status": 429, "x_render_routing": ""}))

    def test_success_proves_only_current_health(self):
        self.assertEqual("healthy_at_probe_time_not_a_long_term_guarantee", probe_module.diagnose({"status": 200}, {"status": 200}))

    def test_upstream_failure_is_inconclusive(self):
        self.assertEqual("inconclusive_check_deploys_readiness_and_provider_events", probe_module.diagnose({"status": 503}, {"status": 200}))

    def test_network_exception_does_not_log_url_or_secret(self):
        def fake_open(request, timeout):
            raise URLError("secret-token-should-not-be-printed")

        result = probe_module.probe(probe_module.DIRECT_HEALTH, opener=fake_open)
        self.assertEqual({"status": None, "error_type": "URLError"}, result)

    def test_truncates_untrusted_headers(self):
        result = probe_module.probe(probe_module.DIRECT_HEALTH, opener=lambda request, timeout: FakeResponse({"X-Render-Routing": "a" * 100 + "\nINJECTION"}))
        self.assertEqual(80, len(result["x_render_routing"]))
        self.assertNotIn("INJECTION", result["x_render_routing"])


if __name__ == "__main__":
    unittest.main()
