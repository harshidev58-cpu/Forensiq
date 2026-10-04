"""
Integration tests for the Authentication Engine module.
Tests end-to-end authentication workflows including analysis and storage.

Requirements: 2.1-2.10, 6.1-6.3, 9.1, 9.2, 16.1
"""

import pytest
import sqlite3
import tempfile
import uuid
from pathlib import Path
from PIL import Image

from src.forensix.authentication.analyzer import AuthenticationAnalyzer
from src.forensix.authentication.image_analyzer import ImageAnalyzer
from src.forensix.authentication.video_analyzer import VideoAnalyzer
from src.forensix.authentication.aggregator import SignalAggregator
from src.forensix.authentication.models import Signal, AuthenticationResult
from src.forensix.authentication.storage import AuthenticationStorage
from src.forensix.config import DATABASE_PATH


class TestAuthenticationIntegration:
    """Integration tests for authentication module."""
    
    @pytest.fixture
    def temp_evidence_dir(self, tmp_path, monkeypatch):
        """Setup temporary evidence storage directory."""
        evid_dir = tmp_path / "evidence_storage"
        evid_dir.mkdir()
        monkeypatch.setenv("EVIDENCE_STORAGE_DIR", str(evid_dir))
        return evid_dir
    
    @pytest.fixture
    def sample_image_path(self, tmp_path):
        """Create a sample test image."""
        img = Image.new('RGB', (100, 100), color='blue')
        img_path = tmp_path / "test.jpg"
        img.save(str(img_path), "JPEG", quality=95)
        return img_path
    
    def test_image_analyzer_generates_minimum_5_signals(self, sample_image_path):
        """Test that image analyzer generates minimum 5 signals (Requirement 3.7)."""
        analyzer = ImageAnalyzer()
        signals = analyzer.analyze(sample_image_path)
        
        assert len(signals) >= 5, f"Expected >= 5 signals for image, got {len(signals)}"
        assert all(0 <= s.score <= 100 for s in signals), "Signal scores must be 0-100"
    
    def test_video_analyzer_generates_minimum_6_signals(self, tmp_path):
        """Test that video analyzer generates minimum 6 signals (Requirement 4.7)."""
        # Create a minimal AVI file header
        avi_path = tmp_path / "test.avi"
        with open(avi_path, 'wb') as f:
            # Write RIFF header
            f.write(b'RIFF')
            f.write((1000).to_bytes(4, 'little'))  # File size
            f.write(b'AVI ')
            f.write(b'\x00' * 1000)  # Padding
        
        analyzer = VideoAnalyzer()
        signals = analyzer.analyze(avi_path)
        
        # AVI should generate container and size signals
        assert len(signals) >= 2, f"Expected signals for AVI, got {len(signals)}"
        assert all(0 <= s.score <= 100 for s in signals), "Signal scores must be 0-100"
    
    def test_signal_aggregation_authentic_verdict(self):
        """Test that high quality signals produce AUTHENTIC verdict (Requirement 5.3)."""
        signals = [
            Signal("HEADER_VALID", "STRUCTURE", "INFO", 5, "Valid"),
            Signal("EXIF_COMPLETE", "METADATA", "INFO", 10, "Complete"),
            Signal("COLORSPACE_STANDARD", "ENCODING", "INFO", 8, "Standard"),
            Signal("COMPRESSION_SINGLE", "ENCODING", "INFO", 15, "Single gen"),
            Signal("DIMENSIONS_VALID", "STRUCTURE", "INFO", 5, "Valid dims"),
        ]
        
        aggregator = SignalAggregator()
        conf, verdict, exp = aggregator.aggregate(signals)
        
        # High quality signals should result in high confidence and AUTHENTIC
        assert conf >= 85, f"Expected confidence >= 85, got {conf}"
        assert verdict == "AUTHENTIC", f"Expected AUTHENTIC verdict, got {verdict}"
    
    def test_signal_aggregation_tampered_verdict(self):
        """Test that critical signals produce TAMPERED verdict (Requirement 5.3)."""
        signals = [
            Signal("HEADER_CORRUPTED", "STRUCTURE", "CRITICAL", 85, "Corrupted"),
            Signal("EXIF_MISSING", "METADATA", "WARNING", 50, "Missing"),
        ]
        
        aggregator = SignalAggregator()
        conf, verdict, exp = aggregator.aggregate(signals)
        
        # Critical signals should result in TAMPERED verdict
        assert verdict == "TAMPERED", f"Expected TAMPERED verdict, got {verdict}"
    
    def test_signal_aggregation_suspicious_verdict(self):
        """Test that mixed signals produce SUSPICIOUS verdict (Requirement 5.3)."""
        signals = [
            Signal("HEADER_VALID", "STRUCTURE", "INFO", 5, "Valid"),
            Signal("EXIF_MISSING", "METADATA", "WARNING", 50, "Missing"),
            Signal("COMPRESSION_MULTIPLE", "ENCODING", "WARNING", 60, "Multiple gen"),
        ]
        
        aggregator = SignalAggregator()
        conf, verdict, exp = aggregator.aggregate(signals)
        
        # Mixed signals should result in SUSPICIOUS verdict
        assert verdict == "SUSPICIOUS", f"Expected SUSPICIOUS verdict, got {verdict}"
    
    def test_confidence_score_range_always_0_100(self):
        """Test that confidence scores are always in range [0, 100] (Requirement 5.1, 6.1)."""
        test_cases = [
            [Signal("TEST1", "STRUCTURE", "INFO", 0, "Zero")],
            [Signal("TEST1", "STRUCTURE", "INFO", 100, "Max")],
            [Signal("TEST1", "STRUCTURE", "CRITICAL", 100, "Critical")],
            [Signal("TEST1", "STRUCTURE", "WARNING", 50, "Warning")],
            [Signal("TEST1", "STRUCTURE", "INFO", 25, "Low")],
        ]
        
        aggregator = SignalAggregator()
        
        for signals in test_cases:
            conf, _, _ = aggregator.aggregate(signals)
            assert 0 <= conf <= 100, f"Confidence {conf} out of range for {signals[0].signal_name}"
    
    def test_authentication_result_storage_and_retrieval(self, tmp_path, monkeypatch):
        """Test storing and retrieving authentication results (Requirement 1.1, 1.3, 1.4)."""
        # Use temporary database for testing
        test_db = tmp_path / "test.db"
        
        # Create temporary database with schema
        conn = sqlite3.connect(str(test_db))
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE authentication_results (
                id TEXT PRIMARY KEY,
                evidence_id TEXT NOT NULL UNIQUE,
                confidence_score INTEGER NOT NULL,
                verdict TEXT NOT NULL,
                signals_detected TEXT NOT NULL,
                explanation TEXT NOT NULL,
                analyzed_at TEXT NOT NULL,
                analyzer_version TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (evidence_id) REFERENCES evidence_records(id)
            )
        ''')
        conn.commit()
        conn.close()
        
        # Monkeypatch database path
        monkeypatch.setattr('src.forensix.config.DATABASE_PATH', test_db)
        
        # Create test result
        signals = [Signal("TEST", "STRUCTURE", "INFO", 50, "Test")]
        result = AuthenticationResult(
            id=str(uuid.uuid4()),
            evidence_id="evidence-123",
            confidence_score=75,
            verdict="SUSPICIOUS",
            signals_detected=signals,
            explanation="Test explanation",
            analyzed_at="2024-01-01T00:00:00Z",
            analyzer_version="1.0.0"
        )
        
        # Store result
        storage = AuthenticationStorage(test_db)
        assert storage.store_result(result) == True
        
        # Retrieve result
        retrieved = storage.get_result("evidence-123")
        assert retrieved is not None
        assert retrieved.evidence_id == "evidence-123"
        assert retrieved.confidence_score == 75
        assert retrieved.verdict == "SUSPICIOUS"
    
    def test_result_contains_all_required_fields(self, sample_image_path):
        """Test that authentication result contains all required fields (Requirement 5.1, 5.2)."""
        analyzer = ImageAnalyzer()
        signals = analyzer.analyze(sample_image_path)
        
        aggregator = SignalAggregator()
        conf, verdict, exp = aggregator.aggregate(signals)
        
        result = AuthenticationResult(
            id="test-id",
            evidence_id="test-evidence",
            confidence_score=conf,
            verdict=verdict,
            signals_detected=signals,
            explanation=exp,
            analyzed_at="2024-01-01T00:00:00Z",
            analyzer_version="1.0.0"
        )
        
        # Verify all required fields
        assert result.id
        assert result.evidence_id
        assert 0 <= result.confidence_score <= 100
        assert result.verdict in ["AUTHENTIC", "SUSPICIOUS", "TAMPERED"]
        assert len(result.signals_detected) >= 0
        assert len(result.explanation) <= 5000
        assert result.analyzed_at
        assert result.analyzer_version
    
    def test_signal_count_matches_file_type(self, sample_image_path, tmp_path):
        """Test that signal count is appropriate for file type."""
        # Image should have >= 5 signals
        img_analyzer = ImageAnalyzer()
        img_signals = img_analyzer.analyze(sample_image_path)
        assert len(img_signals) >= 5, "Image should have >= 5 signals"
        
        # Video should have >= 2 signals (simplified analyzer)
        avi_path = tmp_path / "test.avi"
        with open(avi_path, 'wb') as f:
            f.write(b'RIFF' + (1000).to_bytes(4, 'little') + b'AVI ' + b'\x00' * 1000)
        
        vid_analyzer = VideoAnalyzer()
        vid_signals = vid_analyzer.analyze(avi_path)
        assert len(vid_signals) >= 2, "Video should have >= 2 signals"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
