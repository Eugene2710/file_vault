import os
from functools import wraps
from typing import Callable, Any

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.db.models import QuerySet

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.pagination import PageNumberPagination
from django.http import HttpResponse
from .models import File, FileStorage
from .serializers import FileSerializer
import io

from ..services.rate_limiter_service import RateLimiterService
from ..services.s3_file_service import S3FileService
from ..services.storage_limit_service import StorageLimitService


def rate_limit_required(func: Callable[[...], Any]) -> Callable[[...], Any]:
    """Decorator to apply rate limiting to view methods"""

    @wraps(func)
    def wrapper(self, request: Request, *args, **kwargs):
        user_id: str | None = self._get_user_id(request)
        if not user_id:
            return Response(
                {"error": "UserId header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_allowed, message, request_id = self.rate_limiter.is_allowed(user_id)
        if not is_allowed:
            rate_info = self.rate_limiter.get_rate_limit_info(user_id)
            return Response(
                {
                    "error": message,
                    "request_id": request_id,
                    "rate_limit_info": rate_info,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Add request_id to response headers for tracking
        response = func(self, request, *args, **kwargs)
        if hasattr(response, "headers"):
            response.headers["X-Request-ID"] = request_id
        return response

    return wrapper


class FilesPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# Create your views here.


class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    pagination_class = FilesPagination

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.file_service: S3FileService = S3FileService(
            bucket_name=os.getenv("AWS_BUCKET_NAME", ""),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
        self.rate_limiter: RateLimiterService = RateLimiterService()
        self.storage_limit_service: StorageLimitService = StorageLimitService()

    def _get_user_id(self, request: Request) -> str | None:
        """Extract and validate UserId from request headers"""
        user_id = request.headers.get("UserId")
        if not user_id or not user_id.strip():
            return None
        return user_id.strip()

    @rate_limit_required
    def list(self, request: Request, *args, **kwargs) -> Response:
        """List files for authenticated user with filtering"""
        user_id = self._get_user_id(request)

        # Start with user's files
        queryset = File.objects.filter(user_id=user_id).select_related("storage")

        # Apply filters
        queryset = self._apply_filters(request, queryset)

        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # Fallback if no pagination
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @rate_limit_required
    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        """Retrieve detailed information about a specific file"""
        user_id = self._get_user_id(request)

        # Get the file instance
        instance = self.get_object()

        # Check if the file belongs to the requesting user
        if instance.user_id != user_id:
            # Return 404 instead of 403 to not leak file existence
            return Response(
                {"error": "File not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Serialize and return the file details
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def _apply_filters(
            self, request: Request, queryset: QuerySet[File]
    ) -> QuerySet[File]:
        """Apply query parameter filters to the queryset"""
        # Search by filename (case-insensitive partial match)
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(original_filename__icontains=search)

        # Filter by file type (MIME type)
        file_type = request.query_params.get("file_type")
        if file_type:
            queryset = queryset.filter(file_type=file_type)

        # Filter by size range
        min_size = request.query_params.get("min_size")
        if min_size:
            try:
                min_size_int = int(min_size)
                queryset = queryset.filter(storage__size__gte=min_size_int)
            except ValueError:
                pass  # Ignore invalid min_size

        max_size = request.query_params.get("max_size")
        if max_size:
            try:
                max_size_int = int(max_size)
                queryset = queryset.filter(storage__size__lte=max_size_int)
            except ValueError:
                pass  # Ignore invalid max_size

        # Filter by date range
        start_date = request.query_params.get("start_date")
        if start_date:
            parsed_start = parse_datetime(start_date)
            if parsed_start:
                queryset = queryset.filter(uploaded_at__gte=parsed_start)
            else:
                # Invalid date format, ignore filter
                pass

        end_date = request.query_params.get("end_date")
        if end_date:
            parsed_end = parse_datetime(end_date)
            if parsed_end:
                queryset = queryset.filter(uploaded_at__lte=parsed_end)
            else:
                # Invalid date format, ignore filter
                pass

        return queryset.order_by("-uploaded_at")

    @rate_limit_required
    def create(self, request: Request, *args, **kwargs) -> Response:
        user_id = self._get_user_id(request)

        # Validate file upload
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response(
                {"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Read file content and calculate hash for deduplication
        file_content = file_obj.read()
        file_hash = File.calculate_file_hash(file_content)

        # Check storage limit (only for new files)
        existing_storage = File.find_existing_storage(file_hash)
        if not existing_storage:
            # This is a new file, check storage limit
            is_allowed, error_message = self.storage_limit_service.check_storage_limit(
                user_id, file_obj.size
            )
            if not is_allowed:
                quota_info = self.storage_limit_service.get_storage_quota_info(user_id)
                return Response(
                    {
                        "error": error_message,
                        "current_usage_bytes": quota_info.current_usage_bytes,
                        "limit_bytes": quota_info.limit_bytes,
                        "attempted_upload_bytes": file_obj.size,
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        is_duplicate = existing_storage is not None

        with transaction.atomic():
            if existing_storage:
                # File is duplicate - increment reference count
                existing_storage.reference_count += 1
                existing_storage.save()
                storage = existing_storage
            else:
                # New file - upload to S3 and create storage record
                file_content_io = io.BytesIO(file_content)
                source_path = (
                    f"files/{file_hash[:8]}/{file_obj.name}"  # Organize by hash prefix
                )

                try:
                    self.file_service.upload_fileobj(file_content_io, source_path)
                except Exception as e:
                    return Response(
                        {"error": f"Failed to upload to S3: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                # Create new storage record
                storage = FileStorage.objects.create(
                    file_hash=file_hash, s3_path=source_path, size=file_obj.size
                )

            # Create File record (always created, even for duplicates)
            file_record = File.objects.create(
                storage=storage,
                user_id=user_id,
                original_filename=file_obj.name,
                file_type=file_obj.content_type or "application/octet-stream",
                is_duplicate=is_duplicate,
            )

            # Serialize the file record for response
            serializer = self.get_serializer(file_record)

            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )

    @rate_limit_required
    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Delete a file and update storage usage with reference counting"""
        user_id = self._get_user_id(request)

        # Get the file instance
        try:
            instance = self.get_object()
        except File.DoesNotExist:
            return Response(
                {"error": "File not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the file belongs to the requesting user
        if instance.user_id != user_id:
            return Response(
                {"error": "File not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Handle file deletion with reference counting
        with transaction.atomic():
            storage = instance.storage

            # Delete the File record first
            instance.delete()

            # Decrement reference count and handle storage cleanup
            storage.reference_count -= 1

            if storage.reference_count <= 0:
                # No more references, delete from S3 and remove storage record
                try:
                    self.file_service.delete_file(storage.s3_path)
                except Exception as e:
                    # Log the error but don't fail the delete operation
                    # The database cleanup will still happen
                    print(f"Warning: Failed to delete file from S3: {e}")

                # Delete the storage record
                storage.delete()
            else:
                # Still has references, just update the count
                storage.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="storage_stats")
    @rate_limit_required
    def user_storage_stats(self, request: Request) -> Response:
        """Get storage usage statistics for the user"""
        user_id = self._get_user_id(request)

        # Get user's files
        user_files = File.objects.filter(user_id=user_id).select_related("storage")

        # Use StorageLimitService to get total storage used (deduplicated)
        total_storage_used = self.storage_limit_service.get_user_storage_usage(user_id)

        # Calculate original storage that would be used without deduplication
        original_storage_used = sum(file.storage.size for file in user_files)

        # Calculate savings
        storage_savings = original_storage_used - total_storage_used
        savings_percentage = (
            (storage_savings / original_storage_used * 100)
            if original_storage_used > 0
            else 0.0
        )

        return Response(
            {
                "user_id": user_id,
                "total_storage_used": total_storage_used,
                "original_storage_used": original_storage_used,
                "storage_savings": storage_savings,
                "savings_percentage": round(savings_percentage, 1),
            }
        )

    @action(detail=False, methods=["get"], url_path="file_types")
    @rate_limit_required
    def file_types(self, request: Request) -> Response:
        """Get list of unique file types (MIME types) for the user"""
        user_id = self._get_user_id(request)

        # Get unique file types for the user
        file_types = (
            File.objects.filter(user_id=user_id)
            .values_list("file_type", flat=True)
            .distinct()
            .order_by("file_type")
        )

        return Response(list(file_types))

    @action(detail=True, methods=["get"], url_path="download")
    @rate_limit_required
    def download(self, request: Request, *args, **kwargs) -> HttpResponse:
        """Download a file from S3 by file ID and UserId"""
        user_id = self._get_user_id(request)

        # Get the file instance
        try:
            instance = self.get_object()
        except File.DoesNotExist:
            return HttpResponse("File not found", status=404)

        # Check if the file belongs to the requesting user
        if instance.user_id != user_id:
            return HttpResponse("File not found", status=404)

        try:
            # Download file from S3
            file_obj = self.file_service.download_fileobj(instance.storage.s3_path)
            file_content = file_obj.read()

            # Create HTTP response with the file content
            response = HttpResponse(
                file_content,
                content_type=instance.file_type or 'application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{instance.original_filename}"'
            response['Content-Length'] = str(instance.storage.size)

            return response

        except Exception as e:
            return HttpResponse(f"Failed to download file: {str(e)}", status=500)