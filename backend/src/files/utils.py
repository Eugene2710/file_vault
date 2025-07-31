import hashlib
from typing import BinaryIO
from django.core.files.uploadedfile import UploadedFile


def calculate_file_hash(file_obj: UploadedFile) -> str:
    """
    Calculate SHA-256 hash of an uploaded file.

    Args:
        file_obj: Django UploadedFile object containing the file data

    Returns:
        str: Hexadecimal SHA-256 hash string (64 characters)

    Explanation:
        - hashlib.sha256() creates a new SHA-256 hash object
        - We read the file in 4KB chunks to handle large files efficiently
        - file_obj.seek(0) resets file pointer to beginning after hashing
        - hexdigest() returns the hash as a hexadecimal string
    """
    hash_obj = hashlib.sha256()  # Create SHA-256 hash object

    # Read file in chunks to handle large files without loading into memory
    for chunk in file_obj.chunks(chunk_size=4096):
        hash_obj.update(chunk)  # Update hash with current chunk

    # Reset file pointer to beginning for subsequent operations
    file_obj.seek(0)

    return hash_obj.hexdigest()  # Return 64-character hex string