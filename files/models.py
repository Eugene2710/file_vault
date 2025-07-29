from django.db import models
import uuid
import hashlib
from pathlib import Path


def file_upload_path(instance: models.Model, filename: str) -> str:
    """Generate file path for new file upload"""
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return str(Path("uploads") / filename)


class FileStorage(models.Model):
    """
    File Deduplication Architecture - Physical Storage Layer

    This model represents the actual file content stored in S3. It implements content-addressable
    storage using SHA-256 hashes as unique identifiers. This separation is necessary because:

    1. DEDUPLICATION: Multiple users can upload the same file (same content, different names).
       Without separation, we'd store duplicate content multiple times in S3.

    2. STORAGE EFFICIENCY: By storing unique content only once and using references, we can
       achieve significant storage savings (e.g., if 1000 users upload the same document,
       we store it once but track 1000 references).

    3. INTEGRITY: File hash ensures content integrity and enables efficient duplicate detection
       without comparing entire file contents.

    4. REFERENCE COUNTING: Tracks how many File records reference this storage, enabling
       safe cleanup when no files reference the storage anymore.

    SQL Schema:
    CREATE TABLE files_filestorage (
        id UUID PRIMARY KEY,
        file_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 hash, indexed
        s3_path VARCHAR(500) NOT NULL,          -- S3 object key
        size BIGINT NOT NULL,                   -- File size in bytes
        created_at TIMESTAMP NOT NULL,          -- When first uploaded
        reference_count INTEGER NOT NULL DEFAULT 1  -- How many File records reference this
    );
    CREATE INDEX ON files_filestorage(file_hash);

    Architecture:
    - FileStorage (1) <---> (Many) File
    - Each FileStorage has unique content (identified by hash)
    - Multiple File records can reference the same FileStorage
    - S3 cleanup only happens when reference_count reaches 0
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_hash = models.CharField(
        max_length=64, unique=True, db_index=True
    )  # SHA-256 hash
    s3_path = models.CharField(max_length=500)  # Path in S3 bucket
    size = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    reference_count = models.PositiveIntegerField(
        default=1
    )  # Track how many files reference this storage

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Storage {self.file_hash[:8]}... ({self.reference_count} refs)"


class File(models.Model):
    """
    File Deduplication Architecture - Logical File Layer

    This model represents a user's file upload with metadata. It's separated from FileStorage
    to enable deduplication while preserving user-specific file information:

    1. USER CONTEXT: Each user upload gets its own File record with their chosen filename,
       upload timestamp, and metadata, even if the content is duplicate.

    2. METADATA PRESERVATION: Users can upload the same content with different names
       (e.g., "report.pdf" vs "final_report.pdf") - each gets a separate File record.

    3. DUPLICATE TRACKING: The is_duplicate flag helps track storage savings and can
       be used for analytics or user notifications.

    4. CLEAN SEPARATION: File handles "what the user uploaded" (metadata, context)
       while FileStorage handles "what's actually stored" (content, S3 location).

    SQL Schema:
    CREATE TABLE files_file (
        id UUID PRIMARY KEY,
        storage_id UUID NOT NULL REFERENCES files_filestorage(id) ON DELETE CASCADE,
        original_filename VARCHAR(255) NOT NULL,  -- User's original filename
        file_type VARCHAR(100) NOT NULL,          -- MIME type
        uploaded_at TIMESTAMP NOT NULL,           -- When user uploaded
        is_duplicate BOOLEAN NOT NULL DEFAULT FALSE  -- Was this a duplicate upload?
    );
    CREATE INDEX ON files_file(storage_id);
    CREATE INDEX ON files_file(uploaded_at);

    Flow:
    1. User uploads file -> Calculate hash -> Check if FileStorage exists
    2. If exists: Create File pointing to existing FileStorage, increment reference_count
    3. If not exists: Create new FileStorage, upload to S3, create File pointing to it
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    storage = models.ForeignKey(
        FileStorage, on_delete=models.CASCADE, related_name="files"
    )
    user_id = models.CharField(
        max_length=255, db_index=True
    )  # User identifier from header
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_duplicate = models.BooleanField(
        default=False
    )  # Track if this was a duplicate upload

    @property
    def size(self) -> int:
        """Get file size from storage"""
        return self.storage.size

    @property
    def file_url(self) -> str:
        """Generate file access URL"""
        return f"/media/uploads/{self.id}.{self.original_filename.split('.')[-1]}"

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["user_id", "-uploaded_at"]),
            models.Index(fields=["user_id"]),
        ]

    def __str__(self) -> str:
        return self.original_filename

    @staticmethod
    def calculate_file_hash(file_content: bytes) -> str:
        """Calculate SHA-256 hash of file content for deduplication"""
        return hashlib.sha256(file_content).hexdigest()

    @classmethod
    def find_existing_storage(cls, file_hash: str) -> "FileStorage | None":
        """Find existing storage by file hash to detect duplicates"""
        try:
            return FileStorage.objects.get(file_hash=file_hash)
        except FileStorage.DoesNotExist:
            return None