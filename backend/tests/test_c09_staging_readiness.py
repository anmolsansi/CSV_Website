import json
from pathlib import Path

from app.config import settings
from app.main import health, readiness


REPO_ROOT = Path(__file__).resolve().parents[2]


class _HealthyDb:
    def execute(self, statement):
        return 1


class _UnavailableDb:
    def execute(self, statement):
        raise RuntimeError("database unavailable")


def _response_json(response):
    return json.loads(response.body.decode("utf-8"))


def test_liveness_contract_remains_compatible():
    assert health() == {"status": "ok"}


def test_readiness_requires_database_and_private_storage(tmp_path, monkeypatch):
    storage = tmp_path / "private-documents"
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(storage))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")

    response = readiness(_HealthyDb())

    assert response == {
        "status": "ready",
        "checks": {"database": "ready", "document_storage": "ready"},
    }
    assert (storage / "staging").is_dir()
    assert (storage / "documents").is_dir()
    assert (storage / "trash").is_dir()


def test_readiness_rejects_missing_document_storage(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", "")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response = readiness(_HealthyDb())

    assert response.status_code == 503
    payload = _response_json(response)
    assert payload["status"] == "unavailable"
    assert payload["checks"]["database"] == "ready"
    assert payload["checks"]["document_storage"] == "document_storage_unavailable"
    assert "DOCUMENT_STORAGE_DIR" not in response.body.decode("utf-8")


def test_readiness_rejects_database_failure_without_leaking_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path / "private-documents"))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")

    response = readiness(_UnavailableDb())

    assert response.status_code == 503
    payload = _response_json(response)
    assert payload == {
        "status": "unavailable",
        "checks": {"database": "unavailable", "document_storage": "ready"},
    }
    assert "database unavailable" not in response.body.decode("utf-8")


def test_render_blueprint_enforces_c09_durable_storage_and_safe_workers():
    blueprint = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "plan: 0.5c-512mb" in blueprint
    assert "plan: free" not in blueprint
    assert "healthCheckPath: /ready" in blueprint
    assert "numInstances: 1" in blueprint
    assert "mountPath: /var/data" in blueprint
    assert "sizeGB: 1" in blueprint
    assert "value: /var/data/jobgrid-documents" in blueprint

    for disabled_key in (
        "TEST_AUTH",
        "RUN_MAINTENANCE_JOBS",
        "RUN_REMINDER_WORKER",
        "REMINDER_EMAIL_DELIVERY_ENABLED",
        "JOB_URL_CHECKS_ENABLED",
    ):
        marker = f"- key: {disabled_key}\n        value: \"false\""
        assert marker in blueprint

    assert "- key: AUTO_ARCHIVE_AFTER_DAYS\n        value: \"0\"" in blueprint
    assert "- key: AUTO_PURGE_AFTER_DAYS\n        value: \"0\"" in blueprint
