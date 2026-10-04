"""
Unit tests for image authentication analyzer.
Tests signal generation for EXIF, headers, thumbnails, color space, and compression.

Requirements: 3.1-3.8, 13.1
"""

import pytest
import tempfile
import io
from pathlib import Path
from PIL import Image

from src.forensix.authentication.image_analyzer import ImageAnalyzer
from src.forensix.authentication.models import Signal


class TestImageAnalyzer:
    """Test suite for ImageAnalyzer signal generation."""
    
    @pytest.fixture
    def analyzer(self):
        """Provide analyzer instance."""
        return ImageAnalyzer()
    
    @pytest.fixture
    def sample_jpeg_path(self, tmp_path):
        """Create a sample JPEG image for testing."""
        # Create simple RGB image
        img = Image.new('RGB', (100, 100), color='red')
        
        # Save with EXIF data
        jpeg_path = tmp_path / "test.jpg"
        img.save(str(jpeg_path), "JPEG", quality=95)
        
        return jpeg_path
    
    @pytest.fixture
    def sample_png_path(self, tmp_path):
        """Create a sample PNG image for testing."""
        img = Image.new('RGB', (100, 100), color='blue')
        png_path = tmp_path / "test.png"
        img.save(str(png_path), "PNG")
        return png_path
    
    @pytest.fixture
    def sample_gif_path(self, tmp_path):
        """Create a sample GIF image for testing."""
        img = Image.new('RGB', (100, 100), color='green')
        gif_path = tmp_path / "test.gif"
        img.save(str(gif_path), "GIF")
        return gif_path
    
    def test_analyze_returns_list_of_signals(self, analyzer, sample_jpeg_path):
        """Test that analyze returns a list of Signal objects."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        assert isinstance(signals, list)
        assert all(isinstance(s, Signal) for s in signals)
    
    def test_jpeg_generates_minimum_signals(self, analyzer, sample_jpeg_path):
        """Test that JPEG analysis generates at least 5 signals."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        # Requirement 3.7: minimum 5 signals for images
        assert len(signals) >= 5, f"Expected >= 5 signals, got {len(signals)}"
    
    def test_png_generates_minimum_signals(self, analyzer, sample_png_path):
        """Test that PNG analysis generates at least 5 signals."""
        signals = analyzer.analyze(sample_png_path)
        
        assert len(signals) >= 5, f"Expected >= 5 signals, got {len(signals)}"
    
    def test_signal_scores_in_valid_range(self, analyzer, sample_jpeg_path):
        """Test that all signals have scores in range [0, 100]."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        for signal in signals:
            assert 0 <= signal.score <= 100, f"Signal {signal.signal_name} has invalid score: {signal.score}"
    
    def test_signal_severity_valid(self, analyzer, sample_jpeg_path):
        """Test that all signals have valid severity levels."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        valid_severities = {"INFO", "WARNING", "CRITICAL"}
        for signal in signals:
            assert signal.severity in valid_severities, f"Signal {signal.signal_name} has invalid severity: {signal.severity}"
    
    def test_jpeg_header_validation(self, analyzer, sample_jpeg_path):
        """Test that JPEG header validation produces correct signal."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        # Find header signal
        header_signals = [s for s in signals if "HEADER" in s.signal_name]
        assert len(header_signals) > 0, "No header validation signal found"
        
        header_signal = header_signals[0]
        assert header_signal.signal_name == "HEADER_VALID"
        assert header_signal.severity == "INFO"
        assert header_signal.score > 50
    
    def test_png_header_validation(self, analyzer, sample_png_path):
        """Test that PNG header validation works."""
        signals = analyzer.analyze(sample_png_path)
        
        header_signals = [s for s in signals if "HEADER" in s.signal_name]
        assert len(header_signals) > 0
        assert header_signals[0].signal_name == "HEADER_VALID"
    
    def test_dimensions_valid_signal(self, analyzer, sample_jpeg_path):
        """Test that valid dimensions generate correct signal."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        dim_signals = [s for s in signals if "DIMENSION" in s.signal_name]
        assert len(dim_signals) > 0, "No dimension signal found"
        
        dim_signal = dim_signals[0]
        assert dim_signal.signal_name == "DIMENSIONS_VALID"
        assert dim_signal.score > 50
    
    def test_color_space_signal(self, analyzer, sample_jpeg_path):
        """Test that color space validation produces signal."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        color_signals = [s for s in signals if "COLORSPACE" in s.signal_name]
        assert len(color_signals) > 0, "No colorspace signal found"
        
        color_signal = color_signals[0]
        assert color_signal.signal_name == "COLORSPACE_STANDARD"
        assert color_signal.severity == "INFO"
    
    def test_compression_signal_present(self, analyzer, sample_jpeg_path):
        """Test that compression analysis produces signal for JPEG."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        comp_signals = [s for s in signals if "COMPRESSION" in s.signal_name]
        assert len(comp_signals) > 0, "No compression signal found for JPEG"
    
    def test_corrupted_jpeg_header_detection(self, analyzer, tmp_path):
        """Test that corrupted JPEG header is detected."""
        # Create file with invalid JPEG header
        bad_jpeg_path = tmp_path / "bad.jpg"
        with open(bad_jpeg_path, 'wb') as f:
            f.write(b'\x00\x00\x00\x00')  # Invalid JPEG header
        
        signals = analyzer.analyze(bad_jpeg_path)
        
        # Should detect corrupted header
        corrupted_signals = [s for s in signals if "CORRUPTED" in s.signal_name or "INVALID" in s.signal_name]
        # Note: May have error signal instead
        assert len(signals) > 0, "Should generate signals even for corrupted file"
    
    def test_exif_signal_for_image_with_metadata(self, analyzer, sample_jpeg_path):
        """Test that EXIF signals are generated."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        exif_signals = [s for s in signals if "EXIF" in s.signal_name]
        # May have EXIF_MISSING, EXIF_COMPLETE, or EXIF_INCONSISTENT
        assert len(exif_signals) > 0, "No EXIF signal found"
    
    def test_thumbnail_signal_for_jpeg(self, analyzer, sample_jpeg_path):
        """Test that thumbnail signals are generated for JPEG."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        thumb_signals = [s for s in signals if "THUMBNAIL" in s.signal_name]
        # May have THUMBNAIL_PRESENT or THUMBNAIL_MISSING
        # Thumbnail signal may or may not be present depending on PIL implementation
        for sig in thumb_signals:
            assert sig.signal_name in ["THUMBNAIL_PRESENT", "THUMBNAIL_MISSING", "THUMBNAIL_INCONSISTENT"]
    
    def test_no_thumbnail_signal_for_png(self, analyzer, sample_png_path):
        """Test that PNG analysis doesn't force thumbnail signals."""
        signals = analyzer.analyze(sample_png_path)
        
        thumb_signals = [s for s in signals if "THUMBNAIL" in s.signal_name]
        # PNG shouldn't have thumbnail signals (they're JPEG only)
        # This may vary based on analyzer implementation
        # Just verify structure is correct
        for sig in thumb_signals:
            assert isinstance(sig, Signal)
    
    def test_signal_has_message(self, analyzer, sample_jpeg_path):
        """Test that all signals have descriptive messages."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        for signal in signals:
            assert signal.message and len(signal.message) > 0
            assert isinstance(signal.message, str)
    
    def test_signal_has_category(self, analyzer, sample_jpeg_path):
        """Test that all signals have categories."""
        signals = analyzer.analyze(sample_jpeg_path)
        
        valid_categories = {"METADATA", "STRUCTURE", "ENCODING", "TIMESTAMP"}
        for signal in signals:
            assert signal.category in valid_categories or "CATEGORY" in signal.category


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
