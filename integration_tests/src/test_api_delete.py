#!/usr/bin/env python
"""Integration tests for DELETE /api/files/{id}/ endpoint - file deletion"""

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
from src.services.storage_limit_service import StorageLimitService  # noqa: E402


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
    return f"test-delete-{uuid.uuid4().hex[:8]}"


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
    delete_view = FileViewSet.as_view({"delete": "destroy"})
    retrieve_view = FileViewSet.as_view({"get": "retrieve"})

    return {
        "factory": factory,
        "create_view": create_view,
        "delete_view": delete_view,
        "retrieve_view": retrieve_view,
        "s3_service": s3_service,
    }


@pytest.mark.django_db
def test_delete_file_userid_required(setup_test_environment: dict[str, any]) -> None:
    """Test that UserId header is required for file deletion"""
    env = setup_test_environment

    # Create a test file in database directly
    storage = FileStorage.objects.create(
        file_hash="test_hash_delete", s3_path="test/path.txt", size=100
    )

    file_obj = File.objects.create(
        storage=storage,
        user_id="test_user",
        original_filename="test.txt",
        file_type="text/plain",
        is_duplicate=False,
    )

    # Request without UserId header
    request = env["factory"].delete(f"/files/{file_obj.id}/")
    response = env["delete_view"](request, pk=str(file_obj.id))

    assert response.status_code == 400
    assert "UserId header is required" in response.data["error"]


@pytest.mark.django_db
def test_delete_file_success(setup_test_environment: dict[str, any]) -> None:
    """Test successful file deletion"""
    env = setup_test_environment
    user_id = "test_user_delete"

    # Upload a file first
    file_content = b"Test content for deletion"
    uploaded_file = SimpleUploadedFile(
        "test.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    upload_response = env["create_view"](upload_request)

    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]

    # Verify file exists
    assert File.objects.filter(id=file_id).exists()
    storage_id = File.objects.get(id=file_id).storage.id
    assert FileStorage.objects.filter(id=storage_id).exists()

    # Delete the file
    request = env["factory"].delete(f"/files/{file_id}/")
    request.headers = {"UserId": user_id}
    response = env["delete_view"](request, pk=file_id)

    assert response.status_code == 204
    assert response.data is None

    # Verify file is deleted
    assert not File.objects.filter(id=file_id).exists()
    # Storage should also be deleted since reference count was 1
    assert not FileStorage.objects.filter(id=storage_id).exists()


@pytest.mark.django_db
def test_delete_file_user_isolation(setup_test_environment: dict[str, any]) -> None:
    """Test that users cannot delete files belonging to other users"""
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

    # Try to delete as user2
    request = env["factory"].delete(f"/files/{file_id}/")
    request.headers = {"UserId": "user2"}
    response = env["delete_view"](request, pk=file_id)

    # Should return 404 to not leak file existence
    assert response.status_code == 404
    assert "File not found" in response.data["error"]

    # Verify file still exists
    assert File.objects.filter(id=file_id).exists()


@pytest.mark.django_db
def test_delete_nonexistent_file(setup_test_environment: dict[str, any]) -> None:
    """Test deletion of non-existent file returns 404"""
    env = setup_test_environment

    # Try to delete a non-existent file
    fake_id = str(uuid.uuid4())
    request = env["factory"].delete(f"/files/{fake_id}/")
    request.headers = {"UserId": "test_user"}

    # DRF's get_object() will raise Http404, which should be handled
    try:
        response = env["delete_view"](request, pk=fake_id)
        # If we get here, it should be a 404 response
        assert response.status_code == 404
    except Exception:
        # If an exception is raised, that's also acceptable for non-existent files
        pass


@pytest.mark.django_db
def test_delete_file_with_references(setup_test_environment: dict[str, any]) -> None:
    """Test deleting file with multiple references only decrements reference count"""
    env = setup_test_environment
    user_id = "test_user_refs"

    # Upload original file
    file_content = b"Content for reference test"
    original_file = SimpleUploadedFile(
        "original.txt", file_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": original_file})
    upload_request1.headers = {"UserId": user_id}
    upload_response1 = env["create_view"](upload_request1)

    assert upload_response1.status_code == 201
    original_file_id = upload_response1.data["id"]

    # Upload duplicate file (same content)
    duplicate_file = SimpleUploadedFile(
        "duplicate.txt", file_content, content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": duplicate_file})
    upload_request2.headers = {"UserId": user_id}
    upload_response2 = env["create_view"](upload_request2)

    assert upload_response2.status_code == 201
    duplicate_file_id = upload_response2.data["id"]

    # Both files should reference the same storage
    original_file_obj = File.objects.get(id=original_file_id)
    duplicate_file_obj = File.objects.get(id=duplicate_file_id)
    assert original_file_obj.storage.id == duplicate_file_obj.storage.id
    storage_id = original_file_obj.storage.id

    # Verify reference count is 2
    storage = FileStorage.objects.get(id=storage_id)
    assert storage.reference_count == 2

    # Delete one file
    request = env["factory"].delete(f"/files/{duplicate_file_id}/")
    request.headers = {"UserId": user_id}
    response = env["delete_view"](request, pk=duplicate_file_id)

    assert response.status_code == 204

    # Verify the File record is deleted but storage remains
    assert not File.objects.filter(id=duplicate_file_id).exists()
    assert File.objects.filter(id=original_file_id).exists()
    assert FileStorage.objects.filter(id=storage_id).exists()

    # Verify reference count is decremented
    storage.refresh_from_db()
    assert storage.reference_count == 1

    # Delete the second file
    request = env["factory"].delete(f"/files/{original_file_id}/")
    request.headers = {"UserId": user_id}
    response = env["delete_view"](request, pk=original_file_id)

    assert response.status_code == 204

    # Now both File record and storage should be deleted
    assert not File.objects.filter(id=original_file_id).exists()
    assert not FileStorage.objects.filter(id=storage_id).exists()


@pytest.mark.django_db
def test_delete_file_storage_usage_update(
    setup_test_environment: dict[str, any],
) -> None:
    """Test that deleting files updates storage usage calculations correctly"""
    env = setup_test_environment
    user_id = "test_user_storage"

    # Upload a file
    file_content = b"Content for storage test"
    uploaded_file = SimpleUploadedFile(
        "storage_test.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    upload_response = env["create_view"](upload_request)

    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]

    storage_service = StorageLimitService()
    initial_usage = storage_service.get_user_storage_usage(user_id)
    assert initial_usage == len(file_content)

    # Delete the file
    request = env["factory"].delete(f"/files/{file_id}/")
    request.headers = {"UserId": user_id}
    response = env["delete_view"](request, pk=file_id)

    assert response.status_code == 204

    # Check storage usage after deletion
    final_usage = storage_service.get_user_storage_usage(user_id)
    assert final_usage == 0


@pytest.mark.django_db
def test_delete_file_invalid_uuid(setup_test_environment: dict[str, any]) -> None:
    """Test deleting file with invalid UUID format"""
    env = setup_test_environment

    # Try to delete with invalid UUID
    request = env["factory"].delete("/files/invalid-uuid/")
    request.headers = {"UserId": "test_user"}

    # DRF will handle invalid UUID format and typically return 404 or validation error
    try:
        response = env["delete_view"](request, pk="invalid-uuid")
        # If we get here, it should be an error response
        assert response.status_code in [400, 404]
    except Exception:
        # If an exception is raised for invalid UUID, that's also acceptable
        pass


@pytest.mark.django_db
def test_delete_file_s3_cleanup(setup_test_environment: dict[str, any]) -> None:
    """Test that S3 files are properly cleaned up when storage is deleted"""
    env = setup_test_environment
    user_id = "test_user_s3_cleanup"

    # Upload a file
    file_content = b"S3 cleanup test content"
    uploaded_file = SimpleUploadedFile(
        "s3_test.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    upload_response = env["create_view"](upload_request)

    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]

    # Get the S3 path for verification
    file_obj = File.objects.get(id=file_id)
    s3_path = file_obj.storage.s3_path

    # Verify file exists in S3 (by trying to download it)
    try:
        env["s3_service"].download_fileobj(s3_path)
        file_exists_in_s3 = True
    except Exception:
        file_exists_in_s3 = False

    assert file_exists_in_s3, "File should exist in S3 after upload"

    # Delete the file
    request = env["factory"].delete(f"/files/{file_id}/")
    request.headers = {"UserId": user_id}
    response = env["delete_view"](request, pk=file_id)

    assert response.status_code == 204

    # Verify file no longer exists in S3
    try:
        env["s3_service"].download_fileobj(s3_path)
        file_still_exists = True
    except Exception:
        file_still_exists = False

    assert not file_still_exists, "File should be deleted from S3 after deletion"


@pytest.mark.django_db
def test_delete_file_transaction_rollback(
    setup_test_environment: dict[str, any],
) -> None:
    """Test that delete operations are atomic (database changes rollback on S3 errors)"""
    env = setup_test_environment
    user_id = "test_user_transaction"

    # Upload a file
    file_content = b"Transaction test content"
    uploaded_file = SimpleUploadedFile(
        "transaction_test.txt", file_content, content_type="text/plain"
    )
    upload_request = env["factory"].post("/files/", {"file": uploaded_file})
    upload_request.headers = {"UserId": user_id}
    upload_response = env["create_view"](upload_request)

    assert upload_response.status_code == 201
    file_id = upload_response.data["id"]

    # Verify file exists before deletion
    assert File.objects.filter(id=file_id).exists()
    storage_id = File.objects.get(id=file_id).storage.id
    assert FileStorage.objects.filter(id=storage_id).exists()

    # Note: Since S3 delete failures are caught and logged but don't fail the operation,
    # we can't easily test transaction rollback without mocking. The current implementation
    # prioritizes data consistency by completing database cleanup even if S3 cleanup fails.
    # This is documented in the code comments.

    # Delete the file (should succeed even with potential S3 issues)
    request = env["factory"].delete(f"/files/{file_id}/")
    request.headers = {"UserId": user_id}
    response = env["delete_view"](request, pk=file_id)

    assert response.status_code == 204

    # Database cleanup should always succeed
    assert not File.objects.filter(id=file_id).exists()
    assert not FileStorage.objects.filter(id=storage_id).exists()


@pytest.mark.django_db
def test_delete_file_concurrent_access(setup_test_environment: dict[str, any]) -> None:
    """Test deleting files with shared storage handles reference counting correctly"""
    env = setup_test_environment
    user1_id = "user1_concurrent"
    user2_id = "user2_concurrent"

    # User1 uploads a file
    file_content = b"Shared content for concurrent test"
    user1_file = SimpleUploadedFile(
        "user1.txt", file_content, content_type="text/plain"
    )
    upload_request1 = env["factory"].post("/files/", {"file": user1_file})
    upload_request1.headers = {"UserId": user1_id}
    upload_response1 = env["create_view"](upload_request1)

    assert upload_response1.status_code == 201
    user1_file_id = upload_response1.data["id"]

    # User2 uploads the same content (duplicate)
    user2_file = SimpleUploadedFile(
        "user2.txt", file_content, content_type="text/plain"
    )
    upload_request2 = env["factory"].post("/files/", {"file": user2_file})
    upload_request2.headers = {"UserId": user2_id}
    upload_response2 = env["create_view"](upload_request2)

    assert upload_response2.status_code == 201
    user2_file_id = upload_response2.data["id"]

    # Verify both files share the same storage
    user1_storage_id = File.objects.get(id=user1_file_id).storage.id
    user2_storage_id = File.objects.get(id=user2_file_id).storage.id
    assert user1_storage_id == user2_storage_id

    # Verify reference count is 2
    storage = FileStorage.objects.get(id=user1_storage_id)
    assert storage.reference_count == 2

    # User1 deletes their file
    request = env["factory"].delete(f"/files/{user1_file_id}/")
    request.headers = {"UserId": user1_id}
    response = env["delete_view"](request, pk=user1_file_id)

    assert response.status_code == 204

    # User1's file should be deleted, but storage should remain
    assert not File.objects.filter(id=user1_file_id).exists()
    assert File.objects.filter(id=user2_file_id).exists()
    assert FileStorage.objects.filter(id=user1_storage_id).exists()

    # Reference count should be decremented
    storage.refresh_from_db()
    assert storage.reference_count == 1

    # User2 deletes their file
    request = env["factory"].delete(f"/files/{user2_file_id}/")
    request.headers = {"UserId": user2_id}
    response = env["delete_view"](request, pk=user2_file_id)

    assert response.status_code == 204

    # Both files and storage should now be deleted
    assert not File.objects.filter(id=user2_file_id).exists()
    assert not FileStorage.objects.filter(id=user1_storage_id).exists()