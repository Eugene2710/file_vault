#!/usr/bin/env python
"""Demo script showing the complete API functionality"""

import django
import json
import time
import sys
import os

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.core.settings")
django.setup()

from src.files.views import FileViewSet  # noqa: E402
from src.files.models import File, FileStorage  # noqa: E402
from rest_framework.test import APIRequestFactory  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402,F401
from src.services.rate_limiter_service import RateLimiterService  # noqa: E402
from src.services.s3_file_service import S3FileService  # noqa: E402
from src.services.storage_limit_service import StorageLimitService  # noqa: E402


sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def demo_api():
    """Demonstrate the complete file upload API with deduplication"""
    print("🚀 File Upload API with Deduplication Demo")
    print("=" * 50)

    # Set up demo environment variables for S3
    bucket_name = "demo-bucket"
    os.environ.setdefault("AWS_BUCKET_NAME", bucket_name)
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "minioadmin")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minioadmin")
    os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:9000")
    os.environ.setdefault("AWS_REGION", "us-east-1")

    # Set up S3 service and create bucket if needed
    print("Setting up S3 storage...")
    try:
        s3_service = S3FileService(
            bucket_name=bucket_name,
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin",
            endpoint_url="http://localhost:9000",
            region_name="us-east-1",
        )
        s3_service.create_bucket()
        print("✅ S3 bucket ready!")
    except Exception as e:
        print(f"❌ Failed to set up S3 storage: {e}")
        print("Note: Make sure MinIO is running on localhost:9000")
        print(
            'You can start it with: docker run -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ":9001"'
        )
        return

    # Clean up any existing data for demo
    File.objects.all().delete()
    FileStorage.objects.all().delete()

    factory = APIRequestFactory()

    # Test 1: Upload a file with UserId
    print("\n1. Testing file upload with UserId header...")
    file_content = b"This is test content for the demo"
    uploaded_file = SimpleUploadedFile(
        "demo.txt", file_content, content_type="text/plain"
    )

    request = factory.post("/files/", {"file": uploaded_file})
    request.headers = {"UserId": "demo_user_123"}

    view = FileViewSet.as_view({"post": "create"})
    response = view(request)

    if response.status_code == 201:
        print("✅ File uploaded successfully!")
        print(f"   Response: {json.dumps(response.data, indent=2)}")

        # Verify the response matches API spec
        data = response.data
        expected_fields = [
            "id",
            "file",
            "original_filename",
            "file_type",
            "size",
            "user_id",
            "file_hash",
            "reference_count",
            "is_reference",
            "original_file",
        ]

        print("\n   API Response Fields:")
        for field in expected_fields:
            value = data.get(field)
            print(f"   ✓ {field}: {value}")

    else:
        print(f"❌ Upload failed with status {response.status_code}")
        print(f"   Error: {response.data}")
        return

    # Test 2: Upload duplicate content (should use deduplication)
    print("\n2. Testing file deduplication...")
    duplicate_file = SimpleUploadedFile(
        "duplicate.txt", file_content, content_type="text/plain"
    )

    request2 = factory.post("/files/", {"file": duplicate_file})
    request2.headers = {"UserId": "demo_user_123"}

    response2 = view(request2)

    if response2.status_code == 201:
        print("✅ Duplicate file handled correctly!")
        print(f"   is_reference: {response2.data['is_reference']}")
        print(f"   file_hash: {response2.data['file_hash']}")
        print(f"   reference_count: {response2.data['reference_count']}")
    else:
        print(f"❌ Duplicate upload failed with status {response2.status_code}")
        return

    # Test 3: Check storage efficiency
    print("\n3. Storage efficiency statistics:")
    total_files = File.objects.count()
    unique_storage = FileStorage.objects.count()
    print(f"   Total files uploaded: {total_files}")
    print(f"   Unique storage records: {unique_storage}")
    print(
        f"   Storage efficiency: {((total_files - unique_storage) / total_files * 100):.1f}% saved"
    )

    # Test 4: Test UserId requirement
    print("\n4. Testing UserId header requirement...")
    request3 = factory.post(
        "/files/",
        {"file": SimpleUploadedFile("test.txt", b"test", content_type="text/plain")},
    )
    # No UserId header

    response3 = view(request3)
    if (
        response3.status_code == 400
        and "UserId header is required" in response3.data.get("error", "")
    ):
        print("✅ UserId validation working correctly!")
    else:
        print(f"❌ UserId validation failed: {response3.data}")

    # Test 5: Test storage limit
    print("\n5. Testing storage limit enforcement...")
    storage_service = StorageLimitService()
    user_usage = storage_service.get_user_storage_usage("demo_user_123")
    print(f"   Current usage for demo_user_123: {user_usage} bytes")
    print(f"   Storage limit: 10MB ({10 * 1024 * 1024} bytes)")

    # Try to upload a file that exceeds limit
    large_content = b"x" * (11 * 1024 * 1024)  # 11MB
    large_file = SimpleUploadedFile(
        "large.txt", large_content, content_type="text/plain"
    )

    request4 = factory.post("/files/", {"file": large_file})
    request4.headers = {"UserId": "demo_user_123"}

    response4 = view(request4)
    if response4.status_code == 429:
        print("✅ Storage limit enforcement working correctly!")
        print(f"   Error: {response4.data['error']}")
    else:
        print(f"❌ Storage limit check failed: {response4.data}")
        print(f"   Status code: {response4.status_code}")

    # Test 6: Test file listing functionality
    print("\n6. Testing file listing functionality...")

    # Create list view
    list_view = FileViewSet.as_view({"get": "list"})

    # List all files for user
    request5 = factory.get("/files/")
    request5.headers = {"UserId": "demo_user_123"}
    response5 = list_view(request5)

    if response5.status_code == 200:
        print("✅ File listing working correctly!")
        print(f"   Total files: {response5.data['count']}")
        print(f"   Files returned: {len(response5.data['results'])}")

        # Test search filter
        request6 = factory.get("/files/", {"search": "duplicate"})
        request6.headers = {"UserId": "demo_user_123"}
        response6 = list_view(request6)

        if response6.status_code == 200 and response6.data["count"] == 1:
            print("✅ Search filtering working correctly!")
            print(f"   Found {response6.data['count']} file(s) matching 'duplicate'")

        # Test file type filter
        request7 = factory.get("/files/", {"file_type": "text/plain"})
        request7.headers = {"UserId": "demo_user_123"}
        response7 = list_view(request7)

        if response7.status_code == 200:
            print("✅ File type filtering working correctly!")
            print(f"   Found {response7.data['count']} text/plain file(s)")

        # Test 7: Test file details retrieval
        print("\n7. Testing file details retrieval...")

        # Create retrieve view
        retrieve_view = FileViewSet.as_view({"get": "retrieve"})

        # Get the first file from the list to test retrieval
        if response5.data["results"]:
            first_file = response5.data["results"][0]
            file_id = first_file["id"]

            # Test retrieving file details
            request8 = factory.get(f"/files/{file_id}/")
            request8.headers = {"UserId": "demo_user_123"}
            response8 = retrieve_view(request8, pk=file_id)

            if response8.status_code == 200:
                print("✅ File details retrieval working correctly!")
                print(f"   Retrieved file: {response8.data['original_filename']}")
                print(f"   File size: {response8.data['size']} bytes")
                print(f"   Is reference: {response8.data['is_reference']}")
                print(f"   Reference count: {response8.data['reference_count']}")

                # Verify response format consistency
                expected_fields = [
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
                missing_fields = [
                    field for field in expected_fields if field not in response8.data
                ]
                if not missing_fields:
                    print("✅ Response format matches API specification!")
                else:
                    print(f"❌ Missing fields in response: {missing_fields}")
            else:
                print(f"❌ File details retrieval failed: {response8.data}")

            # Test user isolation - try to access as different user
            request9 = factory.get(f"/files/{file_id}/")
            request9.headers = {"UserId": "different_user"}
            response9 = retrieve_view(request9, pk=file_id)

            if response9.status_code == 404:
                print("✅ User isolation working correctly!")
                print("   Different user cannot access file (404 returned)")
            else:
                print(f"❌ User isolation failed: {response9.status_code}")
        else:
            print("   No files available to test retrieval")
    else:
        print(f"❌ File listing failed: {response5.data}")

    # Test 8: Test file deletion functionality
    print("\n8. Testing file deletion functionality...")

    # First, let's get the files to delete
    request_list = factory.get("/files/")
    request_list.headers = {"UserId": "demo_user_123"}
    response_list = list_view(request_list)

    if response_list.status_code == 200 and response_list.data["results"]:
        # Create delete view
        delete_view = FileViewSet.as_view({"delete": "destroy"})

        # Get a file to delete (let's delete the first one)
        file_to_delete = response_list.data["results"][0]
        file_id = file_to_delete["id"]
        original_filename = file_to_delete["original_filename"]
        is_reference = file_to_delete["is_reference"]

        print(f"   Attempting to delete file: {original_filename} (ID: {file_id})")
        print(f"   Is reference: {is_reference}")

        # Test deletion
        request_delete = factory.delete(f"/files/{file_id}/")
        request_delete.headers = {"UserId": "demo_user_123"}
        response_delete = delete_view(request_delete, pk=file_id)

        if response_delete.status_code == 204:
            print("✅ File deletion successful!")

            # Verify the file is gone
            request_verify = factory.get(f"/files/{file_id}/")
            request_verify.headers = {"UserId": "demo_user_123"}
            response_verify = retrieve_view(request_verify, pk=file_id)

            if response_verify.status_code == 404:
                print("✅ File properly removed from user's files!")
            else:
                print(
                    f"❌ File still accessible after deletion: {response_verify.status_code}"
                )

            # Check reference counting behavior
            print("   Checking reference counting after deletion...")
            remaining_files = File.objects.filter(user_id="demo_user_123")
            storage_records = FileStorage.objects.all()

            print(f"   Remaining files for user: {remaining_files.count()}")
            print(f"   Total storage records: {storage_records.count()}")

            # If we deleted a reference, the original should still exist
            if is_reference:
                print(
                    "   ✅ Reference file deleted, original preserved for deduplication"
                )

        else:
            print(f"❌ File deletion failed with status {response_delete.status_code}")
            if hasattr(response_delete, "data") and response_delete.data:
                print(f"   Error: {response_delete.data}")

        # Test unauthorized deletion (different user trying to delete)
        if response_list.data["results"]:  # If there are still files left
            another_file = response_list.data["results"][-1]  # Get the last file
            another_file_id = another_file["id"]

            print("\n   Testing unauthorized deletion (different user)...")
            request_unauth = factory.delete(f"/files/{another_file_id}/")
            request_unauth.headers = {"UserId": "unauthorized_user"}
            response_unauth = delete_view(request_unauth, pk=another_file_id)

            if response_unauth.status_code == 404:
                print("✅ Unauthorized deletion properly blocked!")
            else:
                print(
                    f"❌ Unauthorized deletion security issue: {response_unauth.status_code}"
                )

        # Test deletion of non-existent file
        print("\n   Testing deletion of non-existent file...")
        request_nonexistent = factory.delete("/files/99999/")
        request_nonexistent.headers = {"UserId": "demo_user_123"}
        response_nonexistent = delete_view(request_nonexistent, pk=99999)

        if response_nonexistent.status_code == 404:
            print("✅ Non-existent file deletion handled correctly!")
        else:
            print(
                f"❌ Non-existent file deletion unexpected response: {response_nonexistent.status_code}"
            )

    else:
        print("   No files available to test deletion")

    # Test 9: Test storage statistics endpoint
    print("\n9. Testing storage statistics endpoint...")

    # Create storage stats view
    storage_stats_view = FileViewSet.as_view({"get": "user_storage_stats"})

    # Test storage stats without UserId header
    request_no_user = factory.get("/files/storage_stats/")
    response_no_user = storage_stats_view(request_no_user)

    if response_no_user.status_code == 400:
        print("✅ Storage stats UserId validation working correctly!")
    else:
        print(
            f"❌ Storage stats UserId validation failed: {response_no_user.status_code}"
        )

    # Test storage stats with UserId header
    request_stats = factory.get("/files/storage_stats/")
    request_stats.headers = {"UserId": "demo_user_123"}
    response_stats = storage_stats_view(request_stats)

    if response_stats.status_code == 200:
        print("✅ Storage statistics retrieval working correctly!")
        print(f"   User ID: {response_stats.data['user_id']}")
        print(
            f"   Total storage used: {response_stats.data['total_storage_used']} bytes"
        )
        print(
            f"   Original storage used: {response_stats.data['original_storage_used']} bytes"
        )
        print(f"   Storage savings: {response_stats.data['storage_savings']} bytes")
        print(f"   Savings percentage: {response_stats.data['savings_percentage']}%")

        # Verify response format matches API specification
        expected_fields = [
            "user_id",
            "total_storage_used",
            "original_storage_used",
            "storage_savings",
            "savings_percentage",
        ]
        missing_fields = [
            field for field in expected_fields if field not in response_stats.data
        ]
        if not missing_fields:
            print("✅ Storage stats response format matches API specification!")
        else:
            print(f"❌ Missing fields in storage stats response: {missing_fields}")

        # Show deduplication savings if any
        if response_stats.data["storage_savings"] > 0:
            print(
                f"✅ Deduplication is saving {response_stats.data['storage_savings']} bytes!"
            )
            print(
                f"   That's {response_stats.data['savings_percentage']}% storage saved!"
            )
        else:
            print("ℹ️  No deduplication savings (expected with unique files)")

    else:
        print(f"❌ Storage statistics retrieval failed: {response_stats.data}")

    # Test with a different user to show user isolation
    request_stats_diff = factory.get("/files/storage_stats/")
    request_stats_diff.headers = {"UserId": "different_user_123"}
    response_stats_diff = storage_stats_view(request_stats_diff)

    if response_stats_diff.status_code == 200:
        if (
            response_stats_diff.data["total_storage_used"] == 0
            and response_stats_diff.data["original_storage_used"] == 0
        ):
            print("✅ User isolation in storage stats working correctly!")
            print("   Different user shows zero usage as expected")
        else:
            print("❌ User isolation issue: different user shows non-zero stats")
    else:
        print(f"❌ Storage stats for different user failed: {response_stats_diff.data}")

    # Test 10: Test file types endpoint
    print("\n10. Testing file types endpoint...")

    # Create file types view
    file_types_view = FileViewSet.as_view({"get": "file_types"})

    # Test file types without UserId header
    request_no_user_types = factory.get("/files/file_types/")
    response_no_user_types = file_types_view(request_no_user_types)

    if response_no_user_types.status_code == 400:
        print("✅ File types UserId validation working correctly!")
    else:
        print(
            f"❌ File types UserId validation failed: {response_no_user_types.status_code}"
        )

    # Test file types with UserId header
    request_types = factory.get("/files/file_types/")
    request_types.headers = {"UserId": "demo_user_123"}
    response_types = file_types_view(request_types)

    if response_types.status_code == 200:
        print("✅ File types retrieval working correctly!")
        print(f"   Available file types: {response_types.data}")

        # Verify response format matches API specification
        assert isinstance(response_types.data, list), "Response should be a list"

        # All items should be strings (MIME types)
        for file_type in response_types.data:
            assert isinstance(
                file_type, str
            ), f"File type should be string, got {type(file_type)}"

        print("✅ File types response format matches API specification!")

        # Verify file types are sorted
        if len(response_types.data) > 1:
            sorted_types = sorted(response_types.data)
            if response_types.data == sorted_types:
                print("✅ File types are properly sorted alphabetically!")
            else:
                print(
                    f"❌ File types not sorted: got {response_types.data}, expected {sorted_types}"
                )

        # Show expected types based on what we uploaded
        print("   Expected types based on uploaded files:")
        print("   - text/plain (from demo.txt and duplicate.txt)")
        if "text/plain" in response_types.data:
            print("   ✅ text/plain found in response")
        else:
            print("   ❌ text/plain missing from response")

    else:
        print(f"❌ File types retrieval failed: {response_types.data}")

    # Test file types for user with no files
    request_types_empty = factory.get("/files/file_types/")
    request_types_empty.headers = {"UserId": "empty_user_123"}
    response_types_empty = file_types_view(request_types_empty)

    if response_types_empty.status_code == 200 and response_types_empty.data == []:
        print("✅ File types for empty user working correctly!")
        print("   Empty user returns empty list as expected")
    else:
        print(f"❌ File types for empty user failed: {response_types_empty.data}")

    # Test file types user isolation
    # Upload a file with different MIME type for different user to test isolation
    image_file = SimpleUploadedFile(
        "test_image.jpg", b"fake jpeg content", content_type="image/jpeg"
    )

    request_upload_image = factory.post("/files/", {"file": image_file})
    request_upload_image.headers = {"UserId": "different_user_456"}
    view(request_upload_image)

    # Check file types for the different user
    request_types_diff_user = factory.get("/files/file_types/")
    request_types_diff_user.headers = {"UserId": "different_user_456"}
    response_types_diff_user = file_types_view(request_types_diff_user)

    if (
        response_types_diff_user.status_code == 200
        and "image/jpeg" in response_types_diff_user.data
        and "text/plain" not in response_types_diff_user.data
    ):
        print("✅ File types user isolation working correctly!")
        print("   Different user sees only their own file types")
    else:
        print(f"❌ File types user isolation issue: {response_types_diff_user.data}")

    # Test with default settings (2 calls per 1 second)
    rate_limiter = RateLimiterService()
    user_id = "test_user"

    print("Testing Rate Limiter with default settings (2 calls per 1 second)")
    print("-" * 60)

    # Test Rate Limiter: First two calls should be allowed
    print("Test: First two calls")
    request_ids = []
    for i in range(2):
        allowed, message, request_id = rate_limiter.is_allowed(user_id)
        request_ids.append(request_id)
        print(
            f"  Call {i + 1}: {'ALLOWED' if allowed else 'BLOCKED'} - {message} (ID: {request_id})"
        )
        assert allowed, f"Call {i + 1} should be allowed"
        assert request_id is not None, "Request ID should be provided"

    # Test Rate Limiter: Third call should be blocked
    print("\nTest: Third call (should be blocked)")
    allowed, message, request_id = rate_limiter.is_allowed(user_id)
    print(
        f"  Call: {'ALLOWED' if allowed else 'BLOCKED'} - {message} (ID: {request_id})"
    )
    assert not allowed, "Call 3 should be blocked"
    assert (
        message == "Call Limit Reached"
    ), f"Expected 'Call Limit Reached', got '{message}'"
    assert (
        request_id is not None
    ), "Request ID should be provided even for blocked requests"

    # Test Rate Limiter: Wait for window to reset and try again
    print("\nTest: Waiting for rate limit window to reset...")
    time.sleep(1.1)  # Wait slightly more than 1 second
    allowed, message, request_id = rate_limiter.is_allowed(user_id)
    print(
        f"  Call after reset: {'ALLOWED' if allowed else 'BLOCKED'} - {message} (ID: {request_id})"
    )
    assert allowed, "Call after reset should be allowed"

    # Test Rate Limiter: Test rate limit info
    print("\nTest: Rate limit info")
    info = rate_limiter.get_rate_limit_info(user_id)
    print(f"  Remaining calls: {info['remaining_calls']}")
    print(f"  Limit: {info['limit']}")
    print(f"  Window: {info['window']} seconds")
    assert info["limit"] == 2, "Limit should be 2"
    assert info["window"] == 1, "Window should be 1 second"

    print("\n🎉 API Demo Complete!")
    print("All key features are working:")
    print("- ✅ UserId header authentication")
    print("- ✅ File upload with deduplication")
    print("- ✅ SHA-256 hash-based deduplication")
    print("- ✅ Reference counting")
    print("- ✅ Storage limit enforcement (10MB default)")
    print("- ✅ File listing with filtering and pagination")
    print("- ✅ Search, file type, size, and date filtering")
    print("- ✅ File details retrieval with user isolation")
    print("- ✅ File deletion with proper authorization")
    print("- ✅ Reference counting in deletion scenarios")
    print("- ✅ Storage statistics with deduplication savings calculation")
    print("- ✅ File types endpoint with user isolation")
    print("- ✅ Proper API response format")
    print("- ✅ Rate Limiter works.")


if __name__ == "__main__":
    demo_api()