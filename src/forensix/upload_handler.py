"""
Upload orchestration module for the Upload & Fingerprint system.
Provides the main upload handler function that coordinates all upload operations.
"""

import json
import shutil
import sqlite3
import uuid
import logging
from pathlib import Path
from typing import Dict

from fastapi import UploadFile

from .config import EVIDENCE_STORAGE_DIR, DATABASE_PATH, ActionType
from .validation import validate_file_size, validate_file_extension, validate_required_params
from .hashing import compute_sha256_hash
from .metadata import extract_file_metadata, extract_exif_metadata, extract_video_metadata
from .timestamps import capture_timestamps
from .custody import create_chain_of_custody_entry

# Get module logger
logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Exception raised when upload processing fails."""
    pass


def upload_evidence_handler(file: UploadFile, uploader_id: str, collection_method: str) -> dict:
    """
    Main upload orchestration function that processes evidence file uploads.
    
    This function coordinates the complete upload workflow:
    1. Validates inputs (size, extension, required parameters)
    2. Generates unique UUID4 identifier (no deduplication - every upload gets new UUID)
    3. Saves temporary file and computes SHA-256 hash
    4. Extracts file metadata, EXIF/video metadata, and timestamps
    5. Moves file to permanent storage location ./evidence_storage/{uuid}.{ext}
    6. Creates database record in atomic transaction with custody logging
    7. Returns success response with evidence details
    
    Implements atomic rollback: on any error, deletes file from evidence_storage
    and rolls back database transaction to ensure no partial records exist.
    
    Args:
        file: FastAPI UploadFile object containing the evidence file
        uploader_id: Identifier for the investigator who uploaded the file
        collection_method: Description of how the evidence was collected
        
    Returns:
        Dictionary containing:
        - id: UUID4 identifier for the evidence
        - sha256_hash: SHA-256 hash of the file contents
        - upload_timestamp: ISO 8601 timestamp when upload was processed
        - original_filename: Original name of the uploaded file
        - file_size: Size of the file in bytes
        
    Raises:
        ValueError: For validation failures (invalid inputs)
        UploadError: For processing failures (storage, hashing, database errors)
        OSError: For disk space and file I/O errors
        
    Requirements: 1.9, 1.10, 1.11, 7.8, 8.1, 8.2, 8.3, 8.4, 8.5
    """
    
    # Step 1: Validate inputs
    # Read file content to get size for validation
    file_content = file.file.read()
    file_size = len(file_content)
    
    # Reset file pointer for later operations
    file.file.seek(0)
    
    # Validate file size (raises ValueError for 0 bytes or >500MB)
    validate_file_size(file_size)
    
    # Validate file extension (raises ValueError for unsupported formats)
    validate_file_extension(file.filename or "")
    
    # Validate required parameters (raises ValueError if missing)
    validate_required_params(uploader_id, collection_method)
    
    # Step 2: Generate unique UUID4 identifier
    # No deduplication - every upload creates a new record with unique UUID
    evidence_id = str(uuid.uuid4())
    
    # Extract file extension for storage filename
    original_filename = file.filename or "unknown"
    file_extension = Path(original_filename).suffix.lower().lstrip('.')
    if not file_extension:
        file_extension = "bin"  # Default extension if none found
    
    # Generate storage filename: {uuid}.{ext}
    storage_filename = f"{evidence_id}.{file_extension}"
    storage_path = EVIDENCE_STORAGE_DIR / storage_filename
    
    # Ensure evidence storage directory exists
    EVIDENCE_STORAGE_DIR.mkdir(exist_ok=True)
    
    # Variables for cleanup tracking
    temp_file_path = None
    final_file_created = False
    db_conn = None
    
    try:
        # Step 3: Save temporary file and compute SHA-256 hash
        # Save content to temporary file for hashing
        temp_file_path = storage_path.with_suffix(f"{storage_path.suffix}.tmp")
        try:
            with open(temp_file_path, 'wb') as temp_file:
                temp_file.write(file_content)
        except OSError as e:
            logger.error(f"Disk write error during upload for {evidence_id}: {e}")
            raise UploadError(f"Disk space error or permission denied: {str(e)}")
        
        # Compute SHA-256 hash of the file
        sha256_hash = compute_sha256_hash(str(temp_file_path))
        
        # Step 4: Extract metadata and timestamps
        # Extract file system metadata
        file_metadata = extract_file_metadata(file, str(temp_file_path))
        
        # Extract embedded metadata based on file type
        embedded_metadata = {}
        if file_extension in {'jpg', 'jpeg', 'png'}:
            # Extract EXIF metadata from images
            try:
                exif_data = extract_exif_metadata(str(temp_file_path))
                if exif_data:
                    embedded_metadata['exif'] = exif_data
            except Exception as e:
                logger.warning(f"EXIF extraction failed for {evidence_id}: {e}")
                # Continue processing with empty metadata
        elif file_extension in {'mp4', 'mov', 'avi'}:
            # Extract video metadata
            try:
                video_data = extract_video_metadata(str(temp_file_path))
                if video_data:
                    embedded_metadata['video'] = video_data
            except Exception as e:
                logger.warning(f"Video metadata extraction failed for {evidence_id}: {e}")
                # Continue processing with empty metadata
        
        # Capture timestamps (upload, creation, modification)
        timestamps = capture_timestamps(str(temp_file_path))
        
        # Step 5: Move file to permanent storage location
        try:
            shutil.move(str(temp_file_path), str(storage_path))
            final_file_created = True
            temp_file_path = None  # File has been moved, no longer temp
        except OSError as e:
            logger.error(f"Failed to move file to storage for {evidence_id}: {e}")
            raise UploadError(f"Disk space error or permission denied during file storage: {str(e)}")
        
        # Step 6: Create database record in atomic transaction
        try:
            db_conn = sqlite3.connect(DATABASE_PATH)
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database for {evidence_id}: {e}")
            raise UploadError(f"Database connection failed: {str(e)}")
        
        db_conn.execute("BEGIN TRANSACTION")
        
        try:
            # Insert evidence record
            cursor = db_conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO evidence_records (
                        id, original_filename, file_size, mime_type, file_extension,
                        sha256_hash, uploader_id, collection_method,
                        upload_timestamp, creation_timestamp, modification_timestamp,
                        extracted_metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        file_metadata['original_filename'],
                        file_metadata['file_size'],
                        file_metadata['mime_type'],
                        file_metadata['file_extension'],
                        sha256_hash,
                        uploader_id,
                        collection_method,
                        timestamps['upload_timestamp'],
                        timestamps['creation_timestamp'],
                        timestamps['modification_timestamp'],
                        json.dumps(embedded_metadata) if embedded_metadata else None
                    )
                )
            except sqlite3.DatabaseError as e:
                logger.error(f"Database error inserting evidence record {evidence_id}: {e}")
                raise UploadError(f"Database constraint violation: {str(e)}")
            except sqlite3.IntegrityError as e:
                logger.error(f"Integrity error inserting evidence record {evidence_id}: {e}")
                raise UploadError(f"Evidence record with ID already exists: {str(e)}")
            except sqlite3.Error as e:
                logger.error(f"SQLite error inserting evidence record {evidence_id}: {e}")
                raise UploadError(f"Database error: {str(e)}")
            
            # Create chain of custody entry for upload action
            try:
                create_chain_of_custody_entry(
                    db_conn,
                    evidence_id,
                    ActionType.UPLOAD,
                    f"Uploaded by {uploader_id}"
                )
            except Exception as e:
                logger.error(f"Failed to create custody entry for {evidence_id}: {e}")
                raise UploadError(f"Failed to log chain of custody: {str(e)}")
            
            # Commit transaction
            try:
                db_conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to commit transaction for {evidence_id}: {e}")
                raise UploadError(f"Database commit failed: {str(e)}")
            
        except UploadError:
            # Re-raise UploadError as-is
            raise
        except Exception as e:
            # Catch unexpected errors during transaction
            logger.error(f"Unexpected error during database operation for {evidence_id}: {e}")
            raise UploadError(f"Unexpected database error: {str(e)}")
        
        finally:
            if db_conn:
                try:
                    db_conn.close()
                except Exception:
                    pass  # Best effort cleanup
        
        # Step 7: Return success response
        logger.info(f"Evidence upload completed successfully: id={evidence_id}, uploader={uploader_id}, filename={original_filename}")
        return {
            "id": evidence_id,
            "sha256_hash": sha256_hash,
            "upload_timestamp": timestamps['upload_timestamp'],
            "original_filename": file_metadata['original_filename'],
            "file_size": file_metadata['file_size']
        }
        
    except Exception as e:
        # Atomic rollback: clean up any created files and database records
        try:
            # Remove temporary file if it still exists
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    Path(temp_file_path).unlink()
                    logger.debug(f"Cleaned up temporary file: {temp_file_path}")
                except OSError as cleanup_error:
                    logger.warning(f"Failed to clean up temporary file {temp_file_path}: {cleanup_error}")
            
            # Remove final file if it was created
            if final_file_created and storage_path.exists():
                try:
                    storage_path.unlink()
                    logger.debug(f"Cleaned up stored file: {storage_path}")
                except OSError as cleanup_error:
                    logger.warning(f"Failed to clean up stored file {storage_path}: {cleanup_error}")
            
            # Rollback database transaction if connection exists
            if db_conn:
                try:
                    db_conn.rollback()
                    db_conn.close()
                    logger.debug(f"Rolled back database transaction for {evidence_id}")
                except Exception as db_cleanup_error:
                    logger.warning(f"Failed to rollback database transaction for {evidence_id}: {db_cleanup_error}")
                    
        except Exception as cleanup_error:
            # Log cleanup errors but don't mask the original error
            logger.warning(f"Error during atomic rollback for {evidence_id}: {cleanup_error}")
        
        # Re-raise the original error
        if isinstance(e, (ValueError, UploadError, OSError)):
            raise
        else:
            logger.error(f"Unexpected error during upload for {evidence_id}: {e}")
            raise UploadError(f"Upload processing failed: {str(e)}")