"""
Unit tests for metadata extraction functions.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from src.forensix.metadata import extract_file_metadata, extract_video_metadata


class TestExtractFileMetadata:
    """Test suite for extract_file_metadata function"""
    
    def test_extract_basic_metadata_jpg(self, tmp_path):
        """Test extraction of basic metadata from a JPG file"""
        # Create a temporary file
        test_file = tmp_path / "test_image.jpg"
        test_file.write_bytes(b"fake image content")
        
        # Mock UploadFile
        mock_file = Mock()
        mock_file.filename = "test_image.jpg"
        
        # Extract metadata
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        # Assertions
        assert metadata["original_filename"] == "test_image.jpg"
        assert metadata["file_size"] == 18  # Length of "fake image content"
        assert metadata["mime_type"] == "image/jpeg"
        assert metadata["file_extension"] == "jpg"
    
    def test_extract_metadata_png(self, tmp_path):
        """Test extraction from PNG file"""
        test_file = tmp_path / "screenshot.png"
        test_file.write_bytes(b"fake png data")
        
        mock_file = Mock()
        mock_file.filename = "screenshot.png"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["original_filename"] == "screenshot.png"
        assert metadata["file_size"] == 13
        assert metadata["mime_type"] == "image/png"
        assert metadata["file_extension"] == "png"
    
    def test_extract_metadata_mp4(self, tmp_path):
        """Test extraction from MP4 video file"""
        test_file = tmp_path / "evidence.mp4"
        test_file.write_bytes(b"fake video content here")
        
        mock_file = Mock()
        mock_file.filename = "evidence.mp4"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["original_filename"] == "evidence.mp4"
        assert metadata["file_size"] == 23
        assert metadata["mime_type"] == "video/mp4"
        assert metadata["file_extension"] == "mp4"
    
    def test_extract_metadata_txt(self, tmp_path):
        """Test extraction from text file"""
        test_file = tmp_path / "log.txt"
        test_file.write_bytes(b"log entry 1\nlog entry 2")
        
        mock_file = Mock()
        mock_file.filename = "log.txt"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["original_filename"] == "log.txt"
        assert metadata["file_size"] == 23
        assert metadata["mime_type"] == "text/plain"
        assert metadata["file_extension"] == "txt"
    
    def test_extract_metadata_csv(self, tmp_path):
        """Test extraction from CSV file"""
        test_file = tmp_path / "data.csv"
        test_content = b"name,age\nJohn,30\n"
        test_file.write_bytes(test_content)
        
        mock_file = Mock()
        mock_file.filename = "data.csv"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["original_filename"] == "data.csv"
        assert metadata["file_size"] == len(test_content)  # 17 bytes
        assert metadata["mime_type"] == "text/csv"
        assert metadata["file_extension"] == "csv"
    
    def test_uppercase_extension_normalized_to_lowercase(self, tmp_path):
        """Test that uppercase extensions are normalized to lowercase"""
        test_file = tmp_path / "IMAGE.JPG"
        test_file.write_bytes(b"content")
        
        mock_file = Mock()
        mock_file.filename = "IMAGE.JPG"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["file_extension"] == "jpg"  # Should be lowercase
        assert metadata["mime_type"] == "image/jpeg"
    
    def test_extension_without_dot(self, tmp_path):
        """Test that extension is returned without the dot"""
        test_file = tmp_path / "file.json"
        test_file.write_bytes(b"{}")
        
        mock_file = Mock()
        mock_file.filename = "file.json"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["file_extension"] == "json"
        assert not metadata["file_extension"].startswith(".")
    
    def test_no_extension(self, tmp_path):
        """Test file with no extension"""
        test_file = tmp_path / "noextension"
        test_file.write_bytes(b"data")
        
        mock_file = Mock()
        mock_file.filename = "noextension"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["file_extension"] == ""
        assert metadata["mime_type"] == "application/octet-stream"  # Default for unknown
    
    def test_unknown_extension(self, tmp_path):
        """Test file with unknown extension defaults to application/octet-stream"""
        test_file = tmp_path / "file.xyz"
        test_file.write_bytes(b"unknown data")
        
        mock_file = Mock()
        mock_file.filename = "file.xyz"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["file_extension"] == "xyz"
        assert metadata["mime_type"] == "application/octet-stream"
    
    def test_zero_byte_file(self, tmp_path):
        """Test extraction from zero-byte file"""
        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")
        
        mock_file = Mock()
        mock_file.filename = "empty.txt"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["file_size"] == 0
        assert metadata["original_filename"] == "empty.txt"
        assert metadata["file_extension"] == "txt"
    
    def test_no_filename(self, tmp_path):
        """Test when uploaded file has no filename"""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"content")
        
        mock_file = Mock()
        mock_file.filename = None
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["original_filename"] == "unknown"
    
    def test_file_size_accuracy(self, tmp_path):
        """Test that file size is accurately measured in bytes"""
        test_content = b"x" * 1024  # 1KB
        test_file = tmp_path / "sizefile.bin"
        test_file.write_bytes(test_content)
        
        mock_file = Mock()
        mock_file.filename = "sizefile.bin"
        
        metadata = extract_file_metadata(mock_file, str(test_file))
        
        assert metadata["file_size"] == 1024
    
    def test_all_supported_image_extensions(self, tmp_path):
        """Test all supported image extensions"""
        extensions = ["jpg", "jpeg", "png", "gif", "bmp"]
        expected_mimes = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "bmp": "image/bmp"
        }
        
        for ext in extensions:
            test_file = tmp_path / f"test.{ext}"
            test_file.write_bytes(b"fake")
            
            mock_file = Mock()
            mock_file.filename = f"test.{ext}"
            
            metadata = extract_file_metadata(mock_file, str(test_file))
            
            assert metadata["file_extension"] == ext
            assert metadata["mime_type"] == expected_mimes[ext]
    
    def test_all_supported_video_extensions(self, tmp_path):
        """Test all supported video extensions"""
        extensions = ["mp4", "mov", "avi"]
        expected_mimes = {
            "mp4": "video/mp4",
            "mov": "video/quicktime",
            "avi": "video/x-msvideo"
        }
        
        for ext in extensions:
            test_file = tmp_path / f"video.{ext}"
            test_file.write_bytes(b"fake")
            
            mock_file = Mock()
            mock_file.filename = f"video.{ext}"
            
            metadata = extract_file_metadata(mock_file, str(test_file))
            
            assert metadata["file_extension"] == ext
            assert metadata["mime_type"] == expected_mimes[ext]
    
    def test_all_supported_text_extensions(self, tmp_path):
        """Test all supported text/data extensions"""
        extensions_mimes = {
            "txt": "text/plain",
            "log": "text/plain",
            "json": "application/json",
            "csv": "text/csv"
        }
        
        for ext, expected_mime in extensions_mimes.items():
            test_file = tmp_path / f"file.{ext}"
            test_file.write_bytes(b"data")
            
            mock_file = Mock()
            mock_file.filename = f"file.{ext}"
            
            metadata = extract_file_metadata(mock_file, str(test_file))
            
            assert metadata["file_extension"] == ext
            assert metadata["mime_type"] == expected_mime


class TestExtractVideoMetadata:
    """Test suite for extract_video_metadata function"""
    
    def test_unsupported_extension_returns_empty_dict(self, tmp_path):
        """Test that unsupported file extensions return empty dict"""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"not a video")
        
        result = extract_video_metadata(str(test_file))
        
        assert result == {}
    
    def test_image_extension_returns_empty_dict(self, tmp_path):
        """Test that image extensions return empty dict"""
        test_file = tmp_path / "image.jpg"
        test_file.write_bytes(b"fake image")
        
        result = extract_video_metadata(str(test_file))
        
        assert result == {}
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_extract_complete_video_metadata(self, mock_probe, tmp_path):
        """Test extraction of complete video metadata with all fields"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake video")
        
        # Mock ffmpeg.probe response with complete metadata
        mock_probe.return_value = {
            'format': {
                'duration': '120.5',
                'tags': {
                    'creation_time': '2024-01-15T10:30:00.000000Z'
                }
            },
            'streams': [
                {
                    'codec_type': 'video',
                    'codec_name': 'h264',
                    'width': 1920,
                    'height': 1080
                }
            ]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] == 120.5
        assert result['width'] == 1920
        assert result['height'] == 1080
        assert result['codec'] == 'h264'
        assert result['creation_timestamp'] == '2024-01-15T10:30:00.000000Z'
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_extract_video_mp4_extension(self, mock_probe, tmp_path):
        """Test extraction from mp4 file"""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {'duration': '10.0'},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 640, 'height': 480}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] == 10.0
        assert result['codec'] == 'h264'
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_extract_video_mov_extension(self, mock_probe, tmp_path):
        """Test extraction from mov file"""
        test_file = tmp_path / "test.mov"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {'duration': '15.5'},
            'streams': [{'codec_type': 'video', 'codec_name': 'mpeg4', 'width': 1280, 'height': 720}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] == 15.5
        assert result['codec'] == 'mpeg4'
        assert result['width'] == 1280
        assert result['height'] == 720
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_extract_video_avi_extension(self, mock_probe, tmp_path):
        """Test extraction from avi file"""
        test_file = tmp_path / "test.avi"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {},
            'streams': [{'codec_type': 'video', 'codec_name': 'xvid', 'width': 800, 'height': 600, 'duration': '5.2'}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] == 5.2
        assert result['codec'] == 'xvid'
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_missing_duration_field(self, mock_probe, tmp_path):
        """Test when duration is missing"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 640, 'height': 480}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] is None
        assert result['codec'] == 'h264'
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_missing_resolution_fields(self, mock_probe, tmp_path):
        """Test when width/height are missing"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {'duration': '10.0'},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264'}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['width'] is None
        assert result['height'] is None
        assert result['codec'] == 'h264'
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_missing_codec_field(self, mock_probe, tmp_path):
        """Test when codec is missing"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {'duration': '10.0'},
            'streams': [{'codec_type': 'video', 'width': 640, 'height': 480}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['codec'] is None
        assert result['width'] == 640
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_missing_creation_timestamp(self, mock_probe, tmp_path):
        """Test when creation timestamp is missing"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {'duration': '10.0'},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 640, 'height': 480}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['creation_timestamp'] is None
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_creation_timestamp_in_stream_tags(self, mock_probe, tmp_path):
        """Test extraction of creation timestamp from stream tags"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {},
            'streams': [{
                'codec_type': 'video',
                'codec_name': 'h264',
                'width': 640,
                'height': 480,
                'tags': {
                    'creation_time': '2024-03-20T14:25:30.000000Z'
                }
            }]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['creation_timestamp'] == '2024-03-20T14:25:30.000000Z'
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_no_video_streams(self, mock_probe, tmp_path):
        """Test when file has no video streams"""
        test_file = tmp_path / "audio.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {'duration': '10.0'},
            'streams': [{'codec_type': 'audio', 'codec_name': 'aac'}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] == 10.0
        assert result['width'] is None
        assert result['height'] is None
        assert result['codec'] is None
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_multiple_video_streams_uses_first(self, mock_probe, tmp_path):
        """Test that first video stream is used when multiple exist"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {},
            'streams': [
                {'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080},
                {'codec_type': 'video', 'codec_name': 'h265', 'width': 640, 'height': 480}
            ]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['codec'] == 'h264'
        assert result['width'] == 1920
        assert result['height'] == 1080
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_ffmpeg_probe_exception_returns_empty_dict(self, mock_probe, tmp_path):
        """Test that ffmpeg.probe exceptions return empty dict (graceful degradation)"""
        test_file = tmp_path / "corrupt.mp4"
        test_file.write_bytes(b"corrupted")
        
        mock_probe.side_effect = Exception("FFmpeg probe failed")
        
        result = extract_video_metadata(str(test_file))
        
        assert result == {}
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_invalid_duration_type_handled(self, mock_probe, tmp_path):
        """Test that invalid duration types are handled gracefully"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {'duration': 'invalid'},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264'}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] is None
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_invalid_resolution_types_handled(self, mock_probe, tmp_path):
        """Test that invalid width/height types are handled gracefully"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 'abc', 'height': 'def'}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['width'] is None
        assert result['height'] is None
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_uppercase_extension_supported(self, mock_probe, tmp_path):
        """Test that uppercase MP4 extension is supported"""
        test_file = tmp_path / "VIDEO.MP4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 640, 'height': 480}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['codec'] == 'h264'
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_all_fields_none_when_missing(self, mock_probe, tmp_path):
        """Test that all optional fields default to None when missing"""
        test_file = tmp_path / "minimal.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {},
            'streams': [{'codec_type': 'video'}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] is None
        assert result['width'] is None
        assert result['height'] is None
        assert result['codec'] is None
        assert result['creation_timestamp'] is None
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_date_tag_alternative(self, mock_probe, tmp_path):
        """Test that 'date' tag is recognized as creation timestamp"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {'tags': {'date': '2024-06-10'}},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264'}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['creation_timestamp'] == '2024-06-10'
    
    @patch('src.forensix.metadata.ffmpeg.probe')
    def test_duration_from_stream_when_format_missing(self, mock_probe, tmp_path):
        """Test that duration is extracted from stream when format duration is missing"""
        test_file = tmp_path / "video.mp4"
        test_file.write_bytes(b"fake")
        
        mock_probe.return_value = {
            'format': {},
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'duration': '25.3'}]
        }
        
        result = extract_video_metadata(str(test_file))
        
        assert result['duration'] == 25.3
