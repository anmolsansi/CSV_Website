import os
from datetime import datetime, timezone

import pytest

from app.services import document_storage


class _Response:
    def __init__(self, status_code=200, *, content=b"", headers=None, payload=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture()
def gateway_backend(tmp_path, monkeypatch):
    objects: dict[str, bytes] = {}
    modified = "2026-09-28T10:00:00+00:00"

    monkeypatch.setenv("DOCUMENT_STORAGE_BACKEND", "gateway")
    monkeypatch.setenv("DOCUMENT_STAGING_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv(
        "DOCUMENT_STORAGE_GATEWAY_URL",
        "https://example.supabase.co/functions/v1/jobgrid-storage",
    )
    monkeypatch.setenv("DOCUMENT_STORAGE_GATEWAY_TOKEN", "test-gateway-token")

    def request(
        method,
        *,
        action=None,
        key=None,
        prefix=None,
        limit=None,
        content=None,
        json_body=None,
    ):
        if action == "ready":
            return _Response(200, payload={"ready": True})
        if action == "list":
            normalized = f"{prefix}/" if prefix else ""
            items = [
                {
                    "key": item_key,
                    "size_bytes": len(payload),
                    "modified_at": modified,
                }
                for item_key, payload in sorted(objects.items())
                if item_key.startswith(normalized)
            ]
            return _Response(200, payload={"items": items[: (limit or 500)]})
        if action == "move" and method == "POST":
            source = json_body["source"]
            target = json_body["target"]
            if source in objects:
                objects[target] = objects.pop(source)
            return _Response(204)
        if method == "HEAD":
            if key not in objects:
                return _Response(404)
            return _Response(
                200,
                headers={
                    "x-object-size": str(len(objects[key])),
                    "last-modified": "Sun, 28 Sep 2026 10:00:00 GMT",
                },
            )
        if method == "GET":
            if key not in objects:
                return _Response(404)
            return _Response(200, content=objects[key])
        if method == "PUT":
            objects[key] = bytes(content or b"")
            return _Response(204)
        if method == "DELETE":
            objects.pop(key, None)
            return _Response(204)
        return _Response(405)

    monkeypatch.setattr(document_storage, "_gateway_request", request)
    return objects, tmp_path / "cache"


def test_gateway_preserves_legacy_remote_backend_contract(gateway_backend):
    assert document_storage.storage_backend_name() == "s3"
    assert document_storage.is_remote_storage_backend() is True
    assert document_storage.document_storage_readiness(create=True) == {
        "ready": True,
        "code": "ready",
    }


def test_gateway_publishes_and_recovers_after_ephemeral_cache_loss(gateway_backend):
    objects, cache_root = gateway_backend
    root = document_storage.storage_cache_root(create=True)
    target = document_storage.resolve_storage_key(root, "documents/1/test.bin")
    staged = cache_root / "staging" / "upload.part"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"survives-render-free-restart")

    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, target)
    with target.open("rb") as handle:
        assert handle.read() == b"survives-render-free-restart"

    assert objects["documents/1/test.bin"] == b"survives-render-free-restart"
    target.local_path.unlink()

    assert target.is_file() is True
    assert target.read_bytes() == b"survives-render-free-restart"


def test_gateway_move_delete_and_inventory_are_remote(gateway_backend):
    objects, _ = gateway_backend
    objects["documents/2/test.bin"] = b"move-me"

    document_storage.move_storage_object(
        "documents/2/test.bin",
        "trash/2/test.bin",
    )
    assert "documents/2/test.bin" not in objects
    assert objects["trash/2/test.bin"] == b"move-me"

    inventory = document_storage.list_storage_objects("trash", limit=10)
    assert [(item.key, item.size_bytes) for item in inventory] == [
        ("trash/2/test.bin", len(b"move-me"))
    ]
    assert inventory[0].modified_at == datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)

    document_storage.delete_storage_object("trash/2/test.bin")
    assert objects == {}


def test_gateway_key_escape_is_rejected(gateway_backend):
    root = document_storage.storage_cache_root(create=True)
    with pytest.raises(document_storage.DocumentStorageError):
        document_storage.resolve_storage_key(root, "../outside.bin")
