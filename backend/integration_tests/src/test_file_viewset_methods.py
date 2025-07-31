import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, APIClient
from rest_framework import status
from files.views import FileViewSet
from files.models import File
from typing import Any


@pytest.fixture
def api_request_factory():
    """
  Fixture providing APIRequestFactory for creating test requests.

  Returns:
      APIRequestFactory: Factory for creating HTTP requests
  """
    return APIRequestFactory()


@pytest.fixture
def file_viewset():
    """
  Fixture providing FileViewSet instance for testing.

  Returns:
      FileViewSet: ViewSet instance for file operations
  """
    return FileViewSet()


@pytest.fixture
def test_file():
    """
  Fixture providing a simple uploaded file for testing.

  Returns:
      SimpleUploadedFile: Test file with known content
  """
    return SimpleUploadedFile(
        name="test.txt",
        content=b"test content",
        content_type="text/plain"
    )


@pytest.fixture
def test_file_large():
    """
  Fixture providing a larger uploaded file for edge case testing.

  Returns:
      SimpleUploadedFile: Large test file (1KB content)
  """
    large_content = b"A" * 1024  # 1KB of 'A' characters
    return SimpleUploadedFile(
        name="large_test.txt",
        content=large_content,
        content_type="text/plain"
    )


@pytest.fixture
def valid_user_id():
    """
  Fixture providing a valid user ID for testing.

  Returns:
      str: Test user identifier
  """
    return "test_user_123"


@pytest.mark.django_db
class TestFileViewSetMethodsIntegration:
    """Integration tests for FileViewSet individual methods using pytest fixtures."""

    def test_validate_file_upload_success(self, api_request_factory, file_viewset, test_file):
        """
        Test successful file validation using fixtures.

        Validates that the method returns a valid uploaded file object with correct
        properties, regardless of the specific file object type (Django may convert
        SimpleUploadedFile to InMemoryUploadedFile during request processing).

        Args:
            api_request_factory: Factory for creating HTTP requests
            file_viewset: FileViewSet instance
            test_file: Test uploaded file
        """
        request = api_request_factory.post('/', {'file': test_file})
        result = file_viewset._validate_file_upload(request)

        # Assert that result is a valid uploaded file object (not error Response)
        assert not hasattr(result, 'status_code'), "Expected file object, got Response"

        # Assert file properties are preserved correctly
        assert result.name == "test.txt", f"Expected filename 'test.txt', got '{result.name}'"
        assert result.content_type == "text/plain", f"Expected 'text/plain', got '{result.content_type}'"
        assert result.size == len(b"test content"), f"Expected size {len(b'test content')}, got {result.size}"

        # Assert file content is accessible and correct
        file_content = result.read()
        assert file_content == b"test content", f"Expected b'test content', got {file_content}"

        # Assert file pointer can be reset (important for subsequent operations)
        result.seek(0)
        assert result.read() == b"test content", "File content should be readable after seek(0)"

    def test_validate_file_upload_failure(self, api_request_factory, file_viewset):
        """
    Test file validation failure when no file provided.

    Args:
        api_request_factory: Factory for creating HTTP requests
        file_viewset: FileViewSet instance
    """
        request = api_request_factory.post('/', {})  # No file uploaded
        result = file_viewset._validate_file_upload(request)

        # Assert error Response is returned
        assert hasattr(result, 'status_code')
        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert 'No file provided' in result.data['error']

    def test_extract_user_id_success(self, api_request_factory, file_viewset, valid_user_id):
        """
    Test successful user ID extraction from headers.

    Args:
        api_request_factory: Factory for creating HTTP requests
        file_viewset: FileViewSet instance
        valid_user_id: Valid test user ID
    """
        request = api_request_factory.get('/', HTTP_USERID=valid_user_id)
        result = file_viewset._extract_user_id(request)

        # Assert user ID is extracted correctly
        assert result == valid_user_id
        assert isinstance(result, str)

    def test_extract_user_id_failure(self, api_request_factory, file_viewset):
        """
    Test user ID extraction failure when header missing.

    Args:
        api_request_factory: Factory for creating HTTP requests
        file_viewset: FileViewSet instance
    """
        request = api_request_factory.get('/')  # No UserId header
        result = file_viewset._extract_user_id(request)

        # Assert error Response is returned
        assert hasattr(result, 'status_code')
        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert 'UserId header is required' in result.data['error']

    def test_process_file_content_success(self, file_viewset, test_file):
        """Test successful file content processing and hash calculation."""
        # Reset file pointer to ensure clean test state
        test_file.seek(0)

        file_content, file_hash = file_viewset._process_file_content(test_file)

        # Assert file content is read correctly
        assert file_content == b"test content"
        assert isinstance(file_content, bytes)

        # Assert hash is calculated correctly
        assert isinstance(file_hash, str)
        assert len(file_hash) == 64  # SHA-256 hex length

        # Verify file pointer was reset (can read again)
        assert test_file.read() == b"test content"

    def test_process_file_content_with_large_file(self, file_viewset, test_file_large):
        """
    Test file content processing with larger file.

    Args:
        file_viewset: FileViewSet instance
        test_file_large: Large test uploaded file
    """
        file_content, file_hash = file_viewset._process_file_content(test_file_large)

        # Assert large file is processed correctly
        assert len(file_content) == 1024
        assert isinstance(file_hash, str)
        assert len(file_hash) == 64

    def test_prepare_file_data_creates_correct_structure(self, file_viewset, test_file, valid_user_id):
        """Test that file data preparation creates correct dictionary structure."""
        test_hash = "abc123def456"  # Mock hash for testing

        # ← FIX: Add required dedup_metadata parameter
        dedup_metadata = {
            'is_reference': False,
            'original_file': None,
            'reference_count': 1
        }

        result = file_viewset._prepare_file_data(test_file, valid_user_id, test_hash, dedup_metadata)

        # Assert all required fields are present
        expected_fields = {
            'file', 'original_filename', 'file_type', 'size', 'user_id', 'file_hash',
            'is_reference', 'original_file', 'reference_count'  # ← Add missing fields
        }
        actual_fields = set(result.keys())
        assert actual_fields == expected_fields

        # Assert field values are correct
        assert result['file'] == test_file
        assert result['original_filename'] == "test.txt"
        assert result['file_type'] == "text/plain"
        assert result['size'] == len(b"test content")
        assert result['user_id'] == valid_user_id
        assert result['file_hash'] == test_hash

    def test_user_specific_deduplication_workflow(self):
        """Integration test for user-specific deduplication workflow."""
        client = APIClient()
        upload_url = '/api/files/'

        # Same content for all uploads
        test_content = b"Shared document content"
        user1_id = "user_001"
        user2_id = "user_002"

        # User 1: First upload - should create original file
        file1 = SimpleUploadedFile("doc1.txt", test_content, content_type="text/plain")
        response1 = client.post(
            upload_url,
            {'file': file1},
            HTTP_USERID=user1_id,
            format='multipart'
        )

        assert response1.status_code == 201
        assert response1.data['is_reference'] is False
        assert response1.data['reference_count'] == 1
        assert response1.data['user_id'] == user1_id

        # User 1: Second upload (same content) - should create reference
        file2 = SimpleUploadedFile("doc1_copy.txt", test_content, content_type="text/plain")
        response2 = client.post(
            upload_url,
            {'file': file2},
            HTTP_USERID=user1_id,  # Same user
            format='multipart'
        )

        # DEBUG: Print error details if request fails
        if response2.status_code != 201:
            print(f"Response2 status: {response2.status_code}")
            print(f"Response2 data: {response2.data}")

        assert response2.status_code == 201
        assert response2.data['is_reference'] is True  # This is a reference
        assert response2.data['original_file'] == response1.data['id']
        assert response2.data['user_id'] == user1_id

        # User 2: Upload same content - should create NEW original file (not reference)
        file3 = SimpleUploadedFile("doc2.txt", test_content, content_type="text/plain")
        response3 = client.post(
            upload_url,
            {'file': file3},
            HTTP_USERID=user2_id,  # Different user
            format='multipart'
        )

        assert response3.status_code == 201
        assert response3.data['is_reference'] is False  # New original for user 2
        assert response3.data['reference_count'] == 1
        assert response3.data['original_file'] is None
        assert response3.data['user_id'] == user2_id

        # Verify user 1's original file reference count was updated
        user1_original = File.objects.get(id=response1.data['id'])
        assert user1_original.reference_count == 2  # Original + 1 reference
        assert user1_original.user_id == user1_id

        # Verify user 2's file is completely separate
        user2_original = File.objects.get(id=response3.data['id'])
        assert user2_original.reference_count == 1  # Only original
        assert user2_original.user_id == user2_id

        # Verify same hash but different user context
        assert response1.data['file_hash'] == response3.data['file_hash']  # Same content hash
        assert user1_original.id != user2_original.id  # Different file records


@pytest.fixture(scope="session")
def django_db_setup():
    """
  Fixture for Django database setup at session level.

  This ensures database is properly configured for integration tests.
  """
    pass  # Django test database will be created automatically
