"""
Unit tests for the Authentication Analyzer module.
Tests the main orchestrator functionality and integration points.
"""

import pytest
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

from src.forensix.authentication.analyzer import AuthenticationAnalyzer
from src.forensix.authentication.models import Signal, AuthenticationResult
from src.forensix.config import DATABASE_PATH, EVIDENCE_STORAGE_DIR, ANALYZER_VERSION


class TestAuthenticationAnalyzer:
    """Tests for the AuthenticationAnalyzer class."""
    
    @pytest.fixture
    def analyzer(self):
        """Create an AuthenticationAnalyzer instance for testing."""
        return AuthenticationAnalyzer()
    
    @pytest.fixture
    def sample_evidence_id(self):
        """Generate a sample evidence ID."""
        return str(uuid.uuid4())
    
    @pytest.fixture
    def setup_test_database(self):
        """Set up a test database with sample evidence record."""
        # Initialize database
        from database_setup import create_database, migrate_add_authentication_results_table
        if DATABASE_PATH.exists():
            DATABASE_PATH.unlink()
        create_database()
        migrate_add_authentication_results_table()
        
        # Insert a test evidence record
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        evidence_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO evidence_records 
            (id, original_filename, file_size, mime_type, file_extension, sha256_hash,
             uploader_id, collection_method, upload_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (evidence_id, "test.jpg", 1024, "image/jpeg", "jpg",
             "abc123def456", "test_user", "upload", "2024-01-01T00:00:00Z")
        )
        conn.commit()
        conn.close()
        
        return evidence_id
    
    def test_analyzer_initialization(self, analyzer):
        """Test that analyzer initializes with correct attributes."""
        assert analyzer.db_path == DATABASE_PATH
        assert analyzer.storage_dir == EVIDENCE_STORAGE_DIR
        assert analyzer.timeout == 300  # 5 minutes
        assert analyzer.max_file_size == 1 * 1024 * 1024 * 1024  # 1 GB
        assert analyzer.analyzer_version == ANALYZER_VERSION
    
    def test_retrieve_evidence_record_found(self, analyzer, setup_test_database):
        """Test retrieving an existing evidence record."""
        evidence = analyzer._retrieve_evidence_record(setup_test_database)
        
        assert evidence is not None
        assert evidence['id'] == setup_test_database
        assert evidence['original_filename'] == "test.jpg"
        assert evidence['mime_type'] == "image/jpeg"
        assert evidence['file_extension'] == "jpg"
    
    def test_retrieve_evidence_record_not_found(self, analyzer, setup_test_database):
        """Test retrieving a non-existent evidence record."""
        fake_id = str(uuid.uuid4())
        evidence = analyzer._retrieve_evidence_record(fake_id)
        
        assert evidence is None
    
    def test_get_evidence_file_path(self, analyzer):
        """Test file path construction."""
        evidence_id = str(uuid.uuid4())
        file_path = analyzer._get_evidence_file_path(evidence_id, "jpg")
        
        assert isinstance(file_path, Path)
        assert file_path.name == f"{evidence_id}.jpg"
        assert file_path.parent == EVIDENCE_STORAGE_DIR
    
    def test_analyze_evidence_unsupported_mime_type(self, analyzer, setup_test_database):
        """Test that unsupported MIME types are rejected."""
        # Insert evidence with unsupported MIME type
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        unsupported_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO evidence_records 
            (id, original_filename, file_size, mime_type, file_extension, sha256_hash,
             uploader_id, collection_method, upload_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (unsupported_id, "test.txt", 1024, "text/plain", "txt",
             "xyz789", "test_user", "upload", "2024-01-01T00:00:00Z")
        )
        conn.commit()
        conn.close()
        
        # Attempt to analyze should fail
        with pytest.raises(ValueError, match="Unsupported file type"):
            analyzer.analyze_evidence(unsupported_id)
    
    def test_analyze_evidence_file_not_in_storage(self, analyzer, setup_test_database):
        """Test that missing files are rejected."""
        # Try to analyze without creating the actual file
        with pytest.raises(OSError, match="Evidence file not found in storage"):
            analyzer.analyze_evidence(setup_test_database)
    
    def test_store_result_new(self, analyzer, setup_test_database):
        """Test storing a new authentication result."""
        result = AuthenticationResult(
            id=str(uuid.uuid4()),
            evidence_id=setup_test_database,
            confidence_score=85,
            verdict="AUTHENTIC",
            signals_detected=[],
            explanation="Test result",
            analyzed_at="2024-01-01T00:00:00Z",
            analyzer_version=ANALYZER_VERSION
        )
        
        analyzer._store_result(result)
        
        # Verify it was stored
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM authentication_results WHERE evidence_id = ?",
            (setup_test_database,)
        )
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row['verdict'] == "AUTHENTIC"
        assert row['confidence_score'] == 85
    
    def test_store_result_update_existing(self, analyzer, setup_test_database):
        """Test updating an existing authentication result."""
        # Insert first result
        result1 = AuthenticationResult(
            id=str(uuid.uuid4()),
            evidence_id=setup_test_database,
            confidence_score=50,
            verdict="SUSPICIOUS",
            signals_detected=[],
            explanation="First analysis",
            analyzed_at="2024-01-01T00:00:00Z",
            analyzer_version=ANALYZER_VERSION
        )
        analyzer._store_result(result1)
        
        # Insert second result (should update)
        result2 = AuthenticationResult(
            id=str(uuid.uuid4()),
            evidence_id=setup_test_database,
            confidence_score=85,
            verdict="AUTHENTIC",
            signals_detected=[],
            explanation="Updated analysis",
            analyzed_at="2024-01-01T01:00:00Z",
            analyzer_version=ANALYZER_VERSION
        )
        analyzer._store_result(result2)
        
        # Verify only one record exists and it's the updated one
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM authentication_results WHERE evidence_id = ?",
            (setup_test_database,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        assert rows[0]['verdict'] == "AUTHENTIC"
        assert rows[0]['confidence_score'] == 85
        assert rows[0]['explanation'] == "Updated analysis"
    
    def test_log_custody_event(self, analyzer, setup_test_database):
        """Test that custody event is logged correctly."""
        request_context = {
            'client_ip': '127.0.0.1',
            'user_agent': 'test-agent'
        }
        
        analyzer._log_custody_event(
            setup_test_database, 
            "AUTHENTIC", 
            85, 
            "test_actor",
            request_context
        )
        
        # Verify custody entry was created
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM custody_entries WHERE evidence_id = ? AND action_type = 'AUTHENTICATE'",
            (setup_test_database,)
        )
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert "verdict=AUTHENTIC" in row['notes']
        assert "confidence_score=85" in row['notes']
        assert "127.0.0.1" in row['notes']
    
    def test_get_cached_result_not_found(self, analyzer, setup_test_database):
        """Test that no cached result is returned when none exists."""
        result = analyzer._get_cached_result(setup_test_database)
        assert result is None
    
    def test_get_cached_result_fresh(self, analyzer, setup_test_database):
        """Test that fresh cached result is returned."""
        # Insert a recent result
        result = AuthenticationResult(
            id=str(uuid.uuid4()),
            evidence_id=setup_test_database,
            confidence_score=85,
            verdict="AUTHENTIC",
            signals_detected=[],
            explanation="Test result",
            analyzed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            analyzer_version=ANALYZER_VERSION
        )
        analyzer._store_result(result)
        
        # Retrieve cached result
        cached = analyzer._get_cached_result(setup_test_database)
        
        assert cached is not None
        assert cached['verdict'] == "AUTHENTIC"
        assert cached['confidence_score'] == 85
    
    def test_get_current_timestamp_utc(self, analyzer):
        """Test timestamp generation in ISO 8601 UTC format."""
        timestamp = analyzer._get_current_timestamp_utc()
        
        # Should be in ISO 8601 format with Z suffix
        assert timestamp.endswith("Z")
        assert "T" in timestamp
        
        # Should be parseable as ISO 8601
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        assert isinstance(dt, datetime)
    
    def test_aggregate_signals_empty(self, analyzer):
        """Test signal aggregation with no signals."""
        confidence, verdict, explanation = analyzer._aggregate_signals([], "image/jpeg")
        
        assert confidence == 50
        assert verdict == "SUSPICIOUS"
        assert "No authentication signals" in explanation
    
    def test_aggregate_signals_high_score(self, analyzer):
        """Test signal aggregation with high confidence signals."""
        signal = Signal(
            signal_name="TEST_SIGNAL",
            category="METADATA",
            severity="INFO",
            score=90,
            message="Test"
        )
        
        confidence, verdict, explanation = analyzer._aggregate_signals([signal], "image/jpeg")
        
        assert confidence == 90
        assert verdict == "AUTHENTIC"
    
    def test_aggregate_signals_mid_score(self, analyzer):
        """Test signal aggregation with moderate confidence signals."""
        signals = [
            Signal("S1", "METADATA", "INFO", 60, "Test1"),
            Signal("S2", "STRUCTURE", "WARNING", 40, "Test2")
        ]
        
        confidence, verdict, explanation = analyzer._aggregate_signals(signals, "image/jpeg")
        
        assert confidence == 50
        assert verdict == "SUSPICIOUS"
    
    def test_aggregate_signals_low_score(self, analyzer):
        """Test signal aggregation with low confidence signals."""
        signal = Signal(
            signal_name="TEST_SIGNAL",
            category="ENCODING",
            severity="CRITICAL",
            score=30,
            message="Test"
        )
        
        confidence, verdict, explanation = analyzer._aggregate_signals([signal], "video/mp4")
        
        assert confidence == 30
        assert verdict == "TAMPERED"


class TestSignalModel:
    """Tests for the Signal data model."""
    
    def test_signal_creation_valid(self):
        """Test creating a valid Signal."""
        signal = Signal(
            signal_name="EXIF_COMPLETE",
            category="METADATA",
            severity="INFO",
            score=85,
            message="EXIF metadata found"
        )
        
        assert signal.signal_name == "EXIF_COMPLETE"
        assert signal.category == "METADATA"
        assert signal.severity == "INFO"
        assert signal.score == 85
    
    def test_signal_invalid_severity(self):
        """Test that invalid severity raises error."""
        with pytest.raises(ValueError, match="Invalid severity"):
            Signal(
                signal_name="TEST",
                category="METADATA",
                severity="INVALID",
                score=50,
                message="Test"
            )
    
    def test_signal_invalid_score_range(self):
        """Test that score outside 0-100 raises error."""
        with pytest.raises(ValueError, match="Score must be integer 0-100"):
            Signal("TEST", "METADATA", "INFO", 150, "Test")
        
        with pytest.raises(ValueError, match="Score must be integer 0-100"):
            Signal("TEST", "METADATA", "INFO", -5, "Test")
    
    def test_signal_to_dict(self):
        """Test converting Signal to dict."""
        signal = Signal(
            signal_name="TEST",
            category="METADATA",
            severity="WARNING",
            score=75,
            message="Test message",
            details={"key": "value"}
        )
        
        d = signal.to_dict()
        
        assert d["signal_name"] == "TEST"
        assert d["category"] == "METADATA"
        assert d["severity"] == "WARNING"
        assert d["score"] == 75
        assert d["message"] == "Test message"
        assert d["details"] == {"key": "value"}
    
    def test_signal_json_roundtrip(self):
        """Test JSON serialization roundtrip."""
        signal1 = Signal("TEST", "METADATA", "INFO", 50, "Message", {"key": "value"})
        json_str = signal1.to_json()
        signal2 = Signal.from_json(json_str)
        
        assert signal1.signal_name == signal2.signal_name
        assert signal1.category == signal2.category
        assert signal1.severity == signal2.severity
        assert signal1.score == signal2.score
        assert signal1.message == signal2.message
        assert signal1.details == signal2.details


class TestAuthenticationResultModel:
    """Tests for the AuthenticationResult data model."""
    
    def test_result_creation_valid(self):
        """Test creating a valid AuthenticationResult."""
        signals = [
            Signal("EXIF_COMPLETE", "METADATA", "INFO", 85, "Found EXIF")
        ]
        
        result = AuthenticationResult(
            id=str(uuid.uuid4()),
            evidence_id=str(uuid.uuid4()),
            confidence_score=85,
            verdict="AUTHENTIC",
            signals_detected=signals,
            explanation="Image is authentic",
            analyzed_at="2024-01-01T00:00:00Z",
            analyzer_version="1.0.0"
        )
        
        assert result.confidence_score == 85
        assert result.verdict == "AUTHENTIC"
        assert len(result.signals_detected) == 1
    
    def test_result_invalid_confidence_score(self):
        """Test that invalid confidence_score raises error."""
        with pytest.raises(ValueError, match="Confidence score must be integer 0-100"):
            AuthenticationResult(
                id=str(uuid.uuid4()),
                evidence_id=str(uuid.uuid4()),
                confidence_score=150,
                verdict="AUTHENTIC",
                signals_detected=[],
                explanation="Test",
                analyzed_at="2024-01-01T00:00:00Z",
                analyzer_version="1.0.0"
            )
    
    def test_result_invalid_verdict(self):
        """Test that invalid verdict raises error."""
        with pytest.raises(ValueError, match="Invalid verdict"):
            AuthenticationResult(
                id=str(uuid.uuid4()),
                evidence_id=str(uuid.uuid4()),
                confidence_score=85,
                verdict="INVALID",
                signals_detected=[],
                explanation="Test",
                analyzed_at="2024-01-01T00:00:00Z",
                analyzer_version="1.0.0"
            )
    
    def test_result_explanation_too_long(self):
        """Test that explanation > 5000 chars raises error."""
        with pytest.raises(ValueError, match="Explanation exceeds 5000 chars"):
            AuthenticationResult(
                id=str(uuid.uuid4()),
                evidence_id=str(uuid.uuid4()),
                confidence_score=85,
                verdict="AUTHENTIC",
                signals_detected=[],
                explanation="X" * 5001,
                analyzed_at="2024-01-01T00:00:00Z",
                analyzer_version="1.0.0"
            )
    
    def test_result_signals_as_json(self):
        """Test converting signals to JSON string."""
        signals = [
            Signal("EXIF_COMPLETE", "METADATA", "INFO", 85, "Found EXIF"),
            Signal("HEADER_VALID", "STRUCTURE", "INFO", 90, "Header valid")
        ]
        
        result = AuthenticationResult(
            id=str(uuid.uuid4()),
            evidence_id=str(uuid.uuid4()),
            confidence_score=87,
            verdict="AUTHENTIC",
            signals_detected=signals,
            explanation="Test",
            analyzed_at="2024-01-01T00:00:00Z",
            analyzer_version="1.0.0"
        )
        
        json_str = result.signals_as_json()
        
        import json
        parsed = json.loads(json_str)
        assert len(parsed) == 2
        assert parsed[0]["signal_name"] == "EXIF_COMPLETE"
        assert parsed[1]["signal_name"] == "HEADER_VALID"
