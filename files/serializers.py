from rest_framework import serializers
from .models import File

class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = [
            'id',  # UUID primary key
            'file',  # File upload field
            'original_filename',  # User's original filename
            'file_type',  # MIME type
            'size',  # File size in bytes
            'uploaded_at',  # Upload timestamp
            'user_id',  # User identifier from header
            'file_hash',  # SHA-256 hash for deduplication
            'reference_count',  # Number of references to this file
            'is_reference',  # Whether this is a duplicate reference
            'original_file'  # Reference to original file if duplicate
        ]
        read_only_fields = [
            'id',  # Generated UUID
            'uploaded_at',  # Auto-generated timestamp
            'file_hash',  # Calculated during upload
            'reference_count',  # Managed internally
            'is_reference',  # Determined by deduplication logic
            'original_file'  # Set by deduplication logic
        ]

    def validate_file_type(self, value: str) -> str:
        """
        Validate file_type is a valid MIME type format.

        Args:
            value: MIME type string (e.g., "text/plain", "image/jpeg")

        Returns:
            str: Validated MIME type

        Raises:
            ValidationError: If MIME type format is invalid
        """
        if not value or '/' not in value:
            raise serializers.ValidationError(
                "file_type must be a valid MIME type (e.g., 'text/plain')"
            )
        return value

    def validate_size(self, value: int) -> int:
        """
        Validate file size is within acceptable limits.

        Args:
            value: File size in bytes

        Returns:
            int: Validated file size

        Raises:
            ValidationError: If file size exceeds limit
        """
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB as per requirements

        if value < 0:
            raise serializers.ValidationError("File size cannot be negative")

        if value > MAX_FILE_SIZE:
            raise serializers.ValidationError(
                f"File size ({value} bytes) exceeds maximum allowed ({MAX_FILE_SIZE} bytes)"
            )

        return value