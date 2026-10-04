"""
Core utility functions for the Upload & Fingerprint module.

This module provides utility functions for:
- SHA-256 hash computation with streaming support
- Timestamp capture and formatting
- File metadata extraction
"""

import hashlib
import time
from pathlib import Path
from typing import Dict, Any, Optional


class HashComputationError(Exception):
    """Base exception for hash computation errors."""
    pass


class HashTimeoutError(HashComputationError):
    """Raised when hash computation exceeds the timeout limit."""
    pass


class HashIOError(HashComputationError):
    """Raised when file I/O fails during hash computation."""
    pass


def compute_sha256_hash(file_path: str, timeout: int = 300) -> str:
    """
    Compute SHA-256 hash of file using streaming to handle large files.
    
    This function uses 8KB chunks to process files efficiently, allowing it to
    handle large files without loading them entirely into memory. It includes
    timeout protection to prevent indefinite hanging on very large files.
    
    Args:
        file_path: Path to the file to hash
        timeout: Maximum seconds allowed for computation (default: 300)
        
    Returns:
        Hexadecimal hash string (64 characters)
        
    Raises:
        HashTimeoutError: If computation exceeds timeout limit
        HashIOError: If file cannot be read or does not exist
        
    Requirements:
        - 2.1: Compute SHA-256 hash of file contents
        - 2.2: Compute hash before file transformation
        - 2.3: Store hash as hexadecimal string
        - 2.4: Ensure idempotent hash computation
        - 2.6: Handle timeout (300 seconds)
        - 2.7: Handle file I/O errors
    """
    sha256_hash = hashlib.sha256()
    chunk_size = 8192  # 8KB chunks for streaming
    
    start_time = time.time()
    
    try:
        with open(file_path, "rb") as f:
            while True:
                # Check timeout before reading each chunk
                if time.time() - start_time > timeout:
                    raise HashTimeoutError(
                        f"Hash computation timeout: exceeded {timeout} seconds"
                    )
                
                # Read next chunk
                chunk = f.read(chunk_size)
                
                # End of file
                if not chunk:
                    break
                
                # Update hash with chunk
                sha256_hash.update(chunk)
                
    except HashTimeoutError:
        # Re-raise timeout errors
        raise
    except (IOError, OSError, FileNotFoundError) as e:
        # Wrap I/O errors with our custom exception
        raise HashIOError(
            f"File read error during hash computation: {str(e)}"
        ) from e
    except Exception as e:
        # Catch any other unexpected errors
        raise HashIOError(
            f"Unexpected error during hash computation: {str(e)}"
        ) from e
    
    return sha256_hash.hexdigest()
