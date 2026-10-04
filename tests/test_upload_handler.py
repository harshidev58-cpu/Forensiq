"""
Integration tests for the upload handler module.
Tests the complete upload workflow including validation, storage, hashing, and database operations.
"""

import json
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.forensix.upload_handler import upload_evidence_handler, UploadError
from src.forensix.config import DATABASE_PATH, EVIDENCE_STORAGE_DIR
from src.forensix.validation import validate_file_size, validate_file_extension, validate_required_params


class TestInputValidation:
    """Test input validation functions."""
    
    def test_validate_file_size_valid(self):
        """Test file size validation with valid sizes."""
        # Test normal file size
        validate_file_size(1024)  # 1KB - should pass
        validate_file_size(100 * 1024 * 1024)  # 100MB - should pass
        validate_file_size(500 * 1024 * 1024)  # 500MB - should pass (at limit)
    
    def test_validate_file_size_zero_bytes(self):
        """Test file size validation rejects 0 bytes."""
        with pytest.raises(ValueError, match="File size must be greater than 0 bytes"):
            validate_file_size(0)
    
    def test_validate_file_size_too_large(self):
        """Test file size validation rejects files >500MB."""
        with pytest.raises(ValueError, match="File size exceeds maximum limit of 500 MB"):
            validate_file_size(500 * 1024 * 1024 + 1)  # Just over 500MB
    
    def test_validate_file_extension_allowed(self):
        """Test file extension validation with allowed extensions."""
        # Test image extensions
        validate_file_extension("photo.jpg")
        validate_file_extension("image.jpeg")
        validate_file_extension("screenshot.png")
        validate_file_extension("animation.gif")
        validate_file_extension("bitmap.bmp")
        
        # Test video extensions
        validate_file_extension("video.mp4")
        validate_file_extension("movie.mov")
        validate_file_extension("clip.avi")
        
        # Test text/data extensions
        validate_file_extension("document.txt")
        validate_file_extension("system.log")
        validate_file_extension("data.json")
        validate_file_extension("export.csv")
    
    def test_validate_file_extension_case_insensitive(self):
        """Test file extension validation is case insensitive."""
        validate_file_extension("photo.JPG")
        validate_file_extension("Video.MP4")
        validate_file_extension("Document.TXT")
    
    def test_validate_file_extension_disallowed(self):
        """Test file extension validation rejects disallowed extensions."""
        with pytest.raises(ValueError, match="Unsupported file format"):
            validate_file_extension("malware.exe")
        
        with pytest.raises(ValueError, match="Supported formats"):
            validate_file_extension("document.pdf")
        
        with pytest.raises(ValueError, match="Supported formats"):
            validate_file_extension("archive.zip")
    
    def test_validate_file_extension_no_extension(self):
        """Test file extension validation with files without extensions."""
        with pytest.raises(ValueError, match="Invalid filename format"):
            validate_file_extension("filename_no_extension")
        
        with pytest.raises(ValueError, match="Invalid filename format"):
            validate_file_extension("")
    
    def test_validate_required_params_valid(self):
        """Test required parameter validation with valid inputs."""
        validate_required_params("investigator_001", "Mobile device extraction")
        validate_required_params("user123", "Network capture")
    
    def test_validate_required_params_missing_uploader_id(self):
        """Test required parameter validation with missing uploader_id."""
        with pytest.raises(ValueError, match="Uploader_ID and Collection_Method are required"):
            validate_required_params("", "Valid collection method")
        
        with pytest.raises(ValueError, match="Uploader_ID and Collection_Method are required"):
            validate_required_params("   ", "Valid collection method")  # Whitespace only
    
    def test_validate_required_params_missing_collection_method(self):
        """Test required parameter validation with missing collection_method."""
        with pytest.raises(ValueError, match="Uploader_ID and Collection_Method are required"):
            validate_required_params("valid_user", "")
        
        with pytest.raises(ValueError, match="Uploader_ID and Collection_Method are required"):
            validate_required_params("valid_user", "   ")  # Whitespace only
    
    def test_validate_required_params_both_missing(self):
        """Test required parameter validation with both parameters missing."""
        with pytest.raises(ValueError, match="Uploader_ID and Collection_Method are required"):
            validate_required_params("", "")


class TestUploadHandler:
    """Integration tests for the upload handler function."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        # Ensure test database and storage directory exist
        self._ensure_test_database()
        EVIDENCE_STORAGE_DIR.mkdir(exist_ok=True)
    
    def _ensure_test_database(self):
        """Ensure test database exists and is initialized."""
        if not DATABASE_PATH.exists():
            # Import and run database setup
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from database_setup import create_database
            create_database()
    
    def _create_mock_file(self, filename: str, content: bytes) -> Mock:
        """Create a mock UploadFile object."""
        mock_file = Mock()
        mock_file.filename = filename
        mock_file.file = Mock()
        mock_file.file.read.return_value = content
        mock_file.file.seek = Mock()
        return mock_file
    
    def test_upload_handler_successful_jpg(self):
        """Test successful upload of a JPG image file."""
        # Create test image content (minimal JPEG header)
        jpg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00' + b'\x00' * 100
        
        mock_file = self._create_mock_file("test_image.jpg", jpg_content)
        
        # Execute upload
        result = upload_evidence_handler(
            file=mock_file,
            uploader_id="investigator_001",
            collection_method="Digital camera extraction"
        )
        
        # Verify response structure
        assert "id" in result
        assert "sha256_hash" in result
        assert "upload_timestamp" in result
        assert "original_filename" in result
        assert "file_size" in result
        
        # Verify response values
        assert result["original_filename"] == "test_image.jpg"
        assert result["file_size"] == len(jpg_content)
        assert len(result["sha256_hash"]) == 64  # SHA-256 is 64 hex chars
        assert len(result["id"]) == 36  # UUID4 format
        
        # Verify file was stored
        evidence_id = result["id"]
        stored_file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.jpg"
        assert stored_file_path.exists()
        
        # Verify stored file content matches original
        with open(stored_file_path, 'rb') as f:
            stored_content = f.read()
        assert stored_content == jpg_content
        
        # Verify database record was created
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM evidence_records WHERE id = ?", (evidence_id,))
        record = cursor.fetchone()
        assert record is not None
        
        # Verify chain of custody entry was created
        cursor.execute("SELECT * FROM custody_entries WHERE evidence_id = ? AND action_type = 'UPLOAD'", (evidence_id,))
        custody_entry = cursor.fetchone()
        assert custody_entry is not None
        
        conn.close()
        
        # Cleanup
        stored_file_path.unlink()
    
    def test_upload_handler_successful_mp4(self):
        """Test successful upload of an MP4 video file."""
        # Create test MP4 content (minimal MP4 header)
        mp4_content = b'\x00\x00\x00\x20ftypmp41' + b'\x00' * 100
        
        mock_file = self._create_mock_file("test_video.mp4", mp4_content)
        
        # Execute upload
        result = upload_evidence_handler(
            file=mock_file,
            uploader_id="forensic_analyst",
            collection_method="Security camera download"
        )
        
        # Verify response
        assert result["original_filename"] == "test_video.mp4"
        assert result["file_size"] == len(mp4_content)
        
        # Verify file extension in storage
        evidence_id = result["id"]
        stored_file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.mp4"
        assert stored_file_path.exists()
        
        # Cleanup
        stored_file_path.unlink()
    
    def test_upload_handler_successful_txt(self):
        """Test successful upload of a text file."""
        txt_content = b"This is evidence from a log file.\nTimestamp: 2024-01-01 10:00:00\nUser action: login"
        
        mock_file = self._create_mock_file("system.log", txt_content)
        
        # Execute upload
        result = upload_evidence_handler(
            file=mock_file,
            uploader_id="sys_admin",
            collection_method="Server log extraction"
        )
        
        # Verify response
        assert result["original_filename"] == "system.log"
        assert result["file_size"] == len(txt_content)
        
        # Cleanup
        evidence_id = result["id"]
        stored_file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.log"
        stored_file_path.unlink()
    
    def test_upload_handler_zero_byte_file(self):
        """Test upload handler rejects zero-byte files."""
        mock_file = self._create_mock_file("empty.jpg", b"")
        
        with pytest.raises(ValueError, match="File size must be greater than 0 bytes"):
            upload_evidence_handler(
                file=mock_file,
                uploader_id="investigator_001",
                collection_method="Test upload"
            )
    
    def test_upload_handler_oversized_file(self):
        """Test upload handler rejects files over 500MB."""
        # Create content larger than 500MB
        large_content = b"x" * (500 * 1024 * 1024 + 1)
        mock_file = self._create_mock_file("large.jpg", large_content)
        
        with pytest.raises(ValueError, match="File size exceeds maximum limit of 500 MB"):
            upload_evidence_handler(
                file=mock_file,
                uploader_id="investigator_001",
                collection_method="Test upload"
            )
    
    def test_upload_handler_unsupported_extension(self):
        """Test upload handler rejects unsupported file extensions."""
        mock_file = self._create_mock_file("malware.exe", b"fake executable content")
        
        with pytest.raises(ValueError, match="Unsupported file format"):
            upload_evidence_handler(
                file=mock_file,
                uploader_id="investigator_001",
                collection_method="Test upload"
            )
    
    def test_upload_handler_missing_uploader_id(self):
        """Test upload handler rejects missing uploader_id."""
        mock_file = self._create_mock_file("test.jpg", b"fake image content")
        
        with pytest.raises(ValueError, match="Uploader_ID and Collection_Method are required"):
            upload_evidence_handler(
                file=mock_file,
                uploader_id="",
                collection_method="Valid collection method"
            )
    
    def test_upload_handler_missing_collection_method(self):
        """Test upload handler rejects missing collection_method."""
        mock_file = self._create_mock_file("test.jpg", b"fake image content")
        
        with pytest.raises(ValueError, match="Uploader_ID and Collection_Method are required"):
            upload_evidence_handler(
                file=mock_file,
                uploader_id="valid_user",
                collection_method=""
            )
    
    def test_upload_handler_unique_identifiers(self):
        """Test that upload handler generates unique identifiers for each upload."""
        jpg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 50
        
        # Upload same file twice
        mock_file1 = self._create_mock_file("duplicate.jpg", jpg_content)
        mock_file2 = self._create_mock_file("duplicate.jpg", jpg_content)
        
        result1 = upload_evidence_handler(
            file=mock_file1,
            uploader_id="user1",
            collection_method="First upload"
        )
        
        result2 = upload_evidence_handler(
            file=mock_file2,
            uploader_id="user2", 
            collection_method="Second upload"
        )
        
        # Verify different UUIDs despite identical content
        assert result1["id"] != result2["id"]
        
        # Both files should have same hash but different IDs
        assert result1["sha256_hash"] == result2["sha256_hash"]
        
        # Cleanup
        Path(EVIDENCE_STORAGE_DIR / f"{result1['id']}.jpg").unlink()
        Path(EVIDENCE_STORAGE_DIR / f"{result2['id']}.jpg").unlink()
    
    def test_upload_handler_response_completeness(self):
        """Test that upload handler response contains all required fields."""
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        mock_file = self._create_mock_file("complete_test.jpg", jpg_content)
        
        result = upload_evidence_handler(
            file=mock_file,
            uploader_id="investigator_123",
            collection_method="Completeness test"
        )
        
        # Verify all required fields are present
        required_fields = ["id", "sha256_hash", "upload_timestamp", "original_filename", "file_size"]
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"
        
        # Verify field types and formats
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 36  # UUID4 format
        assert isinstance(result["sha256_hash"], str)
        assert len(result["sha256_hash"]) == 64  # SHA-256 hex length
        assert isinstance(result["upload_timestamp"], str)
        assert "T" in result["upload_timestamp"]  # ISO 8601 format
        assert isinstance(result["original_filename"], str)
        assert isinstance(result["file_size"], int)
        
        # Cleanup
        Path(EVIDENCE_STORAGE_DIR / f"{result['id']}.jpg").unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])