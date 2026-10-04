"""
Metadata extraction functions for the Upload & Fingerprint module.

This module provides functions to extract file system metadata and embedded metadata
from evidence files (images and videos).
"""

import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import UploadFile


def extract_file_metadata(file: UploadFile, file_path: str) -> Dict[str, Any]:
    """
    Extract file system metadata from an uploaded file.
    
    Captures:
    - Original filename
    - File size in bytes
    - MIME type
    - File extension
    
    Args:
        file: The uploaded file object (FastAPI UploadFile)
        file_path: Path to the stored file on disk
        
    Returns:
        Dictionary containing:
        - original_filename: str - Original name of the uploaded file
        - file_size: int - Size in bytes
        - mime_type: str - MIME type of the file
        - file_extension: str - File extension without the dot
        
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
    """
    # Extract original filename from the uploaded file
    original_filename = file.filename if file.filename else "unknown"
    
    # Get file size from the stored file
    path_obj = Path(file_path)
    file_size = path_obj.stat().st_size if path_obj.exists() else 0
    
    # Determine MIME type
    # Priority: 1) From uploaded file content_type, 2) Guess from filename, 3) Default
    mime_type = file.content_type
    if not mime_type or mime_type == "application/octet-stream":
        # Try to guess MIME type from filename
        guessed_type, _ = mimetypes.guess_type(original_filename)
        mime_type = guessed_type if guessed_type else "application/octet-stream"
    
    # Extract file extension (without the dot)
    file_extension = Path(original_filename).suffix.lower().lstrip('.')
    if not file_extension:
        file_extension = ""
    
    return {
        "original_filename": original_filename,
        "file_size": file_size,
        "mime_type": mime_type,
        "file_extension": file_extension
    }
