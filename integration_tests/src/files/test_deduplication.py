import pytest
import os
import uuid
from django.core.files.uploadedfile import SimpleUploadedFile
from src.files.models import File, FileStorage
from src.files.views import FileViewSet
from src.services.s3_file_service import S3FileService
from rest_framework.test import APIRequestFactory
from rest_framework import status
from typing import Generator


@pytest.mark.django_db
class TestFileDeduplication:
    """Test cases for file deduplication functionality"""

    @pytest.fixture
    def s3_credentials(self) -> dict[str, str]:
        """Get MinIO credentials from environment variables"""
        return {
            "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            "endpoint_url": os.getenv("AWS_ENDPOINT_URL", "http://localhost:9000"),
            "region_name": os.getenv("AWS_REGION", "us-east-1"),
        }

    @pytest.fixture
    def test_bucket_name(self) -> str:
        """Generate unique bucket name for test isolation"""
        return f"test-dedup-{str(uuid.uuid4())}"

    @pytest.fixture
    def s3_service(
        self, s3_credentials: dict[str, str], test_bucket_name: str
    ) -> Generator[S3FileService, None, None]:
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

    @pytest.fixture(autouse=True)
    def setup_method(
        self,
        s3_service: S3FileService,
        s3_credentials: dict[str, str],
        test_bucket_name: str,
        monkeypatch,
    ):
        """Setup for each test method with real S3 service"""
        self.factory = APIRequestFactory()
        self.s3_service = s3_service  # Store reference for use in tests

        # Set environment variables so FileViewSet creates the same S3 service
        monkeypatch.setenv("AWS_BUCKET_NAME", test_bucket_name)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3_credentials["aws_access_key_id"])
        monkeypatch.setenv(
            "AWS_SECRET_ACCESS_KEY", s3_credentials["aws_secret_access_key"]
        )
        monkeypatch.setenv("AWS_ENDPOINT_URL", s3_credentials["endpoint_url"])
        monkeypatch.setenv("AWS_REGION", s3_credentials["region_name"])

        # Create view - it will use the environment variables we just set
        self.view = FileViewSet.as_view({"post": "create"})

    def test_file_hash_calculation(self):
        """Test that file hash calculation works correctly"""
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

    def test_first_file_upload_creates_storage(self):
        """Test that uploading a new file creates FileStorage and File records"""
        file_content = b"This is a test file for upload"
        uploaded_file = SimpleUploadedFile(
            "test.txt", file_content, content_type="text/plain"
        )

        request = self.factory.post("/files/", {"file": uploaded_file})
        request.headers = {"UserId": "test_user_123"}
        response = self.view(request)

        assert response.status_code == status.HTTP_201_CREATED
        # Updated to match new API response format
        assert not response.data["is_reference"]

        # Check database records
        assert FileStorage.objects.count() == 1
        assert File.objects.count() == 1

        file_record = File.objects.first()
        assert not file_record.is_duplicate
        assert file_record.original_filename == "test.txt"
        assert file_record.file_type == "text/plain"
        assert file_record.user_id == "test_user_123"

        storage_record = FileStorage.objects.first()
        assert storage_record.reference_count == 1
        assert storage_record.size == len(file_content)

        # Verify file was actually uploaded to S3
        storage_record = FileStorage.objects.first()
        downloaded_content = self.s3_service.download_fileobj(storage_record.s3_path)
        assert downloaded_content.read() == file_content

    def test_duplicate_file_upload_reuses_storage(self):
        """Test that uploading duplicate content reuses existing storage"""
        file_content = b"Duplicate content test"

        # Upload first file
        uploaded_file1 = SimpleUploadedFile(
            "original.txt", file_content, content_type="text/plain"
        )
        request1 = self.factory.post("/files/", {"file": uploaded_file1})
        request1.headers = {"UserId": "test_user_123"}
        response1 = self.view(request1)

        assert response1.status_code == status.HTTP_201_CREATED
        assert not response1.data["is_reference"]

        # Upload duplicate file with different name
        uploaded_file2 = SimpleUploadedFile(
            "copy.txt", file_content, content_type="text/plain"  # Same content
        )
        request2 = self.factory.post("/files/", {"file": uploaded_file2})
        request2.headers = {"UserId": "test_user_123"}
        response2 = self.view(request2)

        assert response2.status_code == status.HTTP_201_CREATED
        assert response2.data["is_reference"]

        # Check database records
        assert FileStorage.objects.count() == 1  # Only one storage record
        assert File.objects.count() == 2  # Two file records

        # Check reference count was incremented
        storage_record = FileStorage.objects.first()
        assert storage_record.reference_count == 2

        # Check that both files reference the same storage
        file1 = File.objects.get(original_filename="original.txt")
        file2 = File.objects.get(original_filename="copy.txt")

        assert file1.storage == file2.storage
        assert not file1.is_duplicate  # First upload is not marked as duplicate
        assert file2.is_duplicate  # Second upload is marked as duplicate

        # Verify only one file exists in S3 (the original) - use self.s3_service
        storage_record = FileStorage.objects.first()
        downloaded_content = self.s3_service.download_fileobj(storage_record.s3_path)
        assert downloaded_content.read() == file_content

    def test_different_files_create_separate_storage(self):
        """Test that different file contents create separate storage records"""
        file_content1 = b"First file content"
        file_content2 = b"Second file content"

        # Upload first file
        uploaded_file1 = SimpleUploadedFile(
            "file1.txt", file_content1, content_type="text/plain"
        )
        request1 = self.factory.post("/files/", {"file": uploaded_file1})
        request1.headers = {"UserId": "test_user_123"}
        response1 = self.view(request1)

        # Upload second file
        uploaded_file2 = SimpleUploadedFile(
            "file2.txt", file_content2, content_type="text/plain"
        )
        request2 = self.factory.post("/files/", {"file": uploaded_file2})
        request2.headers = {"UserId": "test_user_123"}
        response2 = self.view(request2)

        # Both should be successful, neither should be duplicates
        assert response1.status_code == status.HTTP_201_CREATED
        assert response2.status_code == status.HTTP_201_CREATED
        assert not response1.data["is_reference"]
        assert not response2.data["is_reference"]

        # Should have separate storage records
        assert FileStorage.objects.count() == 2
        assert File.objects.count() == 2

        # Each storage should have reference count of 1
        for storage in FileStorage.objects.all():
            assert storage.reference_count == 1

        # Files should reference different storage
        file1 = File.objects.get(original_filename="file1.txt")
        file2 = File.objects.get(original_filename="file2.txt")
        assert file1.storage != file2.storage

        # Verify both files exist in S3 with different paths
        storages = FileStorage.objects.all()
        for storage in storages:
            downloaded_content = self.s3_service.download_fileobj(storage.s3_path)
            # Verify content matches one of our test contents
            content = downloaded_content.read()
            assert content in [file_content1, file_content2]

    def test_storage_stats_endpoint(self):
        """Test the storage statistics endpoint"""
        stats_view = FileViewSet.as_view({"get": "user_storage_stats"})

        # Initially no files - need UserID header for rate limiting
        request = self.factory.get("/files/storage_stats/")
        request.headers = {"UserId": "test_user_123"}
        response = stats_view(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user_id"] == "test_user_123"
        assert response.data["total_storage_used"] == 0
        assert response.data["original_storage_used"] == 0
        assert response.data["storage_savings"] == 0
        assert response.data["savings_percentage"] == 0.0

        # Add some test data
        file_content = b"Test content for stats"

        # Upload original file
        uploaded_file1 = SimpleUploadedFile(
            "original.txt", file_content, content_type="text/plain"
        )
        upload_request1 = self.factory.post("/files/", {"file": uploaded_file1})
        upload_request1.headers = {"UserId": "test_user_123"}
        self.view(upload_request1)

        # Upload duplicate
        uploaded_file2 = SimpleUploadedFile(
            "duplicate.txt", file_content, content_type="text/plain"
        )
        upload_request2 = self.factory.post("/files/", {"file": uploaded_file2})
        upload_request2.headers = {"UserId": "test_user_123"}
        self.view(upload_request2)

        # Check stats
        response = stats_view(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["user_id"] == "test_user_123"
        assert response.data["total_storage_used"] == len(file_content)  # deduplicated
        assert (
            response.data["original_storage_used"] == len(file_content) * 2
        )  # 2 files
        assert response.data["storage_savings"] == len(
            file_content
        )  # saved 1 file worth
        assert response.data["savings_percentage"] == 50.0  # 50% savings

    def test_find_existing_storage(self):
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

    def test_file_size_property(self):
        """Test that File.size property returns storage size"""
        storage = FileStorage.objects.create(
            file_hash="test_hash", s3_path="test/path", size=12345
        )

        file_record = File.objects.create(
            storage=storage, original_filename="test.txt", file_type="text/plain"
        )

        assert file_record.size == 12345

    def test_multiple_duplicates_increment_reference_count(self):
        """Test that multiple uploads of the same content properly increment reference count"""
        file_content = b"Content for multiple duplicate test"
        filenames = ["file1.txt", "file2.txt", "file3.txt", "file4.txt"]

        for i, filename in enumerate(filenames):
            uploaded_file = SimpleUploadedFile(
                filename, file_content, content_type="text/plain"
            )
            request = self.factory.post("/files/", {"file": uploaded_file})
            request.headers = {"UserId": "test_user_123"}
            response = self.view(request)

            assert response.status_code == status.HTTP_201_CREATED

            # First upload should not be duplicate, others should be
            expected_duplicate = i > 0
            assert response.data["is_reference"] == expected_duplicate

        # Should have only one storage record with reference count = 4
        assert FileStorage.objects.count() == 1
        assert File.objects.count() == 4

        storage_record = FileStorage.objects.first()
        assert storage_record.reference_count == 4

        # Only first file should not be marked as duplicate
        files = File.objects.order_by("uploaded_at")
        assert not files[0].is_duplicate
        for file_record in files[1:]:
            assert file_record.is_duplicate

        # Verify only one file exists in S3
        storage_record = FileStorage.objects.first()
        downloaded_content = self.s3_service.download_fileobj(storage_record.s3_path)
        assert downloaded_content.read() == file_content

    def test_s3_upload_failure_handling(self, monkeypatch):
        """Test that S3 upload failures are handled properly"""
        # Set invalid S3 credentials to cause failure
        monkeypatch.setenv("AWS_BUCKET_NAME", "nonexistent-bucket-" + str(uuid.uuid4()))
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "invalid")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "invalid")
        monkeypatch.setenv("AWS_ENDPOINT_URL", "http://invalid-endpoint:9000")

        # Create new view with failing credentials
        failing_view = FileViewSet.as_view({"post": "create"})

        file_content = b"Test content for S3 failure"
        uploaded_file = SimpleUploadedFile(
            "test.txt", file_content, content_type="text/plain"
        )

        request = self.factory.post("/files/", {"file": uploaded_file})
        request.headers = {"UserId": "test_user_123"}
        response = failing_view(request)

        # Should return error response
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to upload to S3" in response.data["error"]

        # No database records should be created on S3 failure
        assert FileStorage.objects.count() == 0
        assert File.objects.count() == 0

    def test_empty_file_upload(self):
        """Test uploading an empty file"""
        empty_content = b""
        uploaded_file = SimpleUploadedFile(
            "empty.txt", empty_content, content_type="text/plain"
        )

        request = self.factory.post("/files/", {"file": uploaded_file})
        request.headers = {"UserId": "test_user_123"}
        response = self.view(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert not response.data["is_reference"]

        # Should create records even for empty files
        assert FileStorage.objects.count() == 1
        assert File.objects.count() == 1

        storage_record = FileStorage.objects.first()
        assert storage_record.size == 0

        file_record = File.objects.first()
        assert file_record.size == 0

    def test_userid_header_required(self):
        """Test that UserId header is required"""
        file_content = b"Test file for auth"
        uploaded_file = SimpleUploadedFile(
            "test.txt", file_content, content_type="text/plain"
        )

        # Request without UserId header
        request = self.factory.post("/files/", {"file": uploaded_file})
        response = self.view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "UserId header is required" in response.data["error"]

        # No database records should be created
        assert FileStorage.objects.count() == 0
        assert File.objects.count() == 0

    def test_storage_limit_enforcement(self):
        """Test that storage limits are enforced"""
        # Create a large file that exceeds 10MB limit
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        uploaded_file = SimpleUploadedFile(
            "large.txt", large_content, content_type="text/plain"
        )

        request = self.factory.post("/files/", {"file": uploaded_file})
        request.headers = {"UserId": "test_user_123"}
        response = self.view(request)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Storage Quota Exceeded" in response.data["error"]
        assert response.data["limit_bytes"] == 10 * 1024 * 1024
        assert response.data["attempted_upload_bytes"] == 11 * 1024 * 1024

        # No database records should be created
        assert FileStorage.objects.count() == 0
        assert File.objects.count() == 0