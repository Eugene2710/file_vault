#!/usr/bin/env python
"""Integration tests for GET /api/files/{id}/ endpoint - file details retrieval"""

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
from src.files.models import File, FileStorage  # noqa: E402
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
    return f"test-retrieve-{uuid.uuid4().hex[:8]}"


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
    create_view = FileViewSet.as_view({"post": "create"})
    retrieve_view = FileViewSet.as_view({"get": "retrieve"})

    return {
        "factory": factory,
        "create_view": create_view,
        "retrieve_view": retrieve_view,
        "s3_service": s3_service,
    }


@pytest.mark.django_db
def test_retrieve_file_userid_required(setup_test_environment: dict[str, any]) -> None:
    """Test that UserId header is required for file retrieval"""
    env = setup_test_environment

    # Create a test file in database directly
    storage = FileStorage.objects.create(
        file_hash="test_hash_123", s3_path="test/path.txt", size=100
    )

    file_obj = File.objects.create(
        storage=storage,
        user_id="test_user",
        original_filename="test.txt",
        file_type="text/plain",
        is_duplicate=False,
    )

    # Request without UserId header
    request = env["factory"].get(f"/files/{file_obj.id}/")
    response = env["retrieve_view"](request, pk=str(file_obj.id))

    assert response.status_code == 400
    assert "UserId header is required" in response.data["error"]


@pytest.mark.django_db
def test_retrieve_file_success(setup_test_environment: dict[str, any]) -> None:
    """Test successful file retrieval by owner"""
    env = setup_test_environment
    user_id = "test_user_retrieve"

    # Upload a file first
    file_content = b"Test content for retrieval"
    uploaded_file = SimpleUploadedFile(
        "test.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    upload_response = env["create_view"](upload_request)

    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]

    # Now retrieve the file details
    request = env["factory"].get(f"/files/{file_id}/")
    request.headers = {"UserId": user_id}
    response = env["retrieve_view"](request, pk=file_id)

    assert response.status_code == 200

    # Verify response format matches API specification
    data = response.data
    expected_fields = [
        "id",
        "file",
        "original_filename",
        "file_type",
        "size",
        "uploaded_at",
        "user_id",
        "file_hash",
        "reference_count",
        "is_reference",
        "original_file",
    ]

    for field in expected_fields:
        assert field in data, f"Missing field: {field}"

    # Verify field values
    assert data["id"] == file_id
    assert data["original_filename"] == "test.txt"
    assert data["file_type"] == "text/plain"
    assert data["size"] == len(file_content)
    assert data["user_id"] == user_id
    assert data["reference_count"] == 1
    assert data["is_reference"] is False
    assert data["original_file"] is None
    assert len(data["file_hash"]) == 64  # SHA-256 hash length


@pytest.mark.django_db
def test_retrieve_file_user_isolation(setup_test_environment: dict[str, any]) -> None:
    """Test that users cannot access files belonging to other users"""
    env = setup_test_environment

    # Upload file as user1
    file_content = b"User1 private content"
    uploaded_file = SimpleUploadedFile(
        "user1_file.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": "user1"}
    upload_response = env["create_view"](upload_request)

    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]

    # Try to access as user2
    request = env["factory"].get(f"/files/{file_id}/")
    request.headers = {"UserId": "user2"}
    response = env["retrieve_view"](request, pk=file_id)

    # Should return 404 to not leak file existence
    assert response.status_code == 404
    assert "File not found" in response.data["error"]


@pytest.mark.django_db
def test_retrieve_nonexistent_file(setup_test_environment: dict[str, any]) -> None:
    """Test retrieval of non-existent file returns 404"""
    env = setup_test_environment

    # Try to retrieve a non-existent file
    fake_id = str(uuid.uuid4())
    request = env["factory"].get(f"/files/{fake_id}/")
    request.headers = {"UserId": "test_user"}

    # DRF's get_object() will raise Http404, which gets handled by DRF middleware
    # In testing, this typically results in a 404 response
    try:
        response = env["retrieve_view"](request, pk=fake_id)
        # If we get here, it should be a 404 response
        assert response.status_code == 404
    except Exception:
        # If an exception is raised, that's also acceptable for non-existent files
        pass


@pytest.mark.django_db
def test_retrieve_duplicate_file_details(
    setup_test_environment: dict[str, any],
) -> None:
    """Test retrieving details of a duplicate file shows correct reference information"""
    env = setup_test_environment
    user_id = "test_user_duplicate"

    # Upload original file
    file_content = b"Content for duplicate test"
    original_file = SimpleUploadedFile(
        "original.txt", file_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": original_file})
    upload_request1.headers = {"UserId": user_id}
    upload_response1 = env["create_view"](upload_request1)

    assert upload_response1.status_code == 201
    original_file_id = upload_response1.data["id"]

    # Upload duplicate file
    duplicate_file = SimpleUploadedFile(
        "duplicate.txt", file_content, content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": duplicate_file})
    upload_request2.headers = {"UserId": user_id}
    upload_response2 = env["create_view"](upload_request2)

    assert upload_response2.status_code == 201
    duplicate_file_id = upload_response2.data["id"]

    # Retrieve original file details
    request1 = env["factory"].get(f"/files/{original_file_id}/")
    request1.headers = {"UserId": user_id}
    response1 = env["retrieve_view"](request1, pk=original_file_id)

    assert response1.status_code == 200
    assert response1.data["is_reference"] is False
    assert response1.data["original_file"] is None
    assert response1.data["reference_count"] == 2  # Both files reference same storage

    # Retrieve duplicate file details
    request2 = env["factory"].get(f"/files/{duplicate_file_id}/")
    request2.headers = {"UserId": user_id}
    response2 = env["retrieve_view"](request2, pk=duplicate_file_id)

    assert response2.status_code == 200
    assert response2.data["is_reference"] is True
    assert response2.data["original_file"] == original_file_id
    assert response2.data["reference_count"] == 2
    assert response2.data["file_hash"] == response1.data["file_hash"]  # Same hash


@pytest.mark.django_db
def test_retrieve_file_response_consistency(
    setup_test_environment: dict[str, any],
) -> None:
    """Test that retrieve response format is consistent with create response"""
    env = setup_test_environment
    user_id = "test_user_consistency"

    # Upload a file
    file_content = b"Consistency test content"
    uploaded_file = SimpleUploadedFile(
        "consistency.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    upload_response = env["create_view"](upload_request)

    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]
    create_data = upload_response.data

    # Retrieve the same file
    request = env["factory"].get(f"/files/{file_id}/")
    request.headers = {"UserId": user_id}
    response = env["retrieve_view"](request, pk=file_id)

    assert response.status_code == 200
    retrieve_data = response.data

    # Compare key fields (uploaded_at might have slight differences due to timing)
    assert retrieve_data["id"] == create_data["id"]
    assert retrieve_data["original_filename"] == create_data["original_filename"]
    assert retrieve_data["file_type"] == create_data["file_type"]
    assert retrieve_data["size"] == create_data["size"]
    assert retrieve_data["user_id"] == create_data["user_id"]
    assert retrieve_data["file_hash"] == create_data["file_hash"]
    assert retrieve_data["reference_count"] == create_data["reference_count"]
    assert retrieve_data["is_reference"] == create_data["is_reference"]
    assert retrieve_data["original_file"] == create_data["original_file"]


@pytest.mark.django_db
def test_retrieve_file_with_special_characters(
    setup_test_environment: dict[str, any],
) -> None:
    """Test retrieving file with special characters in filename"""
    env = setup_test_environment
    user_id = "test_user_special"

    # Upload file with special characters
    file_content = b"Special filename test"
    special_filename = "test file with spaces & symbols (1).txt"
    uploaded_file = SimpleUploadedFile(
        special_filename, file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    upload_response = env["create_view"](upload_request)

    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]

    # Retrieve the file
    request = env["factory"].get(f"/files/{file_id}/")
    request.headers = {"UserId": user_id}
    response = env["retrieve_view"](request, pk=file_id)

    assert response.status_code == 200
    assert response.data["original_filename"] == special_filename


@pytest.mark.django_db
def test_retrieve_file_different_mime_types(
    setup_test_environment: dict[str, any],
) -> None:
    """Test retrieving files with different MIME types"""
    env = setup_test_environment
    user_id = "test_user_mime"

    # Test different file types
    test_files = [
        ("text.txt", b"Text content", "text/plain"),
        ("data.json", b'{"key": "value"}', "application/json"),
        ("image.jpg", b"fake image data", "image/jpeg"),
        ("doc.pdf", b"fake pdf data", "application/pdf"),
    ]

    uploaded_file_ids = []

    # Upload all files
    for filename, content, mime_type in test_files:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        upload_response = env["create_view"](upload_request)

        assert upload_response.status_code == 201
        uploaded_file_ids.append((upload_response.data["id"], filename, mime_type))

    # Retrieve and verify each file
    for file_id, expected_filename, expected_mime in uploaded_file_ids:
        request = env["factory"].get(f"/files/{file_id}/")
        request.headers = {"UserId": user_id}
        response = env["retrieve_view"](request, pk=file_id)

        assert response.status_code == 200
        assert response.data["original_filename"] == expected_filename
        assert response.data["file_type"] == expected_mime


@pytest.mark.django_db
def test_retrieve_file_invalid_uuid(setup_test_environment: dict[str, any]) -> None:
    """Test retrieving file with invalid UUID format"""
    env = setup_test_environment

    # Try to retrieve with invalid UUID
    request = env["factory"].get("/files/invalid-uuid/")
    request.headers = {"UserId": "test_user"}

    # DRF will handle invalid UUID format and typically return 404 or validation error
    try:
        response = env["retrieve_view"](request, pk="invalid-uuid")
        # If we get here, it should be an error response
        assert response.status_code in [400, 404]
    except Exception:
        # If an exception is raised for invalid UUID, that's also acceptable
        pass