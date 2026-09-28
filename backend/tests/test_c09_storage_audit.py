import hashlib
from types import SimpleNamespace

from app.config import settings
from scripts import c09_storage_audit


class _FakeQuery:
    def __init__(self, documents):
        self.documents = documents

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.documents


class _FakeSession:
    def __init__(self, documents):
        self.documents = documents
        self.closed = False

    def query(self, model):
        return _FakeQuery(self.documents)

    def close(self):
        self.closed = True


def _document(*, storage_key: str, payload: bytes, sha256: str | None = None):
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        state="ready",
        storage_key=storage_key,
        size_bytes=len(payload),
        sha256=sha256 or hashlib.sha256(payload).hexdigest(),
    )


def test_audit_storage_passes_for_matching_ready_document(tmp_path, monkeypatch):
    root = tmp_path / "private-documents"
    payload = b"c09 durable document\n"
    storage_key = "documents/1/sample.bin"
    target = root / storage_key
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    document = _document(storage_key=storage_key, payload=payload)
    session = _FakeSession([document])
    monkeypatch.setattr(c09_storage_audit, "SessionLocal", lambda: session)
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(root))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.delenv("DOCUMENT_STORAGE_BACKEND", raising=False)

    result = c09_storage_audit.audit_storage()

    assert result["status"] == "PASS"
    assert result["counts"] == {
        "ready_records": 1,
        "files_checked": 1,
        "missing": 0,
        "size_mismatch": 0,
        "hash_mismatch": 0,
        "invalid_storage_key": 0,
    }
    assert len(result["inventory_sha256"]) == 64
    assert result["capacity"]["backend"] == "filesystem"
    assert result["capacity"]["total_bytes"] > 0
    assert result["capacity"]["free_bytes"] >= 0
    assert session.closed is True


def test_audit_storage_fails_without_exposing_document_data(tmp_path, monkeypatch):
    root = tmp_path / "private-documents"
    root.mkdir()
    document = _document(
        storage_key="documents/7/private-name.bin",
        payload=b"expected",
    )
    session = _FakeSession([document])
    monkeypatch.setattr(c09_storage_audit, "SessionLocal", lambda: session)
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(root))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.delenv("DOCUMENT_STORAGE_BACKEND", raising=False)

    result = c09_storage_audit.audit_storage()

    assert result["status"] == "FAIL"
    assert result["counts"]["missing"] == 1
    rendered = str(result)
    assert "private-name.bin" not in rendered
    assert str(root) not in rendered


def test_s3_capacity_output_uses_free_tier_guard_without_object_names(tmp_path, monkeypatch):
    payload = b"durable"
    storage_key = "documents/9/secret.bin"
    local = tmp_path / "cached.bin"
    local.write_bytes(payload)
    document = _document(storage_key=storage_key, payload=payload)
    session = _FakeSession([document])

    class _Path:
        def is_file(self):
            return True

        def stat(self):
            return SimpleNamespace(st_size=len(payload))

        def open(self, mode):
            return local.open(mode)

    monkeypatch.setattr(c09_storage_audit, "SessionLocal", lambda: session)
    monkeypatch.setattr(c09_storage_audit, "_storage_root", lambda create=False: tmp_path)
    monkeypatch.setattr(c09_storage_audit, "_resolve_storage_key", lambda root, key: _Path())
    monkeypatch.setattr(c09_storage_audit, "storage_backend_name", lambda: "s3")
    monkeypatch.setattr(
        c09_storage_audit,
        "list_storage_objects",
        lambda: [SimpleNamespace(key=storage_key, size_bytes=len(payload))],
    )

    result = c09_storage_audit.audit_storage()

    assert result["status"] == "PASS"
    assert result["capacity"]["backend"] == "s3"
    assert result["capacity"]["free_tier_quota_bytes"] == 1_000_000_000
    assert result["capacity"]["within_zero_cost_headroom"] is True
    assert "secret.bin" not in str(result)
