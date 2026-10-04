"""
Unit tests for EXIF metadata extraction.
"""

import pytest
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS
from src.forensix.metadata import extract_exif_metadata


class TestExtractExifMetadata:
    """Test suite for extract_exif_metadata function"""
    
    def test_extract_exif_from_non_image_file(self, tmp_path):
        """Test that non-image files return empty dict"""
        # Create a text file
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"not an image")
        
        result = extract_exif_metadata(str(test_file))
        
        assert result == {}
    
    def test_extract_exif_unsupported_extension(self, tmp_path):
        """Test that unsupported extensions return empty dict"""
        # Create a GIF file (not in jpg, jpeg, png)
        test_file = tmp_path / "test.gif"
        test_file.write_bytes(b"GIF89a")
        
        result = extract_exif_metadata(str(test_file))
        
        assert result == {}
    
    def test_extract_exif_from_image_without_exif(self, tmp_path):
        """Test extraction from image without EXIF data returns empty dict"""
        # Create a simple PNG without EXIF data
        test_file = tmp_path / "test.png"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(test_file)
        
        result = extract_exif_metadata(str(test_file))
        
        assert result == {}
    
    def test_extract_exif_corrupted_file(self, tmp_path):
        """Test that corrupted image files return empty dict (graceful degradation)"""
        # Create a file with jpg extension but invalid content
        test_file = tmp_path / "corrupted.jpg"
        test_file.write_bytes(b"not a valid jpeg file")
        
        result = extract_exif_metadata(str(test_file))
        
        # Should return empty dict on exception
        assert result == {}
    
    def test_extract_exif_nonexistent_file(self):
        """Test that non-existent files return empty dict"""
        result = extract_exif_metadata("/nonexistent/path/image.jpg")
        
        assert result == {}
    
    def test_extract_exif_basic_structure(self, tmp_path):
        """Test that result has expected structure when EXIF exists"""
        # Create a simple JPEG with basic EXIF
        test_file = tmp_path / "test.jpg"
        img = Image.new('RGB', (100, 100), color='blue')
        
        # Save with EXIF data
        exif_data = img.getexif()
        exif_data[0x010F] = "TestMake"  # Make tag
        exif_data[0x0110] = "TestModel"  # Model tag
        
        img.save(test_file, exif=exif_data)
        
        result = extract_exif_metadata(str(test_file))
        
        # Should have the expected keys
        assert "camera_make" in result
        assert "camera_model" in result
        assert "gps_latitude" in result
        assert "gps_longitude" in result
        assert "datetime_original" in result
    
    def test_empty_dict_on_failure(self, tmp_path):
        """Test graceful degradation returns empty dict"""
        # Create an image file then delete it to simulate I/O error
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"")
        
        result = extract_exif_metadata(str(test_file))
        
        # Should be empty dict (graceful degradation)
        assert isinstance(result, dict)


class TestConvertToDegrees:
    """Test suite for _convert_to_degrees helper function"""
    
    def test_convert_standard_gps_format(self):
        """Test conversion of standard GPS tuple format"""
        from src.forensix.metadata import _convert_to_degrees
        
        # GPS format: ((degrees_num, degrees_den), (minutes_num, minutes_den), (seconds_num, seconds_den))
        gps_value = ((40, 1), (26, 1), (46, 1))
        
        result = _convert_to_degrees(gps_value)
        
        # 40 degrees + 26/60 minutes + 46/3600 seconds = 40.446111...
        assert result is not None
        assert 40.446 < result < 40.447
    
    def test_convert_with_fractional_seconds(self):
        """Test conversion with fractional seconds"""
        from src.forensix.metadata import _convert_to_degrees
        
        # Example: 73 degrees, 58 minutes, 30.5 seconds
        gps_value = ((73, 1), (58, 1), (305, 10))
        
        result = _convert_to_degrees(gps_value)
        
        # 73 + 58/60 + 30.5/3600 = 73.9751388...
        assert result is not None
        assert 73.975 < result < 73.976
    
    def test_convert_invalid_format_returns_none(self):
        """Test that invalid format returns None"""
        from src.forensix.metadata import _convert_to_degrees
        
        result = _convert_to_degrees("invalid")
        
        assert result is None
    
    def test_convert_with_zero_denominator_returns_none(self):
        """Test that zero denominator returns None"""
        from src.forensix.metadata import _convert_to_degrees
        
        gps_value = ((40, 0), (26, 1), (46, 1))
        
        result = _convert_to_degrees(gps_value)
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
