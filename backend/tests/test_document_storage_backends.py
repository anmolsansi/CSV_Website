import io
import os
from datetime import datetime, timezone

import pytest

from app.services import document_storage


class _Body(io.BytesIO):
    pass


class _Missing(Exception):
    def __init__(self):
        self.response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }


class _FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def head_bucket(self, *, Bucket):
        return {}

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise _Missing()
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise _Missing()
        return {"Body": _Body(self.objects[Key])}

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        self.objects[Key] = Body.read()
        return {}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop(Key, None)
        return {}

    def copy_object(self, *, Bucket, Key, CopySource, **kwargs):
        source = CopySource["Key"]
        if source not in self.objects:
            raise _Missing()
        self.objects[Key] = self.objects[source]
        return {}

    def list_objects_v2(self, *, Bucket, Prefix, MaxKeys, ContinuationToken=None):
        rows = [
            {
                "Key": key,
                "Size": len(payload),
                "LastModified": datetime(2026, 9, 28, tzinfo=timezone.utc),
            }
            for key, payload in sorted(self.objects.items())
            if key.startswith(Prefix)
        ][:MaxKeys]
        return {"Contents": rows, "IsTruncated": False}


@pytest.fixture()
def s3_backend(tmp_path, monkeypatch):
    fake = _FakeS3()
    monkeypatch.setenv("DOCUMENT_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("DOCUMENT_STAGING_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DOCUMENT_STORAGE_S3_ENDPOINT", "https://example.storage.supabase.co/storage/v1/s3")
    monkeypatch.setenv("DOCUMENT_STORAGE_S3_REGION", "ap-southeast-1")
    monkeypatch.setenv("DOCUMENT_STORAGE_S3_BUCKET", "jobgrid-documents")
    monkeypatch.setenv("DOCUMENT_STORAGE_S3_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("DOCUMENT_STORAGE_S3_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(document_storage, "_s3_client", lambda: (fake, "jobgrid-documents"))
    return fake, tmp_path / "cache"


def test_s3_readiness_checks_bucket_without_exposing_configuration(s3_backend):
    result = document_storage.document_storage_readiness(create=True)
    assert result == {"ready": True, "code": "ready"}


def test_s3_compat_path_publishes_after_atomic_local_replace(s3_backend):
    fake, cache_root = s3_backend
    root = document_storage.storage_cache_root(create=True)
    target = document_storage.resolve_storage_key(root, "documents/1/test.bin")
    staged = cache_root / "staging" / "upload.part"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"hello-s3")

    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, target)
    with target.open("rb") as handle:
        assert handle.read() == b"hello-s3"

    assert fake.objects["documents/1/test.bin"] == b"hello-s3"


def test_s3_compat_path_redownloads_after_ephemeral_cache_loss(s3_backend):
    fake, _ = s3_backend
    fake.objects["documents/2/test.bin"] = b"survives-render-restart"
    root = document_storage.storage_cache_root(create=True)
    target = document_storage.resolve_storage_key(root, "documents/2/test.bin")

    assert target.is_file() is True
    assert target.read_bytes() == b"survives-render-restart"
    target.local_path.unlink()

    assert target.is_file() is True
    assert target.read_bytes() == b"survives-render-restart"


def test_s3_delete_and_move_are_remote_operations(s3_backend):
    fake, _ = s3_backend
    fake.objects["documents/3/test.bin"] = b"move-me"

    document_storage.move_storage_object(
        "documents/3/test.bin",
        "trash/3/test.bin",
    )
    assert "documents/3/test.bin" not in fake.objects
    assert fake.objects["trash/3/test.bin"] == b"move-me"

    document_storage.delete_storage_object("trash/3/test.bin")
    assert "trash/3/test.bin" not in fake.objects


def test_storage_key_escape_is_rejected(s3_backend):
    root = document_storage.storage_cache_root(create=True)
    with pytest.raises(document_storage.DocumentStorageError):
        document_storage.resolve_storage_key(root, "../outside.bin")
