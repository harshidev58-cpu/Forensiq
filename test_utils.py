"""
Unit tests for core utility functions.

This module tests:
- SHA-256 hash computation accuracy
- Hash idempotence property
- Timeout handling
- I/O error handling
"""

import pytest
import tempfile
import time
from pathlib import Path
from utils import compute_sha256_hash, HashTimeoutError, HashIOError


class TestHashComputation:
    """Test suite for compute_sha256_hash function."""
    
    def test_hash_accuracy_with_known_vector(self):
        """
        Test hash computation accuracy using known test vector.
        
        Requirements: 2.1, 2.3
        """
        # Known test vector: empty string has known SHA-256 hash
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
            f.write(b"")
            temp_path = f.name
        
        try:
            result = compute_sha256_hash(temp_path)
            # SHA-256 of empty string
            expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            assert result == expected, f"Expected {expected}, got {result}"
        finally:
            Path(temp_path).unlink()
    
    def test_hash_accuracy_with_simple_content(self):
        """
        Test hash computation with simple text content.
        
        Requirements: 2.1, 2.3
        """
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
            f.write(b"Hello, World!")
            temp_path = f.name
        
        try:
            result = compute_sha256_hash(temp_path)
            # SHA-256 of "Hello, World!"
            expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
            assert result == expected, f"Expected {expected}, got {result}"
        finally:
            Path(temp_path).unlink()
    
    def test_hash_idempotence(self):
        """
        Test that computing hash twice on same file produces identical results.
        
        Requirements: 2.4
        """
        # Create a test file with some content
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
            f.write(b"Test content for idempotence validation")
            temp_path = f.name
        
        try:
            # Compute hash twice
            hash1 = compute_sha256_hash(temp_path)
            hash2 = compute_sha256_hash(temp_path)
            
            # Hashes must be identical
            assert hash1 == hash2, f"Hash not idempotent: {hash1} != {hash2}"
            
            # Both should be 64-character hex strings
            assert len(hash1) == 64
            assert len(hash2) == 64
            assert all(c in '0123456789abcdef' for c in hash1)
            assert all(c in '0123456789abcdef' for c in hash2)
        finally:
            Path(temp_path).unlink()
    
    def test_hash_with_large_file(self):
        """
        Test hash computation with a larger file (streaming).
        
        Requirements: 2.1
        """
        # Create a 1MB file
        file_size = 1024 * 1024  # 1 MB
        
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
            # Write 1MB of repeated pattern
            pattern = b"A" * 1024  # 1KB pattern
            for _ in range(1024):  # Write 1024 times = 1MB
                f.write(pattern)
            temp_path = f.name
        
        try:
            # Should complete successfully with streaming
            result = compute_sha256_hash(temp_path)
            
            # Verify it's a valid hash
            assert len(result) == 64
            assert all(c in '0123456789abcdef' for c in result)
            
            # Verify idempotence on large file
            result2 = compute_sha256_hash(temp_path)
            assert result == result2
        finally:
            Path(temp_path).unlink()
    
    def test_timeout_handling(self):
        """
        Test that timeout is enforced during hash computation.
        
        Requirements: 2.6
        """
        # Create a reasonably sized file
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
            # Write 10MB of data
            pattern = b"X" * 1024  # 1KB pattern
            for _ in range(10240):  # 10MB
                f.write(pattern)
            temp_path = f.name
        
        try:
            # Set a very short timeout (should trigger timeout)
            with pytest.raises(HashTimeoutError) as exc_info:
                compute_sha256_hash(temp_path, timeout=0.001)  # 1ms timeout
            
            assert "timeout" in str(exc_info.value).lower()
        finally:
            Path(temp_path).unlink()
    
    def test_io_error_file_not_found(self):
        """
        Test that I/O errors are properly handled when file doesn't exist.
        
        Requirements: 2.7
        """
        non_existent_path = "/tmp/this_file_does_not_exist_12345.txt"
        
        with pytest.raises(HashIOError) as exc_info:
            compute_sha256_hash(non_existent_path)
        
        assert "File read error" in str(exc_info.value)
    
    def test_io_error_permission_denied(self):
        """
        Test that I/O errors are properly handled with permission issues.
        
        Requirements: 2.7
        """
        # Create a file and remove read permissions
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
            f.write(b"Test content")
            temp_path = f.name
        
        try:
            # Remove all permissions
            Path(temp_path).chmod(0o000)
            
            with pytest.raises(HashIOError) as exc_info:
                compute_sha256_hash(temp_path)
            
            assert "File read error" in str(exc_info.value)
        finally:
            # Restore permissions and delete
            try:
                Path(temp_path).chmod(0o644)
                Path(temp_path).unlink()
            except:
                pass
    
    def test_hash_returns_hexadecimal_string(self):
        """
        Test that hash is returned as a 64-character hexadecimal string.
        
        Requirements: 2.3
        """
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f:
            f.write(b"Sample content for hex test")
            temp_path = f.name
        
        try:
            result = compute_sha256_hash(temp_path)
            
            # Should be 64 characters (SHA-256 = 256 bits = 32 bytes = 64 hex chars)
            assert len(result) == 64
            
            # Should only contain hex characters (0-9, a-f)
            assert all(c in '0123456789abcdef' for c in result)
            
            # Should be lowercase hex
            assert result == result.lower()
        finally:
            Path(temp_path).unlink()
    
    def test_hash_different_files_different_hashes(self):
        """
        Test that different files produce different hashes.
        
        Requirements: 2.1
        """
        # Create two files with different content
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f1:
            f1.write(b"Content for file 1")
            path1 = f1.name
        
        with tempfile.NamedTemporaryFile(delete=False, mode='wb') as f2:
            f2.write(b"Content for file 2")
            path2 = f2.name
        
        try:
            hash1 = compute_sha256_hash(path1)
            hash2 = compute_sha256_hash(path2)
            
            # Different content should produce different hashes
            assert hash1 != hash2
        finally:
            Path(path1).unlink()
            Path(path2).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
