#!/usr/bin/env python
"""Integration tests for GET /api/files/ endpoint with filtering and pagination"""

import os
import uuid
import pytest
import django
from datetime import timedelta
from rest_framework.test import APIRequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from pytest import MonkeyPatch

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.core.settings")
django.setup()
from src.files.views import FileViewSet  # noqa: E402
from src.files.models import File  # noqa: E402
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
    return f"test-list-{uuid.uuid4().hex[:8]}"


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
    view = FileViewSet.as_view({"get": "list", "post": "create"})

    return {"factory": factory, "view": view, "s3_service": s3_service}


@pytest.mark.django_db
def test_list_files_userid_required(setup_test_environment: dict[str, any]) -> None:
    """Test that UserId header is required for list endpoint"""
    env = setup_test_environment

    # Request without UserId header
    request = env["factory"].get("/files/")
    response = env["view"](request)

    assert response.status_code == 400
    assert "UserId header is required" in response.data["error"]


@pytest.mark.django_db
def test_list_files_empty_response(setup_test_environment: dict[str, any]) -> None:
    """Test listing files when user has no files"""
    env = setup_test_environment

    request = env["factory"].get("/files/")
    request.headers = {"UserId": "test_user_empty"}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["results"] == []
    assert response.data["next"] is None
    assert response.data["previous"] is None


@pytest.mark.django_db
def test_list_files_basic(setup_test_environment: dict[str, any]) -> None:
    """Test basic file listing functionality"""
    env = setup_test_environment

    # First, upload some test files
    user_id = "test_user_basic"

    # Upload first file
    file_content1 = b"First test file content"
    uploaded_file1 = SimpleUploadedFile(
        "first.txt", file_content1, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": uploaded_file1})
    upload_request1.headers = {"UserId": user_id}
    env["view"](upload_request1)

    # Upload second file with different content
    file_content2 = b"Second test file content"
    uploaded_file2 = SimpleUploadedFile(
        "second.pdf", file_content2, content_type="application/pdf"
    )
    upload_request2 = env["factory"].post("/files/", {"file": uploaded_file2})
    upload_request2.headers = {"UserId": user_id}
    env["view"](upload_request2)

    # Now list files
    request = env["factory"].get("/files/")
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 2
    assert len(response.data["results"]) == 2

    # Check that files are ordered by upload date (most recent first)
    files = response.data["results"]
    assert files[0]["original_filename"] == "second.pdf"
    assert files[1]["original_filename"] == "first.txt"

    # Verify response format matches API specification
    for file_data in files:
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
            assert field in file_data, f"Missing field: {field}"


@pytest.mark.django_db
def test_list_files_with_duplicates(setup_test_environment: dict[str, any]) -> None:
    """Test listing files with duplicate content"""
    env = setup_test_environment
    user_id = "test_user_duplicates"

    # Upload original file
    file_content = b"Content for deduplication test"
    uploaded_file1 = SimpleUploadedFile(
        "original.txt", file_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": uploaded_file1})
    upload_request1.headers = {"UserId": user_id}
    env["view"](upload_request1)

    # Upload duplicate file
    uploaded_file2 = SimpleUploadedFile(
        "duplicate.txt", file_content, content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": uploaded_file2})
    upload_request2.headers = {"UserId": user_id}
    env["view"](upload_request2)

    # List files
    request = env["factory"].get("/files/")
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 2

    files = response.data["results"]
    # Most recent first (duplicate.txt)
    duplicate_file = files[0]
    original_file = files[1]

    assert duplicate_file["original_filename"] == "duplicate.txt"
    assert duplicate_file["is_reference"] is True
    assert duplicate_file["original_file"] == original_file["id"]
    assert duplicate_file["reference_count"] == 2

    assert original_file["original_filename"] == "original.txt"
    assert original_file["is_reference"] is False
    assert original_file["original_file"] is None
    assert original_file["reference_count"] == 2


@pytest.mark.django_db
def test_list_files_search_filter(setup_test_environment: dict[str, any]) -> None:
    """Test search filtering by filename"""
    env = setup_test_environment
    user_id = "test_user_search"

    # Upload files with different names
    files_to_upload = [
        ("document.txt", b"Doc content"),
        ("report.pdf", b"Report content"),
        ("image.jpg", b"Image content"),
        ("my_document.txt", b"Another doc"),
    ]

    for filename, content in files_to_upload:
        uploaded_file = SimpleUploadedFile(filename, content, content_type="text/plain")
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["view"](upload_request)

    # Search for files containing "document"
    request = env["factory"].get("/files/", {"search": "document"})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 2

    filenames = [f["original_filename"] for f in response.data["results"]]
    assert "my_document.txt" in filenames
    assert "document.txt" in filenames
    assert "report.pdf" not in filenames


@pytest.mark.django_db
def test_list_files_file_type_filter(setup_test_environment: dict[str, any]) -> None:
    """Test filtering by file type (MIME type)"""
    env = setup_test_environment
    user_id = "test_user_filetype"

    # Upload files with different MIME types
    files_to_upload = [
        ("file1.txt", b"Text content", "text/plain"),
        ("file2.pdf", b"PDF content", "application/pdf"),
        ("file3.txt", b"More text", "text/plain"),
        ("file4.jpg", b"Image content", "image/jpeg"),
    ]

    for filename, content, mime_type in files_to_upload:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["view"](upload_request)

    # Filter for text/plain files
    request = env["factory"].get("/files/", {"file_type": "text/plain"})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 2

    for file_data in response.data["results"]:
        assert file_data["file_type"] == "text/plain"


@pytest.mark.django_db
def test_list_files_size_filter(setup_test_environment: dict[str, any]) -> None:
    """Test filtering by file size"""
    env = setup_test_environment
    user_id = "test_user_size"

    # Upload files with different sizes
    files_to_upload = [
        ("small.txt", b"tiny", "text/plain"),  # 4 bytes
        ("medium.txt", b"medium file content", "text/plain"),  # 19 bytes
        (
            "large.txt",
            b"this is a much larger file content for testing",
            "text/plain",
        ),  # 48 bytes
    ]

    for filename, content, mime_type in files_to_upload:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["view"](upload_request)

    # Filter for files >= 10 bytes
    request = env["factory"].get("/files/", {"min_size": "10"})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 2

    for file_data in response.data["results"]:
        assert file_data["size"] >= 10

    # Filter for files <= 20 bytes
    request = env["factory"].get("/files/", {"max_size": "20"})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 2

    for file_data in response.data["results"]:
        assert file_data["size"] <= 20

    # Filter for files between 5 and 30 bytes
    request = env["factory"].get("/files/", {"min_size": "5", "max_size": "30"})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["original_filename"] == "medium.txt"


@pytest.mark.django_db
def test_list_files_date_filter(setup_test_environment: dict[str, any]) -> None:
    """Test filtering by upload date"""
    env = setup_test_environment
    user_id = "test_user_date"

    # Upload a file
    uploaded_file = SimpleUploadedFile(
        "test.txt", b"content", content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    env["view"](upload_request)

    # Get the uploaded file to check its date
    file_obj = File.objects.filter(user_id=user_id).first()
    upload_time = file_obj.uploaded_at

    # Test start_date filter (should include the file)
    start_date = (upload_time - timedelta(hours=1)).isoformat()
    request = env["factory"].get("/files/", {"start_date": start_date})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 1

    # Test end_date filter (should include the file)
    end_date = (upload_time + timedelta(hours=1)).isoformat()
    request = env["factory"].get("/files/", {"end_date": end_date})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 1

    # Test with a past end_date (should exclude the file)
    past_end = (upload_time - timedelta(hours=1)).isoformat()
    request = env["factory"].get("/files/", {"end_date": past_end})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 0


@pytest.mark.django_db
def test_list_files_combined_filters(setup_test_environment: dict[str, any]) -> None:
    """Test combining multiple filters"""
    env = setup_test_environment
    user_id = "test_user_combined"

    # Upload various files
    files_to_upload = [
        ("document.txt", b"small text", "text/plain"),
        ("report.pdf", b"large report content for testing filters", "application/pdf"),
        ("my_document.txt", b"another document with more content", "text/plain"),
        ("image.jpg", b"img", "image/jpeg"),
    ]

    for filename, content, mime_type in files_to_upload:
        uploaded_file = SimpleUploadedFile(filename, content, content_type=mime_type)
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["view"](upload_request)

    # Combine search + file_type + size filters
    request = env["factory"].get(
        "/files/", {"search": "document", "file_type": "text/plain", "min_size": "15"}
    )
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["original_filename"] == "my_document.txt"


@pytest.mark.django_db
def test_list_files_user_isolation(setup_test_environment: dict[str, any]) -> None:
    """Test that users only see their own files"""
    env = setup_test_environment

    # Upload file for user1
    uploaded_file1 = SimpleUploadedFile(
        "user1_file.txt", b"user1 content", content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": uploaded_file1})
    upload_request1.headers = {"UserId": "user1"}
    env["view"](upload_request1)

    # Upload file for user2
    uploaded_file2 = SimpleUploadedFile(
        "user2_file.txt", b"user2 content", content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": uploaded_file2})
    upload_request2.headers = {"UserId": "user2"}
    env["view"](upload_request2)

    # List files for user1
    request = env["factory"].get("/files/")
    request.headers = {"UserId": "user1"}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["original_filename"] == "user1_file.txt"
    assert response.data["results"][0]["user_id"] == "user1"

    # List files for user2
    request = env["factory"].get("/files/")
    request.headers = {"UserId": "user2"}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["original_filename"] == "user2_file.txt"
    assert response.data["results"][0]["user_id"] == "user2"


@pytest.mark.django_db
def test_list_files_pagination(setup_test_environment: dict[str, any]) -> None:
    """Test pagination functionality"""
    env = setup_test_environment
    user_id = "test_user_pagination"

    # Upload multiple files (more than default page size)
    for i in range(25):
        content = f"File {i} content".encode()
        uploaded_file = SimpleUploadedFile(
            f"file_{i:02d}.txt", content, content_type="text/plain"
        )
        upload_request = env["factory"].post("/files/", {"file": uploaded_file})
        upload_request.headers = {"UserId": user_id}
        env["view"](upload_request)

    # Test first page
    request = env["factory"].get("/files/")
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 25
    assert len(response.data["results"]) == 20  # Default page size
    assert response.data["next"] is not None
    assert response.data["previous"] is None

    # Test second page
    request = env["factory"].get("/files/", {"page": "2"})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 25
    assert len(response.data["results"]) == 5  # Remaining files
    assert response.data["next"] is None
    assert response.data["previous"] is not None

    # Test custom page size
    request = env["factory"].get("/files/", {"page_size": "10"})
    request.headers = {"UserId": user_id}
    response = env["view"](request)

    assert response.status_code == 200
    assert response.data["count"] == 25
    assert len(response.data["results"]) == 10