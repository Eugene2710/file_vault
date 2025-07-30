#!/usr/bin/env python
"""Integration tests for GET /api/files/storage_stats/ endpoint"""

import os
import uuid
import pytest
import django
from rest_framework.test import APIRequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from pytest import MonkeyPatch

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.core.settings")
django.setup()
from src.files.views import FileViewSet  # noqa: E402
from src.services.s3_file_service import S3FileService  # noqa: E402


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
    return f"test-storage-stats-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def s3_service(s3_credentials: dict[str, str], test_bucket_name: str) -> S3FileService:
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


@pytest.fixture
def setup_test_environment(
    s3_service: S3FileService,
    s3_credentials: dict[str, str],
    test_bucket_name: str,
    monkeypatch: MonkeyPatch,
) -> dict[str, any]:
    """Setup environment variables for tests"""
    monkeypatch.setenv("AWS_BUCKET_NAME", test_bucket_name)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3_credentials["aws_access_key_id"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3_credentials["aws_secret_access_key"])
    monkeypatch.setenv("AWS_ENDPOINT_URL", s3_credentials["endpoint_url"])
    monkeypatch.setenv("AWS_REGION", s3_credentials["region_name"])

    factory = APIRequestFactory()
    upload_view = FileViewSet.as_view({"post": "create"})
    stats_view = FileViewSet.as_view({"get": "user_storage_stats"})

    return {
        "factory": factory,
        "upload_view": upload_view,
        "stats_view": stats_view,
        "s3_service": s3_service,
    }


@pytest.mark.django_db
def test_storage_stats_userid_required(setup_test_environment: dict[str, any]) -> None:
    """Test that UserId header is required for storage stats endpoint"""
    env = setup_test_environment

    # Request without UserId header
    request = env["factory"].get("/files/storage_stats/")
    response = env["stats_view"](request)

    assert response.status_code == 400
    assert "UserId header is required" in response.data["error"]


@pytest.mark.django_db
def test_storage_stats_empty_user(setup_test_environment: dict[str, any]) -> None:
    """Test storage stats for user with no files"""
    env = setup_test_environment

    request = env["factory"].get("/files/storage_stats/")
    request.headers = {"UserId": "empty_user"}
    response = env["stats_view"](request)

    assert response.status_code == 200
    assert response.data["user_id"] == "empty_user"
    assert response.data["total_storage_used"] == 0
    assert response.data["original_storage_used"] == 0
    assert response.data["storage_savings"] == 0
    assert response.data["savings_percentage"] == 0.0


@pytest.mark.django_db
def test_storage_stats_single_file(setup_test_environment: dict[str, any]) -> None:
    """Test storage stats for user with single file"""
    env = setup_test_environment
    user_id = "single_file_user"

    # Upload a single file
    file_content = b"Single file content for testing"
    uploaded_file = SimpleUploadedFile(
        "single.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    env["upload_view"](upload_request)

    # Get storage stats
    request = env["factory"].get("/files/storage_stats/")
    request.headers = {"UserId": user_id}
    response = env["stats_view"](request)

    assert response.status_code == 200
    assert response.data["user_id"] == user_id

    expected_size = len(file_content)
    assert response.data["total_storage_used"] == expected_size
    assert response.data["original_storage_used"] == expected_size
    assert response.data["storage_savings"] == 0
    assert response.data["savings_percentage"] == 0.0


@pytest.mark.django_db
def test_storage_stats_with_duplicates(setup_test_environment: dict[str, any]) -> None:
    """Test storage stats with duplicate files showing savings"""
    env = setup_test_environment
    user_id = "duplicate_user"

    # Upload original file
    file_content = b"Content for deduplication testing in storage stats"
    uploaded_file1 = SimpleUploadedFile(
        "original.txt", file_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": uploaded_file1})
    upload_request1.headers = {"UserId": user_id}
    env["upload_view"](upload_request1)

    # Upload duplicate file (same content, different name)
    uploaded_file2 = SimpleUploadedFile(
        "duplicate.txt", file_content, content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": uploaded_file2})
    upload_request2.headers = {"UserId": user_id}
    env["upload_view"](upload_request2)

    # Upload another duplicate
    uploaded_file3 = SimpleUploadedFile(
        "another_duplicate.txt", file_content, content_type="text/plain"
    )
    upload_request3 = env["factory"].post("/files/", {"file": uploaded_file3})
    upload_request3.headers = {"UserId": user_id}
    env["upload_view"](upload_request3)

    # Get storage stats
    request = env["factory"].get("/files/storage_stats/")
    request.headers = {"UserId": user_id}
    response = env["stats_view"](request)

    assert response.status_code == 200
    assert response.data["user_id"] == user_id

    file_size = len(file_content)
    # Total storage used should be only one copy (deduplicated)
    assert response.data["total_storage_used"] == file_size
    # Original storage would be 3 copies
    assert response.data["original_storage_used"] == file_size * 3
    # Savings should be 2 copies worth
    assert response.data["storage_savings"] == file_size * 2
    # Savings percentage should be 66.7% (2/3)
    assert abs(response.data["savings_percentage"] - 66.7) < 0.1


@pytest.mark.django_db
def test_storage_stats_multiple_unique_files(
    setup_test_environment: dict[str, any],
) -> None:
    """Test storage stats with multiple unique files (no deduplication)"""
    env = setup_test_environment
    user_id = "multiple_unique_user"

    # Upload multiple unique files
    files_to_upload = [
        ("file1.txt", b"First unique file content"),
        ("file2.txt", b"Second unique file content"),
        ("file3.txt", b"Third unique file content"),
    ]

    total_size = 0
    for filename, content in files_to_upload:
        total_size += len(content)
        uploaded_file = SimpleUploadedFile(filename, content, content_type="text/plain")
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["upload_view"](upload_request)

    # Get storage stats
    request = env["factory"].get("/files/storage_stats/")
    request.headers = {"UserId": user_id}
    response = env["stats_view"](request)

    assert response.status_code == 200
    assert response.data["user_id"] == user_id
    assert response.data["total_storage_used"] == total_size
    assert response.data["original_storage_used"] == total_size
    assert response.data["storage_savings"] == 0
    assert response.data["savings_percentage"] == 0.0


@pytest.mark.django_db
def test_storage_stats_mixed_files(setup_test_environment: dict[str, any]) -> None:
    """Test storage stats with mix of unique and duplicate files"""
    env = setup_test_environment
    user_id = "mixed_files_user"

    # Upload unique file
    unique_content = b"Unique file content"
    uploaded_file1 = SimpleUploadedFile(
        "unique.txt", unique_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": uploaded_file1})
    upload_request1.headers = {"UserId": user_id}
    env["upload_view"](upload_request1)

    # Upload duplicate content twice
    duplicate_content = b"Duplicate file content for testing"
    uploaded_file2 = SimpleUploadedFile(
        "dup1.txt", duplicate_content, content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": uploaded_file2})
    upload_request2.headers = {"UserId": user_id}
    env["upload_view"](upload_request2)

    uploaded_file3 = SimpleUploadedFile(
        "dup2.txt", duplicate_content, content_type="text/plain"
    )
    upload_request3 = env["factory"].post("/files/", {"file": uploaded_file3})
    upload_request3.headers = {"UserId": user_id}
    env["upload_view"](upload_request3)

    # Get storage stats
    request = env["factory"].get("/files/storage_stats/")
    request.headers = {"UserId": user_id}
    response = env["stats_view"](request)

    assert response.status_code == 200
    assert response.data["user_id"] == user_id

    unique_size = len(unique_content)
    duplicate_size = len(duplicate_content)

    # Total storage: unique file + one copy of duplicate
    expected_total = unique_size + duplicate_size
    assert response.data["total_storage_used"] == expected_total

    # Original storage: unique file + two copies of duplicate
    expected_original = unique_size + (duplicate_size * 2)
    assert response.data["original_storage_used"] == expected_original

    # Savings: one copy of duplicate content
    expected_savings = duplicate_size
    assert response.data["storage_savings"] == expected_savings

    # Savings percentage
    expected_percentage = (expected_savings / expected_original) * 100
    assert abs(response.data["savings_percentage"] - expected_percentage) < 0.1


@pytest.mark.django_db
def test_storage_stats_user_isolation(setup_test_environment: dict[str, any]) -> None:
    """Test that storage stats only include files for the requesting user"""
    env = setup_test_environment

    # Upload files for different users with same content
    shared_content = b"Shared content between users"

    # User 1 uploads the file
    uploaded_file1 = SimpleUploadedFile(
        "user1_file.txt", shared_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": uploaded_file1})
    upload_request1.headers = {"UserId": "user1"}
    env["upload_view"](upload_request1)

    # User 2 uploads the same content (will be deduplicated)
    uploaded_file2 = SimpleUploadedFile(
        "user2_file.txt", shared_content, content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": uploaded_file2})
    upload_request2.headers = {"UserId": "user2"}
    env["upload_view"](upload_request2)

    # Get storage stats for user1
    request1 = env["factory"].get("/files/storage_stats/")
    request1.headers = {"UserId": "user1"}
    response1 = env["stats_view"](request1)

    assert response1.status_code == 200
    assert response1.data["user_id"] == "user1"

    file_size = len(shared_content)
    assert response1.data["total_storage_used"] == file_size
    assert response1.data["original_storage_used"] == file_size
    assert response1.data["storage_savings"] == 0
    assert response1.data["savings_percentage"] == 0.0

    # Get storage stats for user2
    request2 = env["factory"].get("/files/storage_stats/")
    request2.headers = {"UserId": "user2"}
    response2 = env["stats_view"](request2)

    assert response2.status_code == 200
    assert response2.data["user_id"] == "user2"

    # User2 also shows the same since each user's stats are calculated independently
    # but they reference the same storage record
    assert response2.data["total_storage_used"] == file_size
    assert response2.data["original_storage_used"] == file_size
    assert response2.data["storage_savings"] == 0
    assert response2.data["savings_percentage"] == 0.0


@pytest.mark.django_db
def test_storage_stats_response_format(setup_test_environment: dict[str, any]) -> None:
    """Test that response format matches API specification"""
    env = setup_test_environment
    user_id = "format_test_user"

    # Upload a file to ensure non-zero stats
    file_content = b"Content for format testing"
    uploaded_file = SimpleUploadedFile(
        "format_test.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    env["upload_view"](upload_request)

    # Get storage stats
    request = env["factory"].get("/files/storage_stats/")
    request.headers = {"UserId": user_id}
    response = env["stats_view"](request)

    assert response.status_code == 200

    # Verify response contains all required fields
    required_fields = [
        "user_id",
        "total_storage_used",
        "original_storage_used",
        "storage_savings",
        "savings_percentage",
    ]

    for field in required_fields:
        assert field in response.data, f"Missing required field: {field}"

    # Verify field types
    assert isinstance(response.data["user_id"], str)
    assert isinstance(response.data["total_storage_used"], int)
    assert isinstance(response.data["original_storage_used"], int)
    assert isinstance(response.data["storage_savings"], int)
    assert isinstance(response.data["savings_percentage"], (int, float))

    # Verify that user_id matches the requesting user
    assert response.data["user_id"] == user_id


@pytest.mark.django_db
def test_storage_stats_calculations_accuracy(
    setup_test_environment: dict[str, any],
) -> None:
    """Test the accuracy of storage calculations with complex scenario"""
    env = setup_test_environment
    user_id = "calculation_test_user"

    # Create a complex scenario:
    # - 1 unique file (100 bytes)
    # - 3 copies of duplicate content (200 bytes each)
    # - 2 copies of another duplicate content (50 bytes each)

    # Unique file
    unique_content = b"x" * 100  # 100 bytes
    uploaded_file1 = SimpleUploadedFile(
        "unique.txt", unique_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": uploaded_file1})
    upload_request1.headers = {"UserId": user_id}
    env["upload_view"](upload_request1)

    # First duplicate set (200 bytes each, 3 copies)
    duplicate1_content = b"y" * 200  # 200 bytes
    for i in range(3):
        uploaded_file = SimpleUploadedFile(
            f"dup1_{i}.txt", duplicate1_content, content_type="text/plain"
        )
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["upload_view"](upload_request)

    # Second duplicate set (50 bytes each, 2 copies)
    duplicate2_content = b"z" * 50  # 50 bytes
    for i in range(2):
        uploaded_file = SimpleUploadedFile(
            f"dup2_{i}.txt", duplicate2_content, content_type="text/plain"
        )
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["upload_view"](upload_request)

    # Get storage stats
    request = env["factory"].get("/files/storage_stats/")
    request.headers = {"UserId": user_id}
    response = env["stats_view"](request)

    assert response.status_code == 200

    # Expected calculations:
    # Total storage used (deduplicated): 100 + 200 + 50 = 350 bytes
    # Original storage used (without dedup): 100 + (200*3) + (50*2) = 100 + 600 + 100 = 800 bytes
    # Storage savings: 800 - 350 = 450 bytes
    # Savings percentage: (450/800) * 100 = 56.25%

    assert response.data["total_storage_used"] == 350
    assert response.data["original_storage_used"] == 800
    assert response.data["storage_savings"] == 450
    assert (
        abs(response.data["savings_percentage"] - 56.2) < 0.1
    )  # Allow small rounding difference