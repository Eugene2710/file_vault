import os
import pytest
from unittest.mock import patch

from src.services.storage_limit_service import StorageLimitService, StorageQuotaInfo
from src.files.models import File, FileStorage


@pytest.mark.django_db
class TestStorageLimitServiceIntegration:
    """Integration tests for StorageLimitService using real database"""

    @pytest.fixture
    def storage_service(self) -> StorageLimitService:
        """Create a fresh storage service instance for each test."""
        return StorageLimitService()

    @pytest.fixture
    def test_user_id(self) -> str:
        """Test user ID for isolation."""
        return "test_user_123"

    @pytest.fixture
    def test_user_id_2(self) -> str:
        """Second test user ID for multi-user tests."""
        return "test_user_456"

    def test_initialization_with_default_values(
        self, storage_service: StorageLimitService
    ) -> None:
        """Test storage service initializes with default environment values."""
        assert storage_service.limit_mb == 10
        assert storage_service.limit_bytes == 10 * 1024 * 1024

    @patch.dict(os.environ, {"TOTAL_STORAGE_LIMIT_Z_MB": "25"})
    def test_initialization_with_custom_env_values(self) -> None:
        """Test storage service initializes with custom environment values."""
        service = StorageLimitService()
        assert service.limit_mb == 25
        assert service.limit_bytes == 25 * 1024 * 1024

    def test_get_limit_mb(self, storage_service: StorageLimitService) -> None:
        """Test getting the storage limit in MB."""
        limit = storage_service.get_limit_mb()
        assert limit == 10

    def test_get_user_storage_usage_no_files(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test getting storage usage when user has no files."""
        usage = storage_service.get_user_storage_usage(test_user_id)
        assert usage == 0

    def test_get_user_storage_usage_with_files(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test getting storage usage when user has files."""
        # Create file storage
        storage = FileStorage.objects.create(
            file_hash="abcd1234567890",
            s3_path="test/file1.txt",
            size=3 * 1024 * 1024,  # 3MB
        )

        # Create file record for user
        File.objects.create(
            storage=storage,
            user_id=test_user_id,
            original_filename="file1.txt",
            file_type="text/plain",
        )

        usage = storage_service.get_user_storage_usage(test_user_id)
        assert usage == 3 * 1024 * 1024

    def test_check_storage_limit_within_limit(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test storage limit check when within limit."""
        # Create existing files totaling 5MB
        storage = FileStorage.objects.create(
            file_hash="existing123", s3_path="test/existing.txt", size=5 * 1024 * 1024
        )
        File.objects.create(
            storage=storage,
            user_id=test_user_id,
            original_filename="existing.txt",
            file_type="text/plain",
        )

        # Try to add 3MB (total would be 8MB, under 10MB limit)
        additional_size = 3 * 1024 * 1024
        is_allowed, message = storage_service.check_storage_limit(
            test_user_id, additional_size
        )

        assert is_allowed is True
        assert message == ""

    def test_check_storage_limit_exceeds_limit(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test storage limit check when exceeding limit."""
        # Create existing files totaling 8MB
        storage = FileStorage.objects.create(
            file_hash="existing456", s3_path="test/large.txt", size=8 * 1024 * 1024
        )
        File.objects.create(
            storage=storage,
            user_id=test_user_id,
            original_filename="large.txt",
            file_type="text/plain",
        )

        # Try to add 5MB (total would be 13MB, over 10MB limit)
        additional_size = 5 * 1024 * 1024
        is_allowed, message = storage_service.check_storage_limit(
            test_user_id, additional_size
        )

        assert is_allowed is False
        assert message == "Storage Quota Exceeded"

    def test_check_storage_limit_exactly_at_limit(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test storage limit check when exactly at limit."""
        # Create existing files totaling 7MB
        storage = FileStorage.objects.create(
            file_hash="existing789", s3_path="test/medium.txt", size=7 * 1024 * 1024
        )
        File.objects.create(
            storage=storage,
            user_id=test_user_id,
            original_filename="medium.txt",
            file_type="text/plain",
        )

        # Try to add exactly 3MB (total would be exactly 10MB)
        additional_size = 3 * 1024 * 1024
        is_allowed, message = storage_service.check_storage_limit(
            test_user_id, additional_size
        )

        assert is_allowed is True
        assert message == ""

    def test_get_storage_quota_info_empty_usage(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test getting quota info when user has no files."""
        quota_info = storage_service.get_storage_quota_info(test_user_id)

        assert isinstance(quota_info, StorageQuotaInfo)
        assert quota_info.user_id == test_user_id
        assert quota_info.current_usage_bytes == 0
        assert quota_info.limit_bytes == 10 * 1024 * 1024
        assert quota_info.available_bytes == 10 * 1024 * 1024
        assert quota_info.usage_percentage == 0.0

    def test_get_storage_quota_info_partial_usage(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test getting quota info when user has partial usage."""
        # Create files totaling 3MB (30% of 10MB limit)
        storage = FileStorage.objects.create(
            file_hash="partial123", s3_path="test/partial.txt", size=3 * 1024 * 1024
        )
        File.objects.create(
            storage=storage,
            user_id=test_user_id,
            original_filename="partial.txt",
            file_type="text/plain",
        )

        quota_info = storage_service.get_storage_quota_info(test_user_id)

        assert quota_info.user_id == test_user_id
        assert quota_info.current_usage_bytes == 3 * 1024 * 1024
        assert quota_info.limit_bytes == 10 * 1024 * 1024
        assert quota_info.available_bytes == 7 * 1024 * 1024
        assert quota_info.usage_percentage == 30.0

    def test_get_storage_quota_info_full_usage(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test getting quota info when user is at 100% usage."""
        # Create files totaling 10MB (100% of 10MB limit)
        storage = FileStorage.objects.create(
            file_hash="full123", s3_path="test/full.txt", size=10 * 1024 * 1024
        )
        File.objects.create(
            storage=storage,
            user_id=test_user_id,
            original_filename="full.txt",
            file_type="text/plain",
        )

        quota_info = storage_service.get_storage_quota_info(test_user_id)

        assert quota_info.current_usage_bytes == 10 * 1024 * 1024
        assert quota_info.available_bytes == 0
        assert quota_info.usage_percentage == 100.0

    def test_get_storage_quota_info_over_usage(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test getting quota info when user is over 100% usage."""
        # Create files totaling 12MB (120% of 10MB limit)
        storage = FileStorage.objects.create(
            file_hash="over123", s3_path="test/over.txt", size=12 * 1024 * 1024
        )
        File.objects.create(
            storage=storage,
            user_id=test_user_id,
            original_filename="over.txt",
            file_type="text/plain",
        )

        quota_info = storage_service.get_storage_quota_info(test_user_id)

        assert quota_info.current_usage_bytes == 12 * 1024 * 1024
        assert quota_info.available_bytes == 0  # Can't be negative
        assert quota_info.usage_percentage == 100.0  # Capped at 100%

    @patch.dict(os.environ, {"TOTAL_STORAGE_LIMIT_Z_MB": "50"})
    def test_different_storage_limits(self, test_user_id: str) -> None:
        """Test that different storage limits work correctly."""
        service = StorageLimitService()

        # Create files totaling 30MB
        storage = FileStorage.objects.create(
            file_hash="custom123", s3_path="test/custom.txt", size=30 * 1024 * 1024
        )
        File.objects.create(
            storage=storage,
            user_id=test_user_id,
            original_filename="custom.txt",
            file_type="text/plain",
        )

        # With 50MB limit, 30MB usage should be 60%
        quota_info = service.get_storage_quota_info(test_user_id)

        assert quota_info.limit_bytes == 50 * 1024 * 1024
        assert quota_info.current_usage_bytes == 30 * 1024 * 1024
        assert quota_info.available_bytes == 20 * 1024 * 1024
        assert quota_info.usage_percentage == 60.0

    def test_multiple_users_isolation(
        self,
        storage_service: StorageLimitService,
        test_user_id: str,
        test_user_id_2: str,
    ) -> None:
        """Test that storage limits are isolated between users."""
        # Create 8MB file for user1
        storage1 = FileStorage.objects.create(
            file_hash="user1file", s3_path="test/user1.txt", size=8 * 1024 * 1024
        )
        File.objects.create(
            storage=storage1,
            user_id=test_user_id,
            original_filename="user1.txt",
            file_type="text/plain",
        )

        # Create 2MB file for user2
        storage2 = FileStorage.objects.create(
            file_hash="user2file", s3_path="test/user2.txt", size=2 * 1024 * 1024
        )
        File.objects.create(
            storage=storage2,
            user_id=test_user_id_2,
            original_filename="user2.txt",
            file_type="text/plain",
        )

        # Check user1 (8MB usage)
        quota_info1 = storage_service.get_storage_quota_info(test_user_id)
        assert quota_info1.current_usage_bytes == 8 * 1024 * 1024
        assert quota_info1.usage_percentage == 80.0

        # Check user2 (2MB usage)
        quota_info2 = storage_service.get_storage_quota_info(test_user_id_2)
        assert quota_info2.current_usage_bytes == 2 * 1024 * 1024
        assert quota_info2.usage_percentage == 20.0

    def test_multiple_files_same_user(
        self, storage_service: StorageLimitService, test_user_id: str
    ) -> None:
        """Test storage calculation with multiple files for same user."""
        # Create multiple files for the same user
        storage1 = FileStorage.objects.create(
            file_hash="multi1", s3_path="test/file1.txt", size=2 * 1024 * 1024  # 2MB
        )
        File.objects.create(
            storage=storage1,
            user_id=test_user_id,
            original_filename="file1.txt",
            file_type="text/plain",
        )

        storage2 = FileStorage.objects.create(
            file_hash="multi2", s3_path="test/file2.txt", size=3 * 1024 * 1024  # 3MB
        )
        File.objects.create(
            storage=storage2,
            user_id=test_user_id,
            original_filename="file2.txt",
            file_type="text/plain",
        )

        # Total should be 5MB
        usage = storage_service.get_user_storage_usage(test_user_id)
        assert usage == 5 * 1024 * 1024

        quota_info = storage_service.get_storage_quota_info(test_user_id)
        assert quota_info.usage_percentage == 50.0

    @patch.dict(os.environ, {"TOTAL_STORAGE_LIMIT_Z_MB": "0"})
    def test_zero_limit_edge_case(self, test_user_id: str) -> None:
        """Test behavior when limit is set to zero."""
        service = StorageLimitService()

        # Any upload should fail with zero limit
        is_allowed, message = service.check_storage_limit(test_user_id, 1)
        assert is_allowed is False
        assert message == "Storage Quota Exceeded"

        quota_info = service.get_storage_quota_info(test_user_id)
        assert quota_info.limit_bytes == 0
        assert quota_info.usage_percentage == 0.0