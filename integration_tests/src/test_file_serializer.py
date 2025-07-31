import pytest
from files.serializers import FileSerializer


class TestFileSerializerIntegration:
    """Integration tests for FileSerializer validation and field handling."""

    def test_serializer_includes_all_api_contract_fields(self):
      """Test that serializer includes all required API contract fields."""
      expected_fields = {
          'id', 'file', 'original_filename', 'file_type', 'size',
          'uploaded_at', 'user_id', 'file_hash', 'reference_count',
          'is_reference', 'original_file'
      }

      serializer = FileSerializer()
      actual_fields = set(serializer.fields.keys())

      assert actual_fields == expected_fields, \
          f"Missing fields: {expected_fields - actual_fields}"

    def test_file_type_validation_rejects_invalid_mime_types(self):
      """Test that invalid MIME types are rejected."""
      serializer = FileSerializer()

      with pytest.raises(Exception):  # ValidationError
          serializer.validate_file_type("invalid")

      with pytest.raises(Exception):
          serializer.validate_file_type("")

    def test_size_validation_enforces_10mb_limit(self):
      """Test that file size validation enforces 10MB limit."""
      serializer = FileSerializer()

      # Should pass: 5MB
      assert serializer.validate_size(5 * 1024 * 1024) == 5 * 1024 * 1024

      # Should fail: 15MB
      with pytest.raises(Exception):  # ValidationError
          serializer.validate_size(15 * 1024 * 1024)
