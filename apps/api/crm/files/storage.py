"""Where the bytes of attachments live (D039: object storage).

The rest of the CRM sees only this interface. A key is an opaque name chosen by
the CRM — never anything a user typed — and nothing outside the API process can
read an object: there are no public URLs, every download is authorized first and
then streamed through the API.

`S3Storage` talks to any S3-compatible service. `LocalStorage` keeps files in a
directory and exists for development and tests only.
"""

import os
import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import BinaryIO, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

CHUNK = 64 * 1024
_KEY = re.compile(r"^[a-z0-9]+(/[a-z0-9-]+)+$")


class StorageError(Exception):
    """The storage could not do what was asked. Carries no provider detail."""


class ObjectNotFoundError(StorageError):
    pass


def _check_key(key: str) -> str:
    if not _KEY.fullmatch(key):
        raise ValueError("Unsafe storage key.")
    return key


class Storage(Protocol):
    name: str

    def save(self, key: str, stream: BinaryIO, *, content_type: str) -> None:
        """Store a new object. Never replaces an existing one."""

    def open(self, key: str) -> Iterator[bytes]:
        """Read an object in chunks."""

    def delete(self, key: str) -> None:
        """Remove an object. Removing a missing object is not an error."""


class LocalStorage:
    name = "local"

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / _check_key(key)).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("Unsafe storage key.")
        return path

    def save(self, key: str, stream: BinaryIO, *, content_type: str) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # "x": fail rather than overwrite.
            with path.open("xb") as target:
                while chunk := stream.read(CHUNK):
                    target.write(chunk)
        except OSError as error:
            path.unlink(missing_ok=True) if not isinstance(error, FileExistsError) else None
            raise StorageError("save") from error

    def open(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        try:
            source = path.open("rb")
        except FileNotFoundError as error:
            raise ObjectNotFoundError("open") from error
        except OSError as error:
            raise StorageError("open") from error

        def chunks() -> Iterator[bytes]:
            with source:
                while chunk := source.read(CHUNK):
                    yield chunk

        return chunks()

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as error:
            raise StorageError("delete") from error


class S3Storage:
    name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str | None,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region or None,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=60,
            ),
        )

    def save(self, key: str, stream: BinaryIO, *, content_type: str) -> None:
        _check_key(key)
        try:
            # Keys are unique UUIDs; the bucket is private (no ACL is ever set).
            self._client.upload_fileobj(
                stream, self._bucket, key, ExtraArgs={"ContentType": content_type}
            )
        except (BotoCoreError, ClientError, OSError) as error:
            raise StorageError("save") from error

    def open(self, key: str) -> Iterator[bytes]:
        _check_key(key)
        try:
            body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise ObjectNotFoundError("open") from error
            raise StorageError("open") from error
        except BotoCoreError as error:
            raise StorageError("open") from error

        def chunks() -> Iterator[bytes]:
            try:
                yield from body.iter_chunks(CHUNK)
            finally:
                body.close()

        return chunks()

    def delete(self, key: str) -> None:
        _check_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            raise StorageError("delete") from error


@cache
def _build(kind: str) -> Storage:
    if kind == "local":
        return LocalStorage(Path(settings.FILE_STORAGE_LOCAL_ROOT))
    if kind == "s3":
        missing = [
            name
            for name in (
                "FILE_STORAGE_S3_BUCKET",
                "FILE_STORAGE_S3_ACCESS_KEY_ID",
                "FILE_STORAGE_S3_SECRET_ACCESS_KEY",
            )
            if not getattr(settings, name)
        ]
        if missing:
            raise ImproperlyConfigured(f"Object storage is not configured: {', '.join(missing)}.")
        return S3Storage(
            bucket=settings.FILE_STORAGE_S3_BUCKET,
            endpoint_url=settings.FILE_STORAGE_S3_ENDPOINT_URL,
            region=settings.FILE_STORAGE_S3_REGION,
            access_key_id=settings.FILE_STORAGE_S3_ACCESS_KEY_ID,
            secret_access_key=settings.FILE_STORAGE_S3_SECRET_ACCESS_KEY,
        )
    raise ImproperlyConfigured("FILE_STORAGE must be 'local' or 's3'.")


def get_storage() -> Storage:
    return _build(settings.FILE_STORAGE)


def reset_storage_cache() -> None:
    """For tests that change the storage settings."""
    _build.cache_clear()


def file_size(stream: BinaryIO) -> int:
    position = stream.tell()
    size = stream.seek(0, os.SEEK_END)
    stream.seek(position)
    return size
