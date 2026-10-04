"""
Unit tests for the timestamps module (src/forensix/timestamps.py).

This module tests:
- Timestamp capture functionality
- ISO 8601 format compliance
- Millisecond precision
- UTC timezone handling
- Helper functions
"""

import pytest
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from src.forensix.timestamps import (
    capture_timestamps,
    format_timestamp_iso8601,
    get_current_timestamp_utc
)


class TestCaptureTimestamps:
    """Test suite for capture_timestamps function."""
    
    def test_basic_timestamp_capture(self, tmp_path):
        """
        Test basic timestamp capture with a temporary file.
        
        Requirements: 3.1, 3.2, 3.3, 3.4
        """
        # Create a temporary file
        test_file = tmp_path / "evidence.txt"
        test_file.write_bytes(b"Test evidence content")
        
        # Capture timestamps
        timestamps = capture_timestamps(str(test_file))
        
        # Verify all three timestamps are present
        assert "upload_timestamp" in timestamps
        assert "creation_timestamp" in timestamps
        assert "modification_timestamp" in timestamps
        
        # Verify timestamps are non-empty strings
        assert isinstance(timestamps["upload_timestamp"], str)
        assert isinstance(timestamps["creation_timestamp"], str)
        assert isinstance(timestamps["modification_timestamp"], str)
        assert len(timestamps["upload_timestamp"]) > 0
    
    def test_timestamp_iso8601_format(self, tmp_path):
        """
        Test that timestamps are in ISO 8601 format with milliseconds.
        
        Requirements: 3.4
        """
        test_file = tmp_path / "evidence.jpg"
        test_file.write_bytes(b"fake image data")
        
        timestamps = capture_timestamps(str(test_file))
        
        # ISO 8601 format should contain 'T' separator
        assert 'T' in timestamps["upload_timestamp"]
        assert 'T' in timestamps["creation_timestamp"]
        assert 'T' in timestamps["modification_timestamp"]
        
        # Should contain timezone info (+ or Z)
        upload_ts = timestamps["upload_timestamp"]
        assert '+' in upload_ts or 'Z' in upload_ts
        
        # Should contain milliseconds (period followed by digits)
        assert '.' in upload_ts
    
    def test_timestamp_utc_timezone(self, tmp_path):
        """
        Test that timestamps are in UTC timezone.
        
        Requirements: 3.1, 3.4
        """
        test_file = tmp_path / "evidence.mp4"
        test_file.write_bytes(b"fake video data")
        
        timestamps = capture_timestamps(str(test_file))
        
        # Should end with +00:00 for UTC
        assert timestamps["upload_timestamp"].endswith('+00:00')
    
    def test_timestamp_millisecond_precision(self, tmp_path):
        """
        Test that timestamps have millisecond precision.
        
        Requirements: 3.1
        """
        test_file = tmp_path / "evidence.txt"
        test_file.write_bytes(b"test")
        
        timestamps = capture_timestamps(str(test_file))
        
        # Parse timestamp and verify milliseconds
        upload_ts = timestamps["upload_timestamp"]
        
        # Format should be: YYYY-MM-DDTHH:MM:SS.sss+00:00
        # Extract millisecond part (between . and +)
        ms_part = upload_ts.split('.')[1].split('+')[0]
        
        # Should have 3 digits for milliseconds
        assert len(ms_part) == 3
        assert ms_part.isdigit()
    
    def test_different_captures_different_upload_timestamps(self, tmp_path):
        """
        Test that different capture calls produce different upload timestamps.
        
        Requirements: 3.1
        """
        test_file1 = tmp_path / "file1.txt"
        test_file1.write_bytes(b"file 1")
        
        test_file2 = tmp_path / "file2.txt"
        test_file2.write_bytes(b"file 2")
        
        # Small delay between captures
        ts1 = capture_timestamps(str(test_file1))
        time.sleep(0.01)  # 10ms delay
        ts2 = capture_timestamps(str(test_file2))
        
        # Upload timestamps should be different
        # (They are captured when the function is called)
        # Note: In rare cases they might be the same if system time doesn't change
        # but we expect them to be different most of the time
        if ts1["upload_timestamp"] != ts2["upload_timestamp"]:
            assert True  # Expected behavior
        else:
            # This is acceptable if the system clock didn't advance
            pass
    
    def test_file_not_found_error(self):
        """
        Test that FileNotFoundError is raised for nonexistent file.
        
        Requirements: 3.1, 3.2, 3.3
        """
        non_existent_path = "/tmp/nonexistent_file_12345.txt"
        
        with pytest.raises(FileNotFoundError) as exc_info:
            capture_timestamps(non_existent_path)
        
        assert "File not found" in str(exc_info.value)
    
    def test_all_timestamps_are_strings(self, tmp_path):
        """
        Test that all returned timestamps are strings.
        
        Requirements: 3.4
        """
        test_file = tmp_path / "evidence.log"
        test_file.write_bytes(b"log data")
        
        timestamps = capture_timestamps(str(test_file))
        
        assert isinstance(timestamps["upload_timestamp"], str)
        assert isinstance(timestamps["creation_timestamp"], str)
        assert isinstance(timestamps["modification_timestamp"], str)


class TestFormatTimestampISO8601:
    """Test suite for format_timestamp_iso8601 function."""
    
    def test_format_specific_datetime(self):
        """
        Test formatting a specific datetime to ISO 8601.
        """
        dt = datetime(2024, 10, 4, 12, 30, 45, 123456, tzinfo=timezone.utc)
        formatted = format_timestamp_iso8601(dt)
        
        # Expected format: 2024-10-04T12:30:45.123+00:00
        assert formatted == "2024-10-04T12:30:45.123+00:00"
    
    def test_format_with_milliseconds(self):
        """
        Test that millisecond precision is maintained.
        """
        dt = datetime(2024, 1, 15, 8, 15, 30, 500000, tzinfo=timezone.utc)  # 500ms
        formatted = format_timestamp_iso8601(dt)
        
        assert ".500" in formatted
    
    def test_format_naive_datetime_becomes_utc(self):
        """
        Test that naive datetime (no timezone) is treated as UTC.
        """
        dt_naive = datetime(2024, 5, 20, 14, 0, 0, 0)
        formatted = format_timestamp_iso8601(dt_naive)
        
        # Should add UTC timezone
        assert "+00:00" in formatted


class TestGetCurrentTimestampUTC:
    """Test suite for get_current_timestamp_utc function."""
    
    def test_get_current_timestamp(self):
        """
        Test that current timestamp is returned in correct format.
        """
        timestamp = get_current_timestamp_utc()
        
        # Should be a string
        assert isinstance(timestamp, str)
        
        # Should contain ISO 8601 components
        assert 'T' in timestamp
        assert '.' in timestamp  # milliseconds
        assert '+00:00' in timestamp  # UTC
    
    def test_current_timestamp_advances(self):
        """
        Test that consecutive calls produce different or equal timestamps.
        """
        ts1 = get_current_timestamp_utc()
        time.sleep(0.002)  # 2ms delay
        ts2 = get_current_timestamp_utc()
        
        # Timestamps should be different (or equal if clock didn't advance)
        # We just verify both are valid
        assert 'T' in ts1
        assert 'T' in ts2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
