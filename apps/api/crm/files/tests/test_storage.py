"""The storage adapters: the local directory and S3 (against the moto emulator —
not against a real provider)."""

import io
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from django.core.exceptions import ImproperlyConfigured
from moto import mock_aws
from pytest_django.fixtures import Settings

from crm.files import storage
from crm.files.storage import LocalStorage, ObjectNotFoundError, S3Storage, StorageError

KEY = "attachments/01890a5d-ac96-774b-bcce-b302099a8057"
BUCKET = "crm-test"


@pytest.fixture
def s3() -> Iterator[S3Storage]:
    with mock_aws():
        boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        ).create_bucket(Bucket=BUCKET)
        yield S3Storage(
            bucket=BUCKET,
            endpoint_url=None,
            region="us-east-1",
            access_key_id="test",
            secret_access_key="test",
        )


def roundtrip(target: LocalStorage | S3Storage) -> None:
    content = b"x" * (200 * 1024) + b"end"
    target.save(KEY, io.BytesIO(content), content_type="application/pdf")
    assert b"".join(target.open(KEY)) == content
    target.delete(KEY)
    with pytest.raises(ObjectNotFoundError):
        target.open(KEY)
    target.delete(KEY)  # removing a missing object is not an error


def test_local_roundtrip(tmp_path: Path) -> None:
    roundtrip(LocalStorage(tmp_path))


def test_s3_roundtrip(s3: S3Storage) -> None:
    roundtrip(s3)


def test_s3_object_is_private_and_typed(s3: S3Storage) -> None:
    s3.save(KEY, io.BytesIO(b"data"), content_type="application/pdf")
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    assert client.head_object(Bucket=BUCKET, Key=KEY)["ContentType"] == "application/pdf"
    grants = client.get_object_acl(Bucket=BUCKET, Key=KEY)["Grants"]
    assert all("URI" not in grant["Grantee"] for grant in grants)  # no public group


def test_s3_failure_is_reported_without_provider_detail() -> None:
    with mock_aws():
        missing_bucket = S3Storage(
            bucket="no-such-bucket",
            endpoint_url=None,
            region="us-east-1",
            access_key_id="test",
            secret_access_key="test",
        )
        with pytest.raises(StorageError) as error:
            missing_bucket.save(KEY, io.BytesIO(b"data"), content_type="application/pdf")
        assert str(error.value) == "save"


def test_local_never_overwrites(tmp_path: Path) -> None:
    target = LocalStorage(tmp_path)
    target.save(KEY, io.BytesIO(b"first"), content_type="application/pdf")
    with pytest.raises(StorageError):
        target.save(KEY, io.BytesIO(b"second"), content_type="application/pdf")
    assert b"".join(target.open(KEY)) == b"first"


@pytest.mark.parametrize(
    "key",
    ["../outside", "attachments/../../etc/passwd", "/etc/passwd", "attachments/A B", "", "plain"],
)
def test_unsafe_keys_are_refused(tmp_path: Path, key: str) -> None:
    target = LocalStorage(tmp_path)
    for operation in (
        lambda: target.save(key, io.BytesIO(b"x"), content_type="application/pdf"),
        lambda: target.open(key),
        lambda: target.delete(key),
    ):
        with pytest.raises(ValueError, match="Unsafe"):
            operation()
    assert list(tmp_path.iterdir()) == []


def test_s3_without_credentials_is_a_configuration_error(settings: Settings) -> None:
    settings.FILE_STORAGE = "s3"
    settings.FILE_STORAGE_S3_BUCKET = ""
    storage.reset_storage_cache()
    try:
        with pytest.raises(ImproperlyConfigured, match="FILE_STORAGE_S3_BUCKET"):
            storage.get_storage()
    finally:
        storage.reset_storage_cache()
