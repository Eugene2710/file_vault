from rest_framework import serializers
from .models import File


class FileSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()  # File URL
    size = serializers.ReadOnlyField()  # Property from storage
    file_hash = serializers.SerializerMethodField()  # Hash from storage
    reference_count = (
        serializers.SerializerMethodField()
    )  # Reference count from storage
    is_reference = serializers.SerializerMethodField()  # Maps to is_duplicate
    original_file = (
        serializers.SerializerMethodField()
    )  # Always null for this implementation

    class Meta:
        model = File
        fields = [
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
        read_only_fields = [
            "id",
            "uploaded_at",
            "size",
            "file_hash",
            "reference_count",
            "is_reference",
            "original_file",
        ]

    def get_file(self, obj: File) -> str:
        """Return file access URL"""
        return obj.file_url

    def get_file_hash(self, obj: File) -> str:
        """Return SHA-256 hash from storage"""
        return obj.storage.file_hash

    def get_reference_count(self, obj: File) -> int:
        """Return reference count from storage"""
        return obj.storage.reference_count

    def get_is_reference(self, obj: File) -> bool:
        """Return whether this upload was a duplicate (maps to is_duplicate)"""
        return obj.is_duplicate

    def get_original_file(self, obj: File) -> str | None:
        """
        Return the ID of the original file if this is a reference (duplicate).
        The original file is the first file uploaded with this content (is_duplicate=False)
        """
        if not obj.is_duplicate:
            return None

        # Find the original (first) file with the same storage
        original_file = File.objects.filter(
            storage=obj.storage, is_duplicate=False
        ).first()

        return str(original_file.id) if original_file else None