"""
Object storage for the geo layers a chat generation produced (zones, roads, territory),
with a MinIO backend and a local filesystem fallback.

Objects are addressed by key derived from the result id, so the file endpoint resolves a
link without any database lookup. Objects are never handed to the browser directly:
MinIO sits on a private network the frontend (behind the external proxy) can't reach,
so the API streams the bytes itself through `open_stream`.
"""

from __future__ import annotations

import io
import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from iduconfig import Config
from loguru import logger

from app.common.config_utils import get_optional_config

_CHUNK_SIZE = 64 * 1024
_CONTENT_TYPE = "application/geo+json"
DEFAULT_REGION = "us-east-1"
DEFAULT_LOCAL_ROOT = "runtime_data/layers"

_MINIO_KEYS = (
    "FILESERVER_ENDPOINT",
    "FILESERVER_ACCESS_KEY",
    "FILESERVER_SECRET_KEY",
    "FILESERVER_BUCKET_NAME",
)


class ObjectStorageError(RuntimeError):
    """A stored object could not be written or read."""


class ObjectStorage(ABC):
    """Backend for generated geo-layer blobs."""

    @abstractmethod
    def put_json(self, payload: dict[str, Any], object_key: str) -> None:
        """Store `payload` as UTF-8 JSON under `object_key`."""

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        """Whether the object is still present."""

    @abstractmethod
    def open_stream(self, object_key: str) -> Iterator[bytes]:
        """Yield the object's bytes in chunks, without loading it into memory."""


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class LocalStorage(ObjectStorage):
    """Filesystem-backed storage, used when MinIO is not configured (development, tests)."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    def _resolve(self, object_key: str) -> Path:
        path = (self._root / object_key).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ObjectStorageError(f"Object key resolves outside the storage root: {object_key!r}") from exc
        return path

    def put_json(self, payload: dict[str, Any], object_key: str) -> None:
        path = self._resolve(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_encode(payload))

    def exists(self, object_key: str) -> bool:
        return self._resolve(object_key).is_file()

    def open_stream(self, object_key: str) -> Iterator[bytes]:
        with self._resolve(object_key).open("rb") as handle:
            while chunk := handle.read(_CHUNK_SIZE):
                yield chunk


@contextmanager
def _translated_errors(action: str) -> Iterator[None]:
    """
    Re-raise backend failures as ObjectStorageError -- the MinIO client raises both
    S3Error and raw urllib3 connection errors, and callers shouldn't import either.
    """

    try:
        yield
    except Exception as exc:
        raise ObjectStorageError(f"Object storage failed to {action}: {exc}") from exc


class MinioStorage(ObjectStorage):
    """MinIO / S3-compatible object storage."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        region: str = DEFAULT_REGION,
    ) -> None:
        from minio import Minio  # pylint: disable=import-outside-toplevel

        self._bucket = bucket
        # `region` is passed explicitly: without it the client first resolves the bucket
        # location, which needs an s3:GetBucketLocation right scoped credentials lack.
        # The bucket is provisioned out of band, so nothing is created here.
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure, region=region)

    def put_json(self, payload: dict[str, Any], object_key: str) -> None:
        data = _encode(payload)
        with _translated_errors(f"store {object_key}"):
            self._client.put_object(self._bucket, object_key, io.BytesIO(data), len(data), content_type=_CONTENT_TYPE)

    def exists(self, object_key: str) -> bool:
        from minio.error import S3Error  # pylint: disable=import-outside-toplevel

        try:
            self._client.stat_object(self._bucket, object_key)
        except S3Error as exc:
            if exc.code in ("NoSuchKey", "NoSuchBucket"):
                return False
            raise ObjectStorageError(f"Object storage failed to stat {object_key}: {exc}") from exc
        except Exception as exc:
            raise ObjectStorageError(f"Object storage failed to stat {object_key}: {exc}") from exc
        return True

    def open_stream(self, object_key: str) -> Iterator[bytes]:
        with _translated_errors(f"read {object_key}"):
            response = self._client.get_object(self._bucket, object_key)
        try:
            yield from response.stream(_CHUNK_SIZE)
        finally:
            response.close()
            response.release_conn()


def build_object_storage(config: Config) -> ObjectStorage:
    """
    MinIO when all four FILESERVER_* keys are set, local disk when none are. A partial set
    is refused rather than silently degraded: falling back to local disk in production
    would produce history links that break at the next container restart.
    """

    present = {key: get_optional_config(config, key) for key in _MINIO_KEYS}
    set_keys = [key for key, value in present.items() if value]

    if len(set_keys) == len(_MINIO_KEYS):
        logger.info(
            f"Object storage: MinIO at {present['FILESERVER_ENDPOINT']}, bucket {present['FILESERVER_BUCKET_NAME']}"
        )
        secure = (get_optional_config(config, "FILESERVER_SECURE", "") or "").strip().lower()
        return MinioStorage(
            endpoint=present["FILESERVER_ENDPOINT"],
            access_key=present["FILESERVER_ACCESS_KEY"],
            secret_key=present["FILESERVER_SECRET_KEY"],
            bucket=present["FILESERVER_BUCKET_NAME"],
            secure=secure in ("1", "true", "yes", "on"),
            region=get_optional_config(config, "FILESERVER_REGION", DEFAULT_REGION),
        )

    if set_keys:
        missing = [key for key in _MINIO_KEYS if key not in set_keys]
        raise ObjectStorageError("Object storage is half-configured; missing: " + ", ".join(missing))

    root = get_optional_config(config, "LAYERS_STORAGE_DIR", DEFAULT_LOCAL_ROOT)
    logger.info(f"Object storage: local filesystem at {root}")
    return LocalStorage(root)
