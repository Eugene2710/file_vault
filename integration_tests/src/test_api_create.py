#!/usr/bin/env python
"""Basic API tests using pytest-django for database handling"""

import os
import uuid
import pytest
import django
from pytest import MonkeyPatch
from rest_framework.test import APIRequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from src.files.serializers import FileSerializer
from src.files.views import FileViewSet  # noqa: E402
from src.files.models import File, FileStorage  # noqa: E402
from src.services.s3_file_service import S3FileService  # noqa: E402
from src.services.storage_limit_service import StorageLimitService  # noqa: E402

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.core.settings")
django.setup()


@pytest.fixture
def s3_credentials() -> dict[str, str]:
    """Get MinIO credentials from environment variables"""
    return {
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        "endpoint_url": os.getenv("AWS_ENDPOINT_URL", "http://localhost:9000"),
        "region_name": os.getenv("AWS_REGION", "us-east-1"),
    }


@pytest.fixture
def test_bucket_name() -> str:
    """Generate unique bucket name for test isolation"""
    return f"test-api-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def s3_service(s3_credentials: dict[str, str], test_bucket_name: str):
    """Create real S3FileService instance with MinIO credentials and test bucket"""
    service = S3FileService(
        bucket_name=test_bucket_name,
        aws_access_key_id=s3_credentials["aws_access_key_id"],
        aws_secret_access_key=s3_credentials["aws_secret_access_key"],
        endpoint_url=s3_credentials["endpoint_url"],
        region_name=s3_credentials["region_name"],
    )

    # Create the test bucket
    service.create_bucket()

    yield service

    # Cleanup: delete the test bucket and all its contents
    try:
        service.delete_bucket()
    except Exception as e:
        print(f"Warning: Failed to cleanup test bucket: {e}")


# No custom database fixture needed - pytest-django handles this


@pytest.mark.django_db
def test_userid_required(
    s3_credentials: dict[str, str], test_bucket_name: str, monkeypatch: MonkeyPatch
) -> None:
    """Test that UserId header is required"""
    # Set environment variables so FileViewSet creates the same S3 service
    monkeypatch.setenv("AWS_BUCKET_NAME", test_bucket_name)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3_credentials["aws_access_key_id"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3_credentials["aws_secret_access_key"])
    monkeypatch.setenv("AWS_ENDPOINT_URL", s3_credentials["endpoint_url"])
    monkeypatch.setenv("AWS_REGION", s3_credentials["region_name"])

    factory = APIRequestFactory()
    file_content = b"Test content"
    uploaded_file = SimpleUploadedFile(
        "test.txt", file_content, content_type="text/plain"
    )

    # Request without UserId header
    request = factory.post("/files/", {"file": uploaded_file})

    view = FileViewSet.as_view({"post": "create"})
    response = view(request)

    assert response.status_code == 400
    assert "UserId header is required" in response.data["error"]


@pytest.mark.django_db
def test_storage_limit(
    s3_credentials: dict[str, str], test_bucket_name: str, monkeypatch: MonkeyPatch
) -> None:
    """Test storage limit enforcement"""
    # Set environment variables so FileViewSet creates the same S3 service
    monkeypatch.setenv("AWS_BUCKET_NAME", test_bucket_name)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3_credentials["aws_access_key_id"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3_credentials["aws_secret_access_key"])
    monkeypatch.setenv("AWS_ENDPOINT_URL", s3_credentials["endpoint_url"])
    monkeypatch.setenv("AWS_REGION", s3_credentials["region_name"])

    factory = APIRequestFactory()
    # Create file larger than 10MB
    large_content = b"x" * (11 * 1024 * 1024)  # 11MB
    uploaded_file = SimpleUploadedFile(
        "large.txt", large_content, content_type="text/plain"
    )

    request = factory.post("/files/", {"file": uploaded_file})
    request.headers = {"UserId": "test_user_123"}

    view = FileViewSet.as_view({"post": "create"})
    response = view(request)

    assert response.status_code == 429
    assert "Storage Quota Exceeded" in response.data["error"]
    assert response.data["limit_bytes"] == 10 * 1024 * 1024
    assert response.data["attempted_upload_bytes"] == 11 * 1024 * 1024


@pytest.mark.django_db
def test_serializer_with_db() -> None:
    """Test the serializer with real database objects"""
    # Create real storage and file objects
    storage = FileStorage.objects.create(
        file_hash="abcd1234567890",
        s3_path="test/path.txt",
        size=1024,
        reference_count=1,
    )

    file_obj = File.objects.create(
        storage=storage,
        user_id="test_user",
        original_filename="test.txt",
        file_type="text/plain",
        is_duplicate=False,
    )

    serializer = FileSerializer(file_obj)
    data = serializer.data

    # Check required fields from API spec
    required_fields = [
        "id",
        "file",
        "original_filename",
        "file_type",
        "size",
        "user_id",
        "file_hash",
        "reference_count",
        "is_reference",
        "original_file",
    ]

    for field in required_fields:
        assert field in data, f"Missing field: {field}"

    assert data["file_hash"] == "abcd1234567890"
    assert data["user_id"] == "test_user"
    assert not data["is_reference"]
    assert data["original_file"] is None
    assert data["size"] == 1024
    assert data["reference_count"] == 1


@pytest.mark.django_db
def test_user_storage_methods() -> None:
    """Test user storage calculation methods"""
    # Create some test data
    storage1 = FileStorage.objects.create(
        file_hash="hash1", s3_path="path1.txt", size=1000, reference_count=1
    )

    storage2 = FileStorage.objects.create(
        file_hash="hash2", s3_path="path2.txt", size=2000, reference_count=1
    )

    # Create files for user1
    File.objects.create(
        storage=storage1,
        user_id="user1",
        original_filename="file1.txt",
        file_type="text/plain",
    )

    File.objects.create(
        storage=storage2,
        user_id="user1",
        original_filename="file2.txt",
        file_type="text/plain",
    )

    # Create file for user2
    File.objects.create(
        storage=storage1,
        user_id="user2",
        original_filename="file3.txt",
        file_type="text/plain",
    )
    storage_service = StorageLimitService()

    user1_usage = storage_service.get_user_storage_usage("user1")
    user2_usage = storage_service.get_user_storage_usage("user2")

    assert user1_usage == 3000  # 1000 + 2000
    assert user2_usage == 1000  # Only storage1

    # Test storage limits (user1 has used 3000 bytes, limit is 10MB = 10,485,760 bytes)
    # So user1 can upload about 10MB - 3KB more
    remaining = (10 * 1024 * 1024) - 3000  # About 10MB - 3KB
    is_allowed_1, _ = storage_service.check_storage_limit("user1", remaining - 1000)
    is_allowed_2, _ = storage_service.check_storage_limit("user1", remaining + 1000)
    assert is_allowed_1  # Should fit
    assert not is_allowed_2  # Should exceed


@pytest.mark.django_db
def test_file_hash_calculation() -> None:
    """Test file hash calculation"""
    test_content = b"This is test file content for hash calculation"

    calculated_hash = File.calculate_file_hash(test_content)

    assert isinstance(calculated_hash, str)
    assert len(calculated_hash) == 64  # SHA-256 produces 64 character hex string

    # Same content should produce same hash
    calculated_hash2 = File.calculate_file_hash(test_content)
    assert calculated_hash == calculated_hash2

    # Different content should produce different hash
    different_content = b"Different content"
    different_hash = File.calculate_file_hash(different_content)
    assert calculated_hash != different_hash


@pytest.mark.django_db
def test_find_existing_storage() -> None:
    """Test the find_existing_storage class method"""
    # Create a storage record
    test_hash = "test_hash_12345"
    storage = FileStorage.objects.create(
        file_hash=test_hash, s3_path="test/path", size=100
    )

    # Should find existing storage
    found_storage = File.find_existing_storage(test_hash)
    assert found_storage == storage

    # Should return None for non-existent hash
    not_found = File.find_existing_storage("nonexistent_hash")
    assert not_found is None