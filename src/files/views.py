from typing import Tuple, Optional, Any
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.request import Request
from django.core.files.uploadedfile import UploadedFile
from .models import File
from .serializers import FileSerializer


# Create your views here.

class FileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for File operations with deduplication support.

    Handles file upload, hash calculation, and preparation for deduplication logic.
    """
    queryset = File.objects.all()
    serializer_class = FileSerializer

    def _handle_deduplication(self, file_hash: str, user_id: str) -> dict[str, Any]:
        """
        Handle user-specific file deduplication by checking for existing files with same hash.

        This method implements user-scoped deduplication logic:
        1. Check if the SAME USER has uploaded a file with the same hash before
        2. If exists: increment reference count and mark as reference
        3. If not exists: this will be the original file for this user

        Note: Deduplication is user-specific for privacy and security.
        Different users can have the same file content without cross-references.

        Args:
            file_hash: SHA-256 hash of the file content
            user_id: User identifier for the upload

        Returns:
            dict: Deduplication metadata containing:
                - is_reference: Whether this is a duplicate upload for this user
                - original_file: Reference to original file if duplicate
                - reference_count: Updated reference count
        """
        try:
            # Look for existing file with same hash FOR THE SAME USER
            existing_file = File.objects.filter(
                file_hash=file_hash,
                user_id=user_id  # CRITICAL: Only check within user's files
            ).first()

            if existing_file:
                # Duplicate found for this user - this is a reference to existing file

                # Find the original file (the one with is_reference=False for this user)
                original_file = existing_file if not existing_file.is_reference else existing_file.original_file

                # Increment reference count on original file
                original_file.reference_count += 1
                original_file.save(update_fields=['reference_count'])

                return {
                    'is_reference': True,  # Mark as duplicate
                    'original_file': original_file.id,  # Point to original
                    'reference_count': 1,  # This reference has count 1
                    'file': original_file.file,  # Use original file path
                }
            else:
                # No duplicate found for this user - this is original file
                return {
                    'is_reference': False,  # Mark as original
                    'original_file': None,  # No original (this is it)
                    'reference_count': 1,  # Initial reference count
                }

        except Exception as e:
            # Log error but don't fail upload - treat as new file
            # In production, you'd use proper logging
            print(f"User-specific deduplication check failed for user {user_id}: {str(e)}")
            return {
                'is_reference': False,
                'original_file': None,
                'reference_count': 1,
            }

    def _prepare_file_data(
            self,
            file_obj: UploadedFile,
            user_id: str,
            file_hash: str,
            dedup_metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Prepare data dictionary for file serializer including deduplication metadata.

        Args:
            file_obj: Django uploaded file object
            user_id: User identifier from headers
            file_hash: Calculated SHA-256 hash
            dedup_metadata: Deduplication information from _handle_deduplication

        Returns:
            dict: Data dictionary with all required fields for serializer
        """
        data = {
            'original_filename': file_obj.name,  # User's original filename
            'file_type': file_obj.content_type,  # MIME type from upload
            'size': file_obj.size,  # File size in bytes
            'user_id': user_id,  # User identifier from header
            'file_hash': file_hash,  # Calculated SHA-256 hash
            'is_reference': dedup_metadata['is_reference'],  # Duplicate flag
            'original_file': dedup_metadata['original_file'],  # Original file reference
            'reference_count': dedup_metadata['reference_count'],  # Reference count
        }

        # Only include file upload for non-duplicates (new files)
        if not dedup_metadata['is_reference']:
            data['file'] = file_obj  # Only upload new files to storage
        # else:
        #     # Reference file: reuse the original file's path/name
        #     # We need to set the file field to the same path as the original
        #     original_file = dedup_metadata['original_file']
        #     data['file'] = original_file.file.name  # Just the file path/name string

        return data

    def _validate_file_upload(self, request: Request) -> UploadedFile | Response:
        """
        Validate that a file was uploaded in the request.

        Args:
            request: HTTP request to check for file upload

        Returns:
            UploadedFile: The uploaded file object if valid
            Response: Error response if no file provided
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return file_obj

    def _extract_user_id(self, request: Request) -> str | Response:
        """
        Extract and validate user ID from request headers.

        Args:
            request: HTTP request containing UserId header

        Returns:
            str: User ID if present in headers
            Response: Error response if UserId header missing
        """
        user_id = request.headers.get('UserId')
        if not user_id:
            return Response(
                {'error': 'UserId header is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return user_id

    def _process_file_content(self, file_obj: UploadedFile) -> tuple[bytes | Response, Optional[str]]:
        """
        Read file content and calculate SHA-256 hash for deduplication.

        Args:
            file_obj: Django uploaded file object

        Returns:
            Tuple[bytes | Response, Optional[str]]:
                - File content as bytes or error Response
                - SHA-256 hash string if successful, None if error
        """
        try:
            file_content = file_obj.read()  # Read entire file content as bytes
            file_obj.seek(0)  # Reset file pointer for subsequent operations

            # Calculate hash using File model's static method
            file_hash = File.calculate_file_hash(file_content)

            return file_content, file_hash

        except Exception as e:
            error_response = Response(
                {'error': f'Failed to read file content: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
            return error_response, None

    # def _prepare_file_data(self, file_obj: UploadedFile, user_id: str, file_hash: str) -> dict[str, Any]:
    #     """
    #     Prepare data dictionary for file serializer.
    #
    #     Args:
    #         file_obj: Django uploaded file object
    #         user_id: User identifier from headers
    #         file_hash: Calculated SHA-256 hash
    #
    #     Returns:
    #         dict: Data dictionary with all required fields for serializer
    #     """
    #     return {
    #         'file': file_obj,  # Django file upload object
    #         'original_filename': file_obj.name,  # User's original filename
    #         'file_type': file_obj.content_type,  # MIME type from upload
    #         'size': file_obj.size,  # File size in bytes
    #         'user_id': user_id,  # User identifier from header
    #         'file_hash': file_hash,  # Calculated SHA-256 hash
    #         # Note: reference_count, is_reference, original_file will be set by deduplication logic
    #     }

    def _create_file_record(self, data: dict[str, Any]) -> Response:
        """
        Create file record using serializer validation and save.

        Args:
            data: Dictionary containing all file data for creation

        Returns:
            Response: Created file data with 201 status or validation errors
        """
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def create(self, request: Request, *args, **kwargs) -> Response:
        """
        Handle file upload with hash calculation, deduplication, and user context.

        Flow:
        1. Validate file upload
        2. Extract user_id from headers
        3. Read file content and calculate hash
        4. Check for duplicates and handle deduplication
        5. Prepare data for serializer with deduplication metadata
        6. Create file record

        Args:
            request: HTTP request containing file upload and UserId header

        Returns:
            Response: Created file data or error message
        """
        # Steps 1-3
        file_obj = self._validate_file_upload(request)
        if isinstance(file_obj, Response):
            return file_obj

        user_id = self._extract_user_id(request)
        if isinstance(user_id, Response):
            return user_id

        file_content, file_hash = self._process_file_content(file_obj)
        if isinstance(file_content, Response):
            return file_content

        # Step 4: Handle deduplication
        dedup_metadata = self._handle_deduplication(file_hash, user_id)

        # Step 5: Prepare data with deduplication metadata
        data = self._prepare_file_data(file_obj, user_id, file_hash, dedup_metadata)

        # Step 6: Create file record
        return self._create_file_record(data)
