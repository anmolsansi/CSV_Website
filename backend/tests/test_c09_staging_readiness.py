import json
from pathlib import Path

import app.main as main_module
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


def test_readiness_requires_database_and_private_storage(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "document_storage_readiness",
        lambda runtime_settings, create=False: {"ready": True, "code": "ready"},
    )

    response = readiness(_HealthyDb())

    assert response == {
        "status": "ready",
        "checks": {"database": "ready", "document_storage": "ready"},
    }


def test_readiness_rejects_unavailable_document_storage(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "document_storage_readiness",
        lambda runtime_settings, create=False: {
            "ready": False,
            "code": "document_storage_unavailable",
        },
    )

    response = readiness(_HealthyDb())

    assert response.status_code == 503
    payload = _response_json(response)
    assert payload == {
        "status": "unavailable",
        "checks": {
            "database": "ready",
            "document_storage": "document_storage_unavailable",
        },
    }
    body = response.body.decode("utf-8")
    assert "DOCUMENT_STORAGE" not in body
    assert "supabase" not in body.lower()
    assert "bucket" not in body.lower()


def test_readiness_rejects_database_failure_without_leaking_exception(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "document_storage_readiness",
        lambda runtime_settings, create=False: {"ready": True, "code": "ready"},
    )

    response = readiness(_UnavailableDb())

    assert response.status_code == 503
    payload = _response_json(response)
    assert payload == {
        "status": "unavailable",
        "checks": {"database": "unavailable", "document_storage": "ready"},
    }
    assert "database unavailable" not in response.body.decode("utf-8")


def test_render_blueprint_enforces_zero_dollar_durable_storage_and_safe_workers():
    blueprint = (REPO_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "plan: free" in blueprint
    assert "plan: 0.5c-512mb" not in blueprint
    assert "healthCheckPath: /ready" in blueprint
    assert "numInstances: 1" in blueprint
    assert "disk:" not in blueprint
    assert "mountPath:" not in blueprint
    assert "sizeGB:" not in blueprint
    assert "- key: DOCUMENT_STORAGE_BACKEND\n        value: s3" in blueprint
    assert "- key: DOCUMENT_STORAGE_S3_BUCKET\n        value: jobgrid-documents" in blueprint
    assert "- key: DOCUMENT_STAGING_DIR\n        value: /tmp/jobgrid-document-cache" in blueprint

    for secret_key in (
        "DOCUMENT_STORAGE_S3_ENDPOINT",
        "DOCUMENT_STORAGE_S3_REGION",
        "DOCUMENT_STORAGE_S3_ACCESS_KEY_ID",
        "DOCUMENT_STORAGE_S3_SECRET_ACCESS_KEY",
    ):
        marker = f"- key: {secret_key}\n        sync: false"
        assert marker in blueprint

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
