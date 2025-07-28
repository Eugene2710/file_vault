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

    def create(self, request, *args, **kwargs):
        """
        Handle file upload with hash calculation and user context.

        Orchestrates the file upload process by delegating to specialized methods.
        Each method has a single responsibility for better maintainability.

        Args:
            request: HTTP request containing file upload and UserId header

        Returns:
            Response: Created file data or error message
        """
        # Step 1: Validate file upload
        file_obj = self._validate_file_upload(request)
        if isinstance(file_obj, Response):  # Error response
            return file_obj

        # Step 2: Extract and validate user ID
        user_id = self._extract_user_id(request)
        if isinstance(user_id, Response):  # Error response
            return user_id

        # Step 3: Read file content and calculate hash
        file_content, file_hash = self._process_file_content(file_obj)
        if isinstance(file_content, Response):  # Error response
            return file_content

        # Step 4: Prepare data for serializer
        data = self._prepare_file_data(file_obj, user_id, file_hash)

        # Step 5: Create file record
        return self._create_file_record(data)

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

    def _prepare_file_data(self, file_obj: UploadedFile, user_id: str, file_hash: str) -> dict[str, Any]:
        """
        Prepare data dictionary for file serializer.

        Args:
            file_obj: Django uploaded file object
            user_id: User identifier from headers
            file_hash: Calculated SHA-256 hash

        Returns:
            dict: Data dictionary with all required fields for serializer
        """
        return {
            'file': file_obj,  # Django file upload object
            'original_filename': file_obj.name,  # User's original filename
            'file_type': file_obj.content_type,  # MIME type from upload
            'size': file_obj.size,  # File size in bytes
            'user_id': user_id,  # User identifier from header
            'file_hash': file_hash,  # Calculated SHA-256 hash
            # Note: reference_count, is_reference, original_file will be set by deduplication logic
        }

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
