"""
Unit tests for file system metadata extraction.

Tests the extract_file_metadata function to ensure it correctly captures:
- Original filename
- File size in bytes
- MIME type
- File extension
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock
from src.metadata_extractor import extract_file_metadata


class TestExtractFileMetadata:
    """Test suite for extract_file_metadata function."""
    
    def test_extract_basic_file_metadata(self):
        """Test extraction of basic file metadata with a real file."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            tmp.write("Test content for metadata extraction")
            tmp_path = tmp.name
        
        try:
            # Create a mock UploadFile object
            mock_file = Mock()
            mock_file.filename = "test_document.txt"
            mock_file.content_type = "text/plain"
            
            # Extract metadata
            metadata = extract_file_metadata(mock_file, tmp_path)
            
            # Verify all required fields are present
            assert "original_filename" in metadata
            assert "file_size" in metadata
            assert "mime_type" in metadata
            assert "file_extension" in metadata
            
            # Verify values
            assert metadata["original_filename"] == "test_document.txt"
            assert metadata["file_size"] > 0  # Should have content
            assert metadata["mime_type"] == "text/plain"
            assert metadata["file_extension"] == "txt"
        
        finally:
            # Cleanup
            Path(tmp_path).unlink(missing_ok=True)
    
    def test_extract_image_file_metadata(self):
        """Test extraction from an image file."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.jpg', delete=False) as tmp:
            # Write some dummy binary data
            tmp.write(b'\xFF\xD8\xFF\xE0' + b'\x00' * 100)  # JPEG magic bytes + padding
            tmp_path = tmp.name
        
        try:
            mock_file = Mock()
            mock_file.filename = "photo.jpg"
            mock_file.content_type = "image/jpeg"
            
            metadata = extract_file_metadata(mock_file, tmp_path)
            
            assert metadata["original_filename"] == "photo.jpg"
            assert metadata["file_size"] == 104  # Magic bytes + padding
            assert metadata["mime_type"] == "image/jpeg"
            assert metadata["file_extension"] == "jpg"
        
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    
    def test_extract_video_file_metadata(self):
        """Test extraction from a video file."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.mp4', delete=False) as tmp:
            tmp.write(b'\x00' * 1024)  # 1KB of data
            tmp_path = tmp.name
        
        try:
            mock_file = Mock()
            mock_file.filename = "evidence_video.mp4"
            mock_file.content_type = "video/mp4"
            
            metadata = extract_file_metadata(mock_file, tmp_path)
            
            assert metadata["original_filename"] == "evidence_video.mp4"
            assert metadata["file_size"] == 1024
            assert metadata["mime_type"] == "video/mp4"
            assert metadata["file_extension"] == "mp4"
        
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    
    def test_mime_type_fallback_to_guess(self):
        """Test MIME type guessing when content_type is not provided or is generic."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            tmp.write('{"key": "value"}')
            tmp_path = tmp.name
        
        try:
            # Test with no content_type
            mock_file = Mock()
            mock_file.filename = "data.json"
            mock_file.content_type = None
            
            metadata = extract_file_metadata(mock_file, tmp_path)
            
            # Should guess application/json from filename
            assert metadata["mime_type"] in ["application/json", "application/octet-stream"]
            assert metadata["file_extension"] == "json"
            
            # Test with generic content_type
            mock_file.content_type = "application/octet-stream"
            metadata = extract_file_metadata(mock_file, tmp_path)
            
            # Should attempt to guess from filename
            assert metadata["mime_type"] in ["application/json", "application/octet-stream"]
        
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    
    def test_file_extension_extraction(self):
        """Test extraction of various file extensions."""
        test_cases = [
            ("document.pdf", "pdf"),
            ("image.PNG", "png"),  # Should be lowercase
            ("video.MOV", "mov"),
            ("data.CSV", "csv"),
            ("noextension", ""),  # No extension
        ]
        
        for filename, expected_ext in test_cases:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
                tmp.write("test")
                tmp_path = tmp.name
            
            try:
                mock_file = Mock()
                mock_file.filename = filename
                mock_file.content_type = "application/octet-stream"
                
                metadata = extract_file_metadata(mock_file, tmp_path)
                
                assert metadata["file_extension"] == expected_ext, \
                    f"Expected extension '{expected_ext}' for '{filename}', got '{metadata['file_extension']}'"
            
            finally:
                Path(tmp_path).unlink(missing_ok=True)
    
    def test_file_size_accuracy(self):
        """Test accurate file size reporting for different file sizes."""
        test_sizes = [0, 1, 100, 1024, 1024 * 1024]  # 0B, 1B, 100B, 1KB, 1MB
        
        for size in test_sizes:
            with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp:
                tmp.write(b'\x00' * size)
                tmp_path = tmp.name
            
            try:
                mock_file = Mock()
                mock_file.filename = f"file_{size}bytes.bin"
                mock_file.content_type = "application/octet-stream"
                
                metadata = extract_file_metadata(mock_file, tmp_path)
                
                assert metadata["file_size"] == size, \
                    f"Expected size {size}, got {metadata['file_size']}"
            
            finally:
                Path(tmp_path).unlink(missing_ok=True)
    
    def test_missing_filename_handling(self):
        """Test handling when filename is None or empty."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp.write("test")
            tmp_path = tmp.name
        
        try:
            # Test with None filename
            mock_file = Mock()
            mock_file.filename = None
            mock_file.content_type = "text/plain"
            
            metadata = extract_file_metadata(mock_file, tmp_path)
            
            assert metadata["original_filename"] == "unknown"
            assert metadata["file_extension"] == ""
        
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    
    def test_special_characters_in_filename(self):
        """Test handling of special characters in filenames."""
        special_filenames = [
            "file with spaces.txt",
            "file_with_underscores.jpg",
            "file-with-dashes.png",
            "файл.txt",  # Cyrillic
            "文件.pdf",  # Chinese
        ]
        
        for filename in special_filenames:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
                tmp.write("test")
                tmp_path = tmp.name
            
            try:
                mock_file = Mock()
                mock_file.filename = filename
                mock_file.content_type = "application/octet-stream"
                
                metadata = extract_file_metadata(mock_file, tmp_path)
                
                assert metadata["original_filename"] == filename
                # Should still extract extension correctly
                expected_ext = Path(filename).suffix.lower().lstrip('.')
                assert metadata["file_extension"] == expected_ext
            
            finally:
                Path(tmp_path).unlink(missing_ok=True)
    
    def test_multiple_dots_in_filename(self):
        """Test handling of filenames with multiple dots."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp.write("test")
            tmp_path = tmp.name
        
        try:
            mock_file = Mock()
            mock_file.filename = "my.file.with.dots.txt"
            mock_file.content_type = "text/plain"
            
            metadata = extract_file_metadata(mock_file, tmp_path)
            
            assert metadata["original_filename"] == "my.file.with.dots.txt"
            # Should extract only the last extension
            assert metadata["file_extension"] == "txt"
        
        finally:
            Path(tmp_path).unlink(missing_ok=True)
