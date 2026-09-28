from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
from urllib.parse import urlsplit

from ..config import (
    DocumentStorageConfigurationError,
    settings,
    validate_document_storage_path,
)


class DocumentStorageError(OSError):
    """Safe storage error. Never include credentials or private object names."""


@dataclass(frozen=True)
class StorageObjectInfo:
    key: str
    size_bytes: int
    modified_at: datetime | None


def storage_backend_name() -> str:
    value = str(os.getenv("DOCUMENT_STORAGE_BACKEND", "filesystem") or "filesystem")
    value = value.strip().lower()
    if value not in {"filesystem", "s3"}:
        raise DocumentStorageError("unsupported document storage backend")
    return value


def _safe_storage_key(storage_key: str) -> str:
    raw = str(storage_key or "").strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or any(part in {"", "."} for part in path.parts)
        or "\x00" in raw
    ):
        raise DocumentStorageError("invalid storage key")
    return path.as_posix()


def storage_cache_root(*, create: bool = False) -> Path:
    configured = str(os.getenv("DOCUMENT_STAGING_DIR", "") or "").strip()
    root = (
        Path(configured).expanduser()
        if configured
        else Path(tempfile.gettempdir()) / "jobgrid-document-cache"
    ).resolve(strict=False)
    if create:
        try:
            root.mkdir(parents=True, exist_ok=True)
            for child in ("staging", "documents", "trash"):
                (root / child).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DocumentStorageError("document staging storage is unavailable") from exc
    return root


def _s3_config() -> dict[str, str]:
    values = {
        "endpoint": str(os.getenv("DOCUMENT_STORAGE_S3_ENDPOINT", "") or "").strip().rstrip("/"),
        "region": str(os.getenv("DOCUMENT_STORAGE_S3_REGION", "") or "").strip(),
        "bucket": str(os.getenv("DOCUMENT_STORAGE_S3_BUCKET", "") or "").strip(),
        "access_key": str(os.getenv("DOCUMENT_STORAGE_S3_ACCESS_KEY_ID", "") or "").strip(),
        "secret_key": str(os.getenv("DOCUMENT_STORAGE_S3_SECRET_ACCESS_KEY", "") or "").strip(),
    }
    if not all(values.values()):
        raise DocumentStorageError("S3 document storage is not fully configured")
    parsed = urlsplit(values["endpoint"])
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise DocumentStorageError("S3 document storage endpoint is invalid")
    if str(getattr(settings, "ENVIRONMENT", "")).lower() == "production" and parsed.scheme != "https":
        raise DocumentStorageError("S3 document storage endpoint must use HTTPS in production")
    return values


def _s3_client():
    config = _s3_config()
    try:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            endpoint_url=config["endpoint"],
            region_name=config["region"],
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
            ),
        )
        return client, config["bucket"]
    except DocumentStorageError:
        raise
    except Exception as exc:
        raise DocumentStorageError("S3 document storage client could not be initialized") from exc


def _is_missing_s3_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error") or {}
    code = str(error.get("Code", ""))
    status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
    return code in {"404", "NoSuchKey", "NotFound"} or status == 404


def _head_s3_object(storage_key: str) -> dict[str, Any] | None:
    key = _safe_storage_key(storage_key)
    client, bucket = _s3_client()
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if _is_missing_s3_error(exc):
            return None
        raise DocumentStorageError("private object storage is unavailable") from exc


def storage_object_exists(storage_key: str) -> bool:
    if storage_backend_name() == "filesystem":
        root = validate_document_storage_path(
            getattr(settings, "DOCUMENT_STORAGE_DIR", ""),
            environment=getattr(settings, "ENVIRONMENT", ""),
        )
        key = _safe_storage_key(storage_key)
        candidate = (root / key).resolve(strict=False)
        if root != candidate and root not in candidate.parents:
            raise DocumentStorageError("invalid storage key")
        return candidate.is_file()
    return _head_s3_object(storage_key) is not None


def _download_s3_object(storage_key: str, local_path: Path) -> None:
    key = _safe_storage_key(storage_key)
    client, bucket = _s3_client()
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        local_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = local_path.with_name(f".{local_path.name}.download")
        try:
            with temporary.open("wb") as output:
                while True:
                    chunk = body.read(64 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, local_path)
        finally:
            temporary.unlink(missing_ok=True)
            close = getattr(body, "close", None)
            if close is not None:
                close()
    except DocumentStorageError:
        raise
    except Exception as exc:
        if _is_missing_s3_error(exc):
            raise FileNotFoundError("private object is missing") from exc
        raise DocumentStorageError("private object could not be downloaded") from exc


def _upload_s3_file(storage_key: str, local_path: Path) -> None:
    key = _safe_storage_key(storage_key)
    client, bucket = _s3_client()
    try:
        with local_path.open("rb") as source:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=source,
                ContentType="application/octet-stream",
                CacheControl="private, no-store",
            )
    except Exception as exc:
        raise DocumentStorageError("private object could not be published") from exc


def delete_storage_object(storage_key: str) -> None:
    key = _safe_storage_key(storage_key)
    if storage_backend_name() == "filesystem":
        root = validate_document_storage_path(
            getattr(settings, "DOCUMENT_STORAGE_DIR", ""),
            environment=getattr(settings, "ENVIRONMENT", ""),
        )
        candidate = (root / key).resolve(strict=False)
        if root != candidate and root not in candidate.parents:
            raise DocumentStorageError("invalid storage key")
        candidate.unlink(missing_ok=True)
        return

    client, bucket = _s3_client()
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except Exception as exc:
        raise DocumentStorageError("private object could not be deleted") from exc
    cache = storage_cache_root(create=True) / key
    cache.unlink(missing_ok=True)


def move_storage_object(source_key: str, target_key: str) -> None:
    source = _safe_storage_key(source_key)
    target = _safe_storage_key(target_key)
    if storage_backend_name() == "filesystem":
        root = validate_document_storage_path(
            getattr(settings, "DOCUMENT_STORAGE_DIR", ""),
            environment=getattr(settings, "ENVIRONMENT", ""),
        )
        source_path = (root / source).resolve(strict=False)
        target_path = (root / target).resolve(strict=False)
        if root not in source_path.parents or root not in target_path.parents:
            raise DocumentStorageError("invalid storage key")
        if not source_path.exists():
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source_path, target_path)
        return

    client, bucket = _s3_client()
    try:
        client.copy_object(
            Bucket=bucket,
            Key=target,
            CopySource={"Bucket": bucket, "Key": source},
            MetadataDirective="COPY",
        )
        client.delete_object(Bucket=bucket, Key=source)
    except Exception as exc:
        if _is_missing_s3_error(exc):
            return
        raise DocumentStorageError("private object could not be moved") from exc
    root = storage_cache_root(create=True)
    source_local = root / source
    target_local = root / target
    if source_local.exists():
        target_local.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source_local, target_local)


def list_storage_objects(prefix: str = "", *, limit: int | None = None) -> list[StorageObjectInfo]:
    normalized_prefix = "" if not prefix else _safe_storage_key(prefix.rstrip("/")) + "/"
    if storage_backend_name() == "filesystem":
        root = validate_document_storage_path(
            getattr(settings, "DOCUMENT_STORAGE_DIR", ""),
            environment=getattr(settings, "ENVIRONMENT", ""),
        )
        start = (root / normalized_prefix).resolve(strict=False)
        if root != start and root not in start.parents:
            raise DocumentStorageError("invalid storage prefix")
        rows: list[StorageObjectInfo] = []
        if start.exists():
            for path in start.rglob("*"):
                if not path.is_file():
                    continue
                stat = path.stat()
                rows.append(
                    StorageObjectInfo(
                        key=path.resolve().relative_to(root).as_posix(),
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    )
                )
                if limit is not None and len(rows) >= limit:
                    break
        return rows

    client, bucket = _s3_client()
    rows: list[StorageObjectInfo] = []
    continuation: str | None = None
    try:
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": bucket,
                "Prefix": normalized_prefix,
                "MaxKeys": min(1000, max(1, (limit - len(rows)) if limit else 1000)),
            }
            if continuation:
                kwargs["ContinuationToken"] = continuation
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                modified = item.get("LastModified")
                if isinstance(modified, datetime) and modified.tzinfo is None:
                    modified = modified.replace(tzinfo=timezone.utc)
                rows.append(
                    StorageObjectInfo(
                        key=str(item.get("Key", "")),
                        size_bytes=int(item.get("Size", 0) or 0),
                        modified_at=modified if isinstance(modified, datetime) else None,
                    )
                )
                if limit is not None and len(rows) >= limit:
                    return rows
            if not response.get("IsTruncated"):
                break
            continuation = response.get("NextContinuationToken")
            if not continuation:
                break
    except Exception as exc:
        raise DocumentStorageError("private object inventory is unavailable") from exc
    return rows


class S3CompatPath(os.PathLike[str]):
    """Path-like cache façade that keeps existing filesystem call sites compatible.

    Durable bytes live in S3. The local path is only a transient Render cache.
    A read materializes the object locally. When an existing call site atomically
    replaces the local cache path and then opens it for fsync, the first read-open
    publishes the new object before returning the local file handle.
    """

    def __init__(self, root: Path, storage_key: str):
        self.root = root.resolve(strict=False)
        self.key = _safe_storage_key(storage_key)
        self.local_path = (self.root / self.key).resolve(strict=False)
        if self.root not in self.local_path.parents:
            raise DocumentStorageError("invalid storage key")

    def __fspath__(self) -> str:
        return str(self.local_path)

    def __str__(self) -> str:
        return str(self.local_path)

    @property
    def parent(self) -> Path:
        return self.local_path.parent

    @property
    def name(self) -> str:
        return self.local_path.name

    def _materialize(self) -> bool:
        head = _head_s3_object(self.key)
        if head is None:
            self.local_path.unlink(missing_ok=True)
            return False
        if not self.local_path.is_file() or self.local_path.stat().st_size != int(head.get("ContentLength", -1)):
            _download_s3_object(self.key, self.local_path)
        return True

    def exists(self) -> bool:
        return self._materialize()

    def is_file(self) -> bool:
        return self._materialize()

    def stat(self):
        if not self._materialize():
            raise FileNotFoundError("private object is missing")
        return self.local_path.stat()

    def read_bytes(self) -> bytes:
        if not self._materialize():
            raise FileNotFoundError("private object is missing")
        return self.local_path.read_bytes()

    def open(self, mode: str = "r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "+", "x")):
            raise DocumentStorageError("direct writes through cached object paths are unsupported")
        remote_exists = _head_s3_object(self.key) is not None
        if not remote_exists:
            if not self.local_path.is_file():
                raise FileNotFoundError("private object is missing")
            _upload_s3_file(self.key, self.local_path)
        elif not self.local_path.is_file():
            _download_s3_object(self.key, self.local_path)
        return self.local_path.open(mode, *args, **kwargs)

    def unlink(self, missing_ok: bool = False) -> None:
        try:
            delete_storage_object(self.key)
        except DocumentStorageError:
            if not missing_ok:
                raise
        self.local_path.unlink(missing_ok=True)


def resolve_storage_key(root: Path, storage_key: str):
    key = _safe_storage_key(storage_key)
    if storage_backend_name() == "s3":
        return S3CompatPath(root, key)
    candidate = (root / key).resolve(strict=False)
    if root != candidate and root not in candidate.parents:
        raise DocumentStorageError("invalid storage key")
    return candidate


def document_storage_readiness(runtime_settings=None, *, create: bool = False) -> dict[str, object]:
    try:
        if storage_backend_name() == "filesystem":
            runtime = runtime_settings or settings
            root = validate_document_storage_path(
                getattr(runtime, "DOCUMENT_STORAGE_DIR", ""),
                environment=getattr(runtime, "ENVIRONMENT", ""),
            )
            if create:
                root.mkdir(parents=True, exist_ok=True)
                for child in ("staging", "documents", "trash"):
                    (root / child).mkdir(parents=True, exist_ok=True)
            if not root.exists() or not root.is_dir():
                return {"ready": False, "code": "document_storage_missing"}
            if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
                return {"ready": False, "code": "document_storage_not_writable"}
            return {"ready": True, "code": "ready"}

        storage_cache_root(create=True)
        client, bucket = _s3_client()
        client.head_bucket(Bucket=bucket)
        return {"ready": True, "code": "ready"}
    except (DocumentStorageConfigurationError, DocumentStorageError, OSError, Exception):
        # The route must not reveal endpoints, bucket names, keys, or provider errors.
        return {"ready": False, "code": "document_storage_unavailable"}
