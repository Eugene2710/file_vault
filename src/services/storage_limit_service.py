import os
from dataclasses import dataclass


@dataclass
class StorageQuotaInfo:
    user_id: str
    current_usage_bytes: int
    limit_bytes: int
    available_bytes: int
    usage_percentage: float


class StorageLimitService:
    def __init__(self):
        self.limit_mb = int(os.environ.get("TOTAL_STORAGE_LIMIT_Z_MB", 10))
        self.limit_bytes = self.limit_mb * 1024 * 1024

    def get_user_storage_usage(self, user_id: str) -> int:
        """Calculate total storage usage for a user in bytes (deduplicated)"""
        from src.files.models import FileStorage

        # Get distinct storage records for this user (handles deduplication)
        user_storage_records = FileStorage.objects.filter(
            files__user_id=user_id
        ).distinct()
        return sum(storage.size for storage in user_storage_records)

    def check_storage_limit(
        self, user_id: str, additional_size: int
    ) -> tuple[bool, str]:
        """Check if user can upload additional_size without exceeding limit"""
        current_usage = self.get_user_storage_usage(user_id)

        if (current_usage + additional_size) > self.limit_bytes:
            return False, "Storage Quota Exceeded"

        return True, ""

    def get_storage_quota_info(self, user_id: str) -> StorageQuotaInfo:
        """Get detailed storage quota information for a user"""
        current_usage = self.get_user_storage_usage(user_id)
        available_bytes = max(0, self.limit_bytes - current_usage)
        usage_percentage = (
            (current_usage / self.limit_bytes) * 100 if self.limit_bytes > 0 else 0
        )

        return StorageQuotaInfo(
            user_id=user_id,
            current_usage_bytes=current_usage,
            limit_bytes=self.limit_bytes,
            available_bytes=available_bytes,
            usage_percentage=min(usage_percentage, 100.0),
        )

    def get_limit_mb(self) -> int:
        """Get the storage limit in MB"""
        return self.limit_mb