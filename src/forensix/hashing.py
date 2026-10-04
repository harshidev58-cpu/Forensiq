"""
Hash computation module for ForensiX Upload & Fingerprint.

This module provides SHA-256 cryptographic fingerprinting functionality for evidence files.
Uses streaming hash computation (8KB chunks) to efficiently handle large files while
enforcing timeout and file size limits for forensic evidence processing.
"""

import hashlib
import os
import signal
from pathlib import Path
from typing import Optional


class HashComputationError(Exception):
    """Exception raised when hash computation fails."""
    pass


class HashTimeoutError(HashComputationError):
    """Exception raised when hash computation exceeds timeout."""
    pass


class FileSizeExceededError(HashComputationError):
    """Exception raised when file exceeds maximum size for hashing."""
    pass


def _timeout_handler(signum, frame):
    """Signal handler for hash computation timeout."""
    raise HashTimeoutError("Hash computation timeout")


def compute_sha256_hash(file_path: str, timeout: int = 300) -> str:
    """
    Compute SHA-256 cryptographic hash of an evidence file.
    
    This function computes the SHA-256 hash using streaming (8KB chunks) to
    efficiently handle large files without loading the entire file into memory.
    Enforces a configurable timeout (default 300 seconds) and file size limit
    (10 GB maximum) for forensic processing requirements.
    
    The hash is computed BEFORE any file transformation or metadata extraction
    to ensure the fingerprint represents the original uploaded content.
    
    Args:
        file_path: Absolute or relative path to the evidence file
        timeout: Maximum time in seconds for hash computation (default: 300)
        
    Returns:
        64-character hexadecimal SHA-256 hash string (lowercase)
        
    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be read
        FileSizeExceededError: If file exceeds 10 GB limit (HTTP 413)
        HashTimeoutError: If computation exceeds timeout (HTTP 500)
        HashComputationError: If file I/O error occurs during hashing (HTTP 500)
        
    Example:
        >>> hash_value = compute_sha256_hash("/path/to/evidence.jpg")
        >>> hash_value
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        >>> len(hash_value)
        64
    
    Requirements:
        - Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
    """
    # Constants from config
    HASH_CHUNK_SIZE = 8192  # 8KB chunks
    MAX_HASH_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB
    
    # Validate file exists
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Check file size limit (10 GB max)
    try:
        file_size = file_path_obj.stat().st_size
    except PermissionError as e:
        raise PermissionError(f"Permission denied reading file: {file_path}") from e
    except OSError as e:
        raise HashComputationError(f"Error accessing file: {file_path}") from e
    
    if file_size > MAX_HASH_FILE_SIZE:
        raise FileSizeExceededError(
            f"File exceeds maximum size for hash computation ({MAX_HASH_FILE_SIZE} bytes)"
        )
    
    # Set up timeout using signal (Unix-based systems)
    # Note: signal.alarm() only works on Unix-like systems and only in main thread
    old_handler = None
    timeout_set = False
    try:
        if hasattr(signal, 'SIGALRM') and timeout > 0:
            try:
                old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(timeout)
                timeout_set = True
            except ValueError:
                # signal.signal() raises ValueError if not in main thread
                # Continue without timeout in this case
                pass
    except Exception:
        # Ignore any signal setup errors
        pass
    
    try:
        # Initialize SHA-256 hasher
        sha256_hasher = hashlib.sha256()
        
        # Stream file in chunks and update hash
        with open(file_path_obj, 'rb') as f:
            while True:
                chunk = f.read(HASH_CHUNK_SIZE)
                if not chunk:
                    break
                sha256_hasher.update(chunk)
        
        # Return hexadecimal hash string (64 characters, lowercase)
        return sha256_hasher.hexdigest()
        
    except HashTimeoutError:
        # Re-raise timeout error as-is
        raise
        
    except PermissionError as e:
        raise PermissionError(f"Permission denied reading file: {file_path}") from e
        
    except OSError as e:
        raise HashComputationError(f"File read error during hash computation: {file_path}") from e
        
    except Exception as e:
        raise HashComputationError(f"Unexpected error during hash computation: {e}") from e
        
    finally:
        # Cancel timeout alarm and restore old handler
        if timeout_set and hasattr(signal, 'SIGALRM') and old_handler is not None:
            try:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
            except ValueError:
                # Ignore errors if not in main thread
                pass


def verify_hash_format(hash_value: str) -> bool:
    """
    Verify that a hash string is a valid 64-character hexadecimal SHA-256 hash.
    
    Args:
        hash_value: Hash string to validate
        
    Returns:
        True if valid SHA-256 hash format, False otherwise
        
    Example:
        >>> verify_hash_format("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        True
        >>> verify_hash_format("invalid")
        False
    """
    if not isinstance(hash_value, str):
        return False
    
    # SHA-256 produces 64-character hexadecimal string
    if len(hash_value) != 64:
        return False
    
    # Check if all characters are valid hexadecimal (0-9, a-f, A-F)
    try:
        int(hash_value, 16)
        return True
    except ValueError:
        return False


def compute_hash_with_verification(file_path: str, timeout: int = 300) -> str:
    """
    Compute SHA-256 hash and verify the result format.
    
    This is a convenience function that combines hash computation with
    format verification to ensure the returned hash is valid.
    
    Args:
        file_path: Path to the evidence file
        timeout: Maximum time in seconds for hash computation
        
    Returns:
        Verified 64-character hexadecimal SHA-256 hash string
        
    Raises:
        HashComputationError: If hash format verification fails
        (Also raises all exceptions from compute_sha256_hash)
    """
    hash_value = compute_sha256_hash(file_path, timeout)
    
    if not verify_hash_format(hash_value):
        raise HashComputationError(
            f"Hash computation produced invalid format: {hash_value}"
        )
    
    return hash_value
