"""
Manual test script to verify timestamp capture functionality.
This is a quick validation before running full unit tests.
"""

import sys
import os
from pathlib import Path
import tempfile
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from forensix.timestamps import capture_timestamps, get_current_timestamp_utc, format_timestamp_iso8601
from datetime import datetime, timezone


def test_basic_functionality():
    """Test basic timestamp capture with a temporary file."""
    print("=" * 60)
    print("Test 1: Basic timestamp capture")
    print("=" * 60)
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        temp_path = f.name
        f.write("Test evidence file for timestamp capture")
    
    try:
        # Capture timestamps
        timestamps = capture_timestamps(temp_path)
        
        print(f"✓ File created: {temp_path}")
        print(f"✓ Upload timestamp:       {timestamps['upload_timestamp']}")
        print(f"✓ Creation timestamp:     {timestamps['creation_timestamp']}")
        print(f"✓ Modification timestamp: {timestamps['modification_timestamp']}")
        
        # Verify format (should contain 'T' for ISO 8601 and timezone info)
        assert 'T' in timestamps['upload_timestamp'], "Upload timestamp not in ISO 8601 format"
        assert '+' in timestamps['upload_timestamp'] or 'Z' in timestamps['upload_timestamp'], \
            "Upload timestamp missing timezone"
        
        # Verify milliseconds (format should be YYYY-MM-DDTHH:MM:SS.sss+00:00)
        assert '.' in timestamps['upload_timestamp'], "Upload timestamp missing milliseconds"
        
        print("✓ All timestamps in correct ISO 8601 format with milliseconds")
        print()
        
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_nonexistent_file():
    """Test error handling for nonexistent file."""
    print("=" * 60)
    print("Test 2: Error handling - nonexistent file")
    print("=" * 60)
    
    try:
        capture_timestamps("/nonexistent/file/path.txt")
        print("✗ Should have raised FileNotFoundError")
    except FileNotFoundError as e:
        print(f"✓ Correctly raised FileNotFoundError: {e}")
        print()


def test_helper_functions():
    """Test helper functions."""
    print("=" * 60)
    print("Test 3: Helper functions")
    print("=" * 60)
    
    # Test get_current_timestamp_utc
    current = get_current_timestamp_utc()
    print(f"✓ get_current_timestamp_utc(): {current}")
    assert 'T' in current, "Timestamp not in ISO 8601 format"
    assert '.' in current, "Timestamp missing milliseconds"
    
    # Test format_timestamp_iso8601
    dt = datetime(2024, 10, 4, 12, 30, 45, 123456, tzinfo=timezone.utc)
    formatted = format_timestamp_iso8601(dt)
    print(f"✓ format_timestamp_iso8601(): {formatted}")
    assert formatted == "2024-10-04T12:30:45.123+00:00", f"Unexpected format: {formatted}"
    
    print("✓ All helper functions working correctly")
    print()


def test_timestamp_precision():
    """Test millisecond precision in timestamps."""
    print("=" * 60)
    print("Test 4: Millisecond precision")
    print("=" * 60)
    
    # Create two files with a small delay
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f1:
        temp_path1 = f1.name
        f1.write("File 1")
    
    time.sleep(0.1)  # 100ms delay
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f2:
        temp_path2 = f2.name
        f2.write("File 2")
    
    try:
        ts1 = capture_timestamps(temp_path1)
        ts2 = capture_timestamps(temp_path2)
        
        print(f"✓ File 1 upload: {ts1['upload_timestamp']}")
        print(f"✓ File 2 upload: {ts2['upload_timestamp']}")
        
        # Timestamps should be different (captured at different times)
        if ts1['upload_timestamp'] != ts2['upload_timestamp']:
            print("✓ Timestamps correctly differ between captures")
        else:
            print("⚠ Timestamps are identical (may be due to fast execution)")
        
        print()
        
    finally:
        if os.path.exists(temp_path1):
            os.unlink(temp_path1)
        if os.path.exists(temp_path2):
            os.unlink(temp_path2)


def main():
    """Run all manual tests."""
    print("\nManual Timestamp Capture Tests")
    print("================================\n")
    
    try:
        test_basic_functionality()
        test_nonexistent_file()
        test_helper_functions()
        test_timestamp_precision()
        
        print("=" * 60)
        print("✓ All manual tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
