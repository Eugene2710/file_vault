import pytest
from files.models import File


class TestFileHashingIntegration:
    """Integration tests for File model hashing functionality."""

    def test_calculate_file_hash_returns_correct_type_and_format(self):
        """
        Test that hash calculation returns correct type and format.

        Validates:
        - Return type is string
        - Hash length is exactly 64 characters (SHA-256 hex format)
        - Hash contains only valid hexadecimal characters
        """
        test_content = b"Hello, World!"

        result = File.calculate_file_hash(test_content)

        # Assert return type is string
        assert isinstance(result, str), f"Expected str, got {type(result)}"

        # Assert SHA-256 hex string length (64 characters)
        assert len(result) == 64, f"Expected 64 characters, got {len(result)}"

        # Assert only valid hexadecimal characters (0-9, a-f)
        assert all(c in '0123456789abcdef' for c in result), \
            f"Hash contains invalid hex characters: {result}"

    def test_calculate_file_hash_known_content_produces_expected_hash(self):
        """
        Test that known content produces the expected SHA-256 hash.

        Uses a known test vector to verify hash calculation correctness.
        """
        test_content = b"Hello, World!"
        expected_hash = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"

        actual_hash = File.calculate_file_hash(test_content)

        assert actual_hash == expected_hash, \
            f"Expected {expected_hash}, got {actual_hash}"

    def test_calculate_file_hash_different_content_produces_different_hashes(self):
        """
        Test that different file content produces different hashes.

        Validates that the hash function properly differentiates content.
        """
        content_1 = b"First file content"
        content_2 = b"Second file content"
        content_3 = b"First file content"  # Same as content_1

        hash_1 = File.calculate_file_hash(content_1)
        hash_2 = File.calculate_file_hash(content_2)
        hash_3 = File.calculate_file_hash(content_3)

        # Different content should produce different hashes
        assert hash_1 != hash_2, \
            f"Different content produced same hash: {hash_1}"

        # Same content should produce same hash (deterministic)
        assert hash_1 == hash_3, \
            f"Same content produced different hashes: {hash_1} vs {hash_3}"

    def test_calculate_file_hash_empty_file_produces_valid_hash(self):
        """
        Test that empty file content produces a valid hash.

        Edge case: Ensures empty files can be hashed properly.
        """
        empty_content = b""

        result = File.calculate_file_hash(empty_content)

        # Should still return valid 64-character hex string
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in '0123456789abcdef' for c in result)

        # Empty string SHA-256 hash (known value)
        expected_empty_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert result == expected_empty_hash

    def test_calculate_file_hash_large_content_produces_valid_hash(self):
        """
        Test that large file content produces a valid hash.

        Edge case: Ensures method works with larger content sizes.
        """
        # Create 1MB of test data
        large_content = b"A" * (1024 * 1024)

        result = File.calculate_file_hash(large_content)

        # Should still return valid format regardless of input size
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in '0123456789abcdef' for c in result)
