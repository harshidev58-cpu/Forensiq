"""
Evidence integrity verification module for ForensiX.
Provides SHA-256 hash verification and tampering detection functionality.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, Optional

from .hashing import compute_sha256_hash, verify_hash_format, HashComputationError, HashTimeoutError
from .custody import create_chain_of_custody_entry
from .timestamps import get_current_timestamp_utc
from .config import EVIDENCE_STORAGE_DIR

# Configure logger
logger = logging.getLogger(__name__)


class EvidenceNotFoundError(Exception):
    """Exception raised when evidence record is not found."""
    pass


class EvidenceFileNotFoundError(Exception):
    """Exception raised when evidence file is missing from storage."""
    pass


def verify_evidence_integrity(conn: sqlite3.Connection, evidence_id: str) -> Dict[str, str]:
    """
    Verify the integrity of stored evidence by recomputing its SHA-256 hash.
    
    This function implements the integrity verification workflow:
    1. Retrieve the original SHA-256 hash from evidence_records
    2. Retrieve the file from ./evidence_storage/{evidence_id}.{ext}
    3. Compute a new SHA-256 hash of the current file contents
    4. Compare the new hash against the original hash
    5. Log a chain of custody entry with the verification result
    
    The comparison is case-insensitive to handle any hex encoding variations.
    
    Args:
        conn: SQLite database connection
        evidence_id: UUID of the evidence record to verify
        
    Returns:
        Dictionary containing verification results:
        - status: "PASS" if hashes match, "FAIL" if they differ
        - original_hash: 64-character hexadecimal SHA-256 hash from database
        - computed_hash: 64-character hexadecimal SHA-256 hash of current file
        - verification_timestamp: ISO 8601 UTC timestamp when verification occurred
        
    Raises:
        EvidenceNotFoundError: If evidence record does not exist in database
        EvidenceFileNotFoundError: If evidence file is missing from storage
        HashComputationError: If hash computation fails (file I/O error)
        HashTimeoutError: If hash computation exceeds 300 second timeout
        
    Requirements:
        - Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.9
    """
    try:
        # Step 1: Retrieve original hash and file extension from evidence record
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sha256_hash, file_extension
            FROM evidence_records
            WHERE id = ?
            """,
            (evidence_id,)
        )
        
        row = cursor.fetchone()
        
        if not row:
            error_msg = f"Evidence record not found: {evidence_id}"
            logger.warning(error_msg)
            raise EvidenceNotFoundError(error_msg)
        
        original_hash = row[0]
        file_extension = row[1]
        
        # Validate the stored hash format
        if not verify_hash_format(original_hash):
            logger.error(f"Invalid hash format in database for evidence {evidence_id}: {original_hash}")
            raise ValueError(f"Invalid stored hash format for evidence {evidence_id}")
        
        # Step 2: Construct file path and verify file exists
        file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.{file_extension}"
        
        if not file_path.exists():
            error_msg = f"Evidence file missing from storage: {file_path}"
            logger.error(error_msg)
            raise EvidenceFileNotFoundError(error_msg)
        
        # Step 3: Compute new SHA-256 hash of current file
        try:
            computed_hash = compute_sha256_hash(str(file_path), timeout=300)
        except HashTimeoutError as e:
            logger.error(f"Hash computation timeout for evidence {evidence_id}: {e}")
            raise
        except HashComputationError as e:
            logger.error(f"Hash computation error for evidence {evidence_id}: {e}")
            raise
        
        # Validate the computed hash format
        if not verify_hash_format(computed_hash):
            logger.error(f"Hash computation produced invalid format for evidence {evidence_id}: {computed_hash}")
            raise HashComputationError(f"Invalid hash format computed for evidence {evidence_id}")
        
        # Step 4: Compare hashes (case-insensitive)
        hashes_match = original_hash.lower() == computed_hash.lower()
        status = "PASS" if hashes_match else "FAIL"
        
        # Capture verification timestamp
        verification_timestamp = get_current_timestamp_utc()
        
        # Step 5: Log chain of custody entry with verification result
        # Non-blocking: custody logging failure doesn't raise exception
        try:
            notes = f"Result: {status}"
            create_chain_of_custody_entry(
                conn,
                evidence_id,
                "VERIFY",
                notes=notes
            )
        except Exception as e:
            # Non-blocking: log error but don't raise
            logger.error(f"Failed to log custody entry for verification: {e}")
        
        # Build result dictionary
        result = {
            "status": status,
            "original_hash": original_hash,
            "computed_hash": computed_hash,
            "verification_timestamp": verification_timestamp
        }
        
        logger.info(f"Evidence integrity verification completed: {evidence_id}, status={status}")
        
        return result
        
    except (EvidenceNotFoundError, EvidenceFileNotFoundError, HashTimeoutError, HashComputationError):
        # Re-raise expected exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error during integrity verification for evidence {evidence_id}: {e}")
        raise
