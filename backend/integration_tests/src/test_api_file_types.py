#!/usr/bin/env python
"""Integration tests for GET /api/files/file_types/ endpoint"""

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
    return f"test-file-types-{uuid.uuid4().hex[:8]}"


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
    file_types_view = FileViewSet.as_view({"get": "file_types"})

    return {
        "factory": factory,
        "create_view": create_view,
        "file_types_view": file_types_view,
        "s3_service": s3_service,
    }


@pytest.mark.django_db
def test_file_types_userid_required(setup_test_environment: dict[str, any]) -> None:
    """Test that UserId header is required for file_types endpoint"""
    env = setup_test_environment

    # Request without UserId header
    request = env["factory"].get("/files/file_types/")
    response = env["file_types_view"](request)

    assert response.status_code == 400
    assert "UserId header is required" in response.data["error"]


@pytest.mark.django_db
def test_file_types_empty_response(setup_test_environment: dict[str, any]) -> None:
    """Test file types endpoint when user has no files"""
    env = setup_test_environment

    request = env["factory"].get("/files/file_types/")
    request.headers = {"UserId": "test_user_empty"}
    response = env["file_types_view"](request)

    assert response.status_code == 200
    assert response.data == []


@pytest.mark.django_db
def test_file_types_single_type(setup_test_environment: dict[str, any]) -> None:
    """Test file types endpoint with files of single MIME type"""
    env = setup_test_environment
    user_id = "test_user_single"

    # Upload multiple files with same MIME type
    files_to_upload = [
        ("file1.txt", b"Content 1", "text/plain"),
        ("file2.txt", b"Content 2", "text/plain"),
        ("file3.txt", b"Content 3", "text/plain"),
    ]

    for filename, content, mime_type in files_to_upload:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["create_view"](upload_request)

    # Get file types
    request = env["factory"].get("/files/file_types/")
    request.headers = {"UserId": user_id}
    response = env["file_types_view"](request)

    assert response.status_code == 200
    assert response.data == ["text/plain"]


@pytest.mark.django_db
def test_file_types_multiple_types(setup_test_environment: dict[str, any]) -> None:
    """Test file types endpoint with files of multiple MIME types"""
    env = setup_test_environment
    user_id = "test_user_multiple"

    # Upload files with different MIME types
    files_to_upload = [
        ("document.txt", b"Text content", "text/plain"),
        ("report.pdf", b"PDF content", "application/pdf"),
        ("image.jpg", b"Image content", "image/jpeg"),
        ("data.json", b'{"key": "value"}', "application/json"),
        ("photo.png", b"PNG content", "image/png"),
        ("another_doc.txt", b"More text", "text/plain"),  # Duplicate MIME type
    ]

    for filename, content, mime_type in files_to_upload:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["create_view"](upload_request)

    # Get file types
    request = env["factory"].get("/files/file_types/")
    request.headers = {"UserId": user_id}
    response = env["file_types_view"](request)

    assert response.status_code == 200

    # Should return unique file types, sorted alphabetically
    expected_types = [
        "application/json",
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
    ]
    assert response.data == expected_types


@pytest.mark.django_db
def test_file_types_user_isolation(setup_test_environment: dict[str, any]) -> None:
    """Test that file types are isolated per user"""
    env = setup_test_environment

    # Upload files for user1
    files_user1 = [
        ("doc1.txt", b"User1 text", "text/plain"),
        ("pdf1.pdf", b"User1 PDF", "application/pdf"),
    ]

    for filename, content, mime_type in files_user1:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": "user1"}
        env["create_view"](upload_request)

    # Upload files for user2
    files_user2 = [
        ("image1.jpg", b"User2 image", "image/jpeg"),
        ("data1.json", b'{"user": "2"}', "application/json"),
    ]

    for filename, content, mime_type in files_user2:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": "user2"}
        env["create_view"](upload_request)

    # Get file types for user1
    request1 = env["factory"].get("/files/file_types/")
    request1.headers = {"UserId": "user1"}
    response1 = env["file_types_view"](request1)

    assert response1.status_code == 200
    assert set(response1.data) == {"application/pdf", "text/plain"}

    # Get file types for user2
    request2 = env["factory"].get("/files/file_types/")
    request2.headers = {"UserId": "user2"}
    response2 = env["file_types_view"](request2)

    assert response2.status_code == 200
    assert set(response2.data) == {"application/json", "image/jpeg"}

    # Get file types for user with no files
    request3 = env["factory"].get("/files/file_types/")
    request3.headers = {"UserId": "user3"}
    response3 = env["file_types_view"](request3)

    assert response3.status_code == 200
    assert response3.data == []


@pytest.mark.django_db
def test_file_types_with_duplicates(setup_test_environment: dict[str, any]) -> None:
    """Test file types endpoint behavior with duplicate files"""
    env = setup_test_environment
    user_id = "test_user_duplicates"

    # Upload original file
    file_content = b"Content for duplicate test"
    uploaded_file1 = SimpleUploadedFile(
        "original.txt", file_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": uploaded_file1})
    upload_request1.headers = {"UserId": user_id}
    env["create_view"](upload_request1)

    # Upload duplicate file (same content, same MIME type)
    uploaded_file2 = SimpleUploadedFile(
        "duplicate.txt", file_content, content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": uploaded_file2})
    upload_request2.headers = {"UserId": user_id}
    env["create_view"](upload_request2)

    # Upload file with different MIME type
    uploaded_file3 = SimpleUploadedFile(
        "document.pdf", b"PDF content", content_type="application/pdf"
    )
    upload_request3 = env["factory"].post("/files/", {"file": uploaded_file3})
    upload_request3.headers = {"UserId": user_id}
    env["create_view"](upload_request3)

    # Get file types
    request = env["factory"].get("/files/file_types/")
    request.headers = {"UserId": user_id}
    response = env["file_types_view"](request)

    assert response.status_code == 200

    # Should include both MIME types, even though text/plain appears in duplicates
    expected_types = ["application/pdf", "text/plain"]
    assert response.data == expected_types


@pytest.mark.django_db
def test_file_types_sorting(setup_test_environment: dict[str, any]) -> None:
    """Test that file types are sorted alphabetically"""
    env = setup_test_environment
    user_id = "test_user_sorting"

    # Upload files with MIME types in non-alphabetical order
    files_to_upload = [
        ("zebra.txt", b"Z content", "text/plain"),
        ("apple.json", b'{"a": 1}', "application/json"),
        ("banana.xml", b"<xml></xml>", "application/xml"),
        ("orange.pdf", b"PDF content", "application/pdf"),
        ("mango.csv", b"col1,col2", "text/csv"),
    ]

    for filename, content, mime_type in files_to_upload:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["create_view"](upload_request)

    # Get file types
    request = env["factory"].get("/files/file_types/")
    request.headers = {"UserId": user_id}
    response = env["file_types_view"](request)

    assert response.status_code == 200

    # Should be sorted alphabetically
    expected_types = [
        "application/json",
        "application/pdf",
        "application/xml",
        "text/csv",
        "text/plain",
    ]
    assert response.data == expected_types

    # Verify it's actually sorted
    assert response.data == sorted(response.data)


@pytest.mark.django_db
def test_file_types_api_spec_compliance(setup_test_environment: dict[str, any]) -> None:
    """Test that the response format matches API specification"""
    env = setup_test_environment
    user_id = "test_user_spec"

    # Upload sample files matching the spec example
    files_to_upload = [
        ("document.txt", b"Plain text", "text/plain"),
        ("photo.jpg", b"JPEG image", "image/jpeg"),
        ("picture.png", b"PNG image", "image/png"),
        ("report.pdf", b"PDF document", "application/pdf"),
        ("data.json", b'{"test": true}', "application/json"),
    ]

    for filename, content, mime_type in files_to_upload:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["create_view"](upload_request)

    # Get file types
    request = env["factory"].get("/files/file_types/")
    request.headers = {"UserId": user_id}
    response = env["file_types_view"](request)

    assert response.status_code == 200

    # Response should be a list of strings (MIME types)
    assert isinstance(response.data, list)

    # All items should be strings
    for file_type in response.data:
        assert isinstance(file_type, str)

    # Should match the example from the spec (sorted)
    expected_types = [
        "application/json",
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
    ]
    assert response.data == expected_types