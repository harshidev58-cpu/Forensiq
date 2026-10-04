"""
Timestamp capture module for ForensiX Upload & Fingerprint.

This module provides functionality to capture temporal metadata for evidence files,
including upload timestamps, file creation timestamps, and modification timestamps.
All timestamps are captured in UTC with millisecond precision in ISO 8601 format.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


def capture_timestamps(file_path: str) -> Dict[str, str]:
    """
    Capture upload, creation, and modification timestamps for an evidence file.
    
    This function captures three types of timestamps:
    1. Upload timestamp: The current time when this function is called (UTC)
    2. Creation timestamp: File system creation time (ctime on Unix, creation time on Windows)
    3. Modification timestamp: File system last modification time (mtime)
    
    All timestamps are formatted in ISO 8601 format with millisecond precision
    and UTC timezone offset (+00:00 or Z suffix).
    
    Args:
        file_path: Absolute or relative path to the evidence file
        
    Returns:
        Dictionary containing three timestamp strings:
        - "upload_timestamp": Current UTC time in ISO 8601 format
        - "creation_timestamp": File creation time in ISO 8601 format
        - "modification_timestamp": File modification time in ISO 8601 format
        
    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be accessed
        OSError: If file system metadata cannot be read
        
    Example:
        >>> timestamps = capture_timestamps("/path/to/evidence.jpg")
        >>> timestamps
        {
            "upload_timestamp": "2024-10-04T00:30:45.123+00:00",
            "creation_timestamp": "2024-10-03T15:20:10.456+00:00",
            "modification_timestamp": "2024-10-03T18:45:30.789+00:00"
        }
    
    Requirements:
        - Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
    """
    # Capture upload timestamp first (current time in UTC with millisecond precision)
    upload_timestamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    
    # Get file path object for metadata access
    file_path_obj = Path(file_path)
    
    # Check if file exists
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Get file statistics
    try:
        file_stat = file_path_obj.stat()
    except PermissionError as e:
        raise PermissionError(f"Permission denied accessing file: {file_path}") from e
    except OSError as e:
        raise OSError(f"Error reading file metadata: {file_path}") from e
    
    # Capture creation timestamp from file system metadata
    # Note: st_ctime is creation time on Windows, change time on Unix/Linux
    # For forensic purposes, we capture what the file system provides
    creation_timestamp = datetime.fromtimestamp(
        file_stat.st_ctime,
        tz=timezone.utc
    ).isoformat(timespec='milliseconds')
    
    # Capture modification timestamp from file system metadata
    modification_timestamp = datetime.fromtimestamp(
        file_stat.st_mtime,
        tz=timezone.utc
    ).isoformat(timespec='milliseconds')
    
    return {
        "upload_timestamp": upload_timestamp,
        "creation_timestamp": creation_timestamp,
        "modification_timestamp": modification_timestamp
    }


def format_timestamp_iso8601(dt: datetime) -> str:
    """
    Format a datetime object to ISO 8601 string with millisecond precision.
    
    This is a helper function to ensure consistent timestamp formatting
    across the application.
    
    Args:
        dt: datetime object (should be timezone-aware, preferably UTC)
        
    Returns:
        ISO 8601 formatted string with millisecond precision
        
    Example:
        >>> dt = datetime(2024, 10, 4, 12, 30, 45, 123456, tzinfo=timezone.utc)
        >>> format_timestamp_iso8601(dt)
        "2024-10-04T12:30:45.123+00:00"
    """
    # Ensure datetime is timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.isoformat(timespec='milliseconds')


def get_current_timestamp_utc() -> str:
    """
    Get the current timestamp in UTC with millisecond precision.
    
    This is a convenience function for generating upload timestamps
    and other current-time captures throughout the application.
    
    Returns:
        Current timestamp in ISO 8601 format with millisecond precision
        
    Example:
        >>> timestamp = get_current_timestamp_utc()
        >>> timestamp
        "2024-10-04T00:30:45.123+00:00"
    """
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')
