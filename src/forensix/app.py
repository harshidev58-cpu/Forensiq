"""
FastAPI application for the Upload & Fingerprint module.
Main application entry point with database initialization.
"""

import sqlite3
import logging
import logging.handlers
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import DATABASE_PATH, EVIDENCE_STORAGE_DIR, MAX_BATCH_FILES, MAX_BATCH_SIZE
from .upload_handler import upload_evidence_handler, UploadError
from .custody import create_chain_of_custody_entry, get_chain_of_custody_entries
from .verification import verify_evidence_integrity, EvidenceNotFoundError, EvidenceFileNotFoundError
from .hashing import HashTimeoutError, HashComputationError

# Configure structured logging with console and file output
def configure_logging():
    """
    Configure structured logging for the ForensiX application.
    
    Logs are written to:
    - Console (stdout) with INFO level
    - File (forensix.log) with DEBUG level for detailed diagnostics
    
    Includes timestamp, logger name, log level, and message in all outputs.
    Requirements: 8.4
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Define consistent log format with timestamp and error details
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%dT%H:%M:%S')
    
    # Console handler (INFO level)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (DEBUG level, rotates at 10MB, keeps 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        'forensix.log',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Suppress noisy FastAPI/Uvicorn logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Call logging configuration at import time
configure_logging()

# Get module logger
logger = logging.getLogger(__name__)


# Database connection management
def get_db_connection() -> sqlite3.Connection:
    """Get SQLite database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn


def initialize_database():
    """Initialize database and ensure evidence storage directory exists."""
    
    # Ensure evidence storage directory exists
    EVIDENCE_STORAGE_DIR.mkdir(exist_ok=True)
    print(f"✓ Evidence storage directory: {EVIDENCE_STORAGE_DIR.absolute()}")
    
    # Create database if it doesn't exist
    if not DATABASE_PATH.exists():
        print("Database not found. Creating new database...")
        # Import and run database setup
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from database_setup import create_database
        create_database()
    else:
        print(f"✓ Database found: {DATABASE_PATH.absolute()}")
    
    # Verify database connection
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM evidence_records")
        evidence_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM custody_entries")
        custody_count = cursor.fetchone()[0]
        conn.close()
        print(f"✓ Database verified: {evidence_count} evidence records, {custody_count} custody entries")
    except sqlite3.Error as e:
        raise RuntimeError(f"Database verification failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown."""
    # Startup
    print("Starting ForensiX Upload & Fingerprint service...")
    initialize_database()
    yield
    # Shutdown
    print("Shutting down ForensiX Upload & Fingerprint service...")


# Create FastAPI application
app = FastAPI(
    title="ForensiX Upload & Fingerprint",
    description="Digital evidence upload, fingerprinting, and chain of custody tracking",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return {
            "status": "healthy",
            "service": "ForensiX Upload & Fingerprint",
            "database": "connected",
            "evidence_storage": str(EVIDENCE_STORAGE_DIR.absolute())
        }
    except sqlite3.DatabaseError as e:
        logger.error(f"Database error in health check: {e}")
        raise HTTPException(status_code=503, detail="Database connection failed")
    except sqlite3.Error as e:
        logger.error(f"SQLite error in health check: {e}")
        raise HTTPException(status_code=503, detail="Database error occurred")
    except Exception as e:
        logger.error(f"Unexpected error in health check: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "service": "ForensiX Upload & Fingerprint",
        "version": "1.0.0",
        "description": "Digital evidence upload, fingerprinting, and chain of custody tracking",
        "endpoints": {
            "health": "/health",
            "upload": "/evidence/upload",
            "batch_upload": "/evidence/upload/batch",
            "get_evidence": "/evidence/{id}",
            "download_file": "/evidence/{id}/file",
            "get_custody": "/evidence/{id}/custody",
            "verify_integrity": "/evidence/{id}/verify"
        }
    }



# ============================================================================
# Pydantic Models for Request/Response Validation
# ============================================================================

class EvidenceUploadResponse(BaseModel):
    """Response model for successful evidence upload."""
    id: str = Field(..., description="Unique identifier (UUID4) for the evidence")
    sha256_hash: str = Field(..., description="SHA-256 hash of the file contents (64-char hex string)")
    upload_timestamp: str = Field(..., description="ISO 8601 timestamp when upload was processed (UTC)")
    original_filename: str = Field(..., description="Original filename of the uploaded evidence")
    file_size: int = Field(..., description="File size in bytes")


class BatchUploadResult(BaseModel):
    """Result for a single file in batch upload operation."""
    original_filename: str = Field(..., description="Original filename of the file")
    id: Optional[str] = Field(None, description="Unique identifier (UUID4) if upload succeeded")
    sha256_hash: Optional[str] = Field(None, description="SHA-256 hash if upload succeeded")
    status: int = Field(..., description="HTTP status code for this file (201 success, 400/413 error)")
    error: Optional[str] = Field(None, description="Error message if upload failed")


class BatchUploadResponse(BaseModel):
    """Response model for batch upload operation."""
    results: List[BatchUploadResult] = Field(..., description="Array of results for each file")


class EvidenceRecord(BaseModel):
    """Response model for evidence record retrieval."""
    id: str = Field(..., description="Unique identifier (UUID4) for the evidence")
    original_filename: str = Field(..., description="Original filename of the uploaded evidence")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type of the file")
    file_extension: str = Field(..., description="File extension (lowercase, no dot)")
    sha256_hash: str = Field(..., description="SHA-256 hash of the file contents (64-char hex string)")
    uploader_id: str = Field(..., description="Identifier for the uploader")
    collection_method: str = Field(..., description="Description of how evidence was collected")
    upload_timestamp: str = Field(..., description="ISO 8601 timestamp when upload was processed (UTC)")
    creation_timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp of file creation (UTC)")
    modification_timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp of file modification (UTC)")
    extracted_metadata: Optional[dict] = Field(None, description="Extracted metadata (EXIF/video)")


class ChainOfCustodyEntry(BaseModel):
    """Response model for chain of custody entry."""
    id: int = Field(..., description="Unique entry ID")
    evidence_id: str = Field(..., description="Evidence record ID")
    action_type: str = Field(..., description="Type of action (UPLOAD, ACCESS, VERIFY)")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the action (UTC)")
    notes: Optional[str] = Field(None, description="Optional notes about the action")


class VerificationResult(BaseModel):
    """Response model for evidence integrity verification."""
    status: str = Field(..., description="Verification result: 'PASS' if hashes match, 'FAIL' if different")
    original_hash: str = Field(..., description="Original SHA-256 hash from database (64-char hex string)")
    computed_hash: str = Field(..., description="Newly computed SHA-256 hash (64-char hex string)")
    verification_timestamp: str = Field(..., description="ISO 8601 timestamp when verification occurred (UTC)")


# ============================================================================
# Upload Endpoints
# ============================================================================

@app.post("/evidence/upload", response_model=EvidenceUploadResponse, status_code=201)
async def upload_evidence(
    file: UploadFile = File(..., description="Evidence file to upload"),
    uploader_id: str = Form(..., description="Identifier for the uploader"),
    collection_method: str = Form(..., description="Description of how evidence was collected")
):
    """
    Upload a single evidence file.
    
    Accepts a single evidence file with metadata about the uploader and collection method.
    Performs validation (file size, extension), computes SHA-256 hash, extracts metadata,
    and stores the file in the evidence storage directory.
    
    Requirements: 1.1, 1.2, 1.3, 1.11, 7.8, 8.1, 8.2, 8.3, 8.4
    
    Args:
        file: The evidence file to upload (multipart/form-data)
        uploader_id: Identifier for the investigator uploading the file
        collection_method: Description of how the evidence was collected
        
    Returns:
        201 Created: Evidence upload response with ID, hash, timestamp, filename, and size
        
    Raises:
        400 Bad Request: Invalid input (missing fields, unsupported format, 0-byte file)
        413 Payload Too Large: File exceeds 500 MB limit
        500 Internal Server Error: Processing error (storage, hashing, database)
    """
    try:
        # Call upload handler which validates, processes, and stores the file
        result = upload_evidence_handler(file, uploader_id, collection_method)
        logger.info(f"Evidence uploaded successfully: id={result['id']}, uploader={uploader_id}")
        return EvidenceUploadResponse(**result)
        
    except ValueError as e:
        # Validation error (missing params, invalid format, 0-byte file)
        error_msg = str(e)
        logger.warning(f"Upload validation error: {error_msg}, uploader={uploader_id}")
        
        # Check if it's a file size error
        if "exceeds maximum limit" in error_msg or "0 bytes" in error_msg:
            if "exceeds maximum limit" in error_msg:
                raise HTTPException(status_code=413, detail=error_msg)
            else:
                raise HTTPException(status_code=400, detail=error_msg)
        
        raise HTTPException(status_code=400, detail=error_msg)
        
    except UploadError as e:
        # Check if it's a file size error (413) or processing error (500)
        error_msg = str(e)
        if "exceeds maximum limit" in error_msg or "exceeds maximum size for hash" in error_msg:
            logger.warning(f"Upload file size error: {error_msg}, uploader={uploader_id}")
            raise HTTPException(status_code=413, detail=error_msg)
        elif "disk space" in error_msg.lower() or isinstance(e.__cause__, OSError):
            # Handle disk space exhaustion
            logger.error(f"Disk space error during upload: {error_msg}, uploader={uploader_id}")
            raise HTTPException(status_code=500, detail="Insufficient disk space for file storage")
        else:
            logger.error(f"Upload processing error: {error_msg}, uploader={uploader_id}")
            raise HTTPException(status_code=500, detail="Internal server error during upload processing")
            
    except OSError as e:
        # Handle disk space and file I/O errors
        logger.error(f"File I/O error during upload: {e}, uploader={uploader_id}")
        raise HTTPException(status_code=500, detail="File storage error or insufficient disk space")
        
    except sqlite3.DatabaseError as e:
        # Handle database errors
        logger.error(f"Database error during upload: {e}, uploader={uploader_id}")
        raise HTTPException(status_code=500, detail="Database error occurred during upload")
        
    except sqlite3.Error as e:
        # Handle other SQLite errors
        logger.error(f"SQLite error during upload: {e}, uploader={uploader_id}")
        raise HTTPException(status_code=500, detail="Database operation failed")
        
    except Exception as e:
        # Unexpected error
        error_msg = str(e)
        logger.error(f"Unexpected upload error: {error_msg}, uploader={uploader_id}")
        raise HTTPException(status_code=500, detail="Internal server error during upload processing")


@app.post("/evidence/upload/batch", status_code=207)
async def batch_upload_evidence(
    files: List[UploadFile] = File(..., description="Multiple evidence files to upload"),
    uploader_id: str = Form(..., description="Identifier for the uploader"),
    collection_method: str = Form(..., description="Description of how evidence was collected")
):
    """
    Upload multiple evidence files in a single batch request.
    
    Accepts multiple evidence files and processes them independently. Returns HTTP 207
    (Multi-Status) indicating partial success is possible. Each file is processed and
    results in either success (201) or failure (400/413) status.
    
    Validates constraints:
    - Maximum 100 files
    - Maximum 2 GB combined size
    
    Continues processing remaining files even if one fails.
    
    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 8.1, 8.2, 8.3, 8.4
    
    Args:
        files: List of evidence files to upload
        uploader_id: Identifier for the investigator uploading the files
        collection_method: Description of how the evidence was collected
        
    Returns:
        207 Multi-Status: Batch upload response with individual results for each file
        
    Raises:
        400 Bad Request: If validation fails (missing params)
        413 Payload Too Large: If file count exceeds 100 or combined size exceeds 2 GB
    """
    try:
        # Validate batch constraints
        if not files:
            logger.warning(f"Batch upload attempted with no files, uploader={uploader_id}")
            raise HTTPException(status_code=400, detail="No files provided")
        
        if len(files) > MAX_BATCH_FILES:
            logger.warning(f"Batch upload exceeded max files: {len(files)} > {MAX_BATCH_FILES}, uploader={uploader_id}")
            raise HTTPException(
                status_code=413,
                detail=f"Too many files: maximum {MAX_BATCH_FILES} files allowed, got {len(files)}"
            )
        
        # Validate required parameters
        if not uploader_id or not collection_method:
            logger.warning(f"Batch upload missing required parameters")
            raise HTTPException(status_code=400, detail="Uploader_ID and Collection_Method are required")
        
        # Validate combined batch size (read all files to calculate total size)
        total_size = 0
        file_contents = []
        for file in files:
            try:
                # Read file content to get size
                content = await file.read()
                total_size += len(content)
                file_contents.append((file, content))
            except Exception as e:
                logger.error(f"Error reading file during batch size validation: {e}")
                raise HTTPException(status_code=500, detail="Error reading file during batch validation")
        
        if total_size > MAX_BATCH_SIZE:
            logger.warning(f"Batch upload exceeded max size: {total_size} > {MAX_BATCH_SIZE}, uploader={uploader_id}")
            raise HTTPException(
                status_code=413,
                detail=f"Batch size exceeds limit: maximum {MAX_BATCH_SIZE // (1024*1024*1024)} GB, got {total_size // (1024*1024*1024)} GB"
            )
        
        # Process each file independently
        results = []
        for idx, (file, content) in enumerate(file_contents):
            try:
                # Create a new UploadFile-like object with the content we already read
                # Reset file.file to BytesIO with content
                file.file = BytesIO(content)
                file.file.seek(0)
                
                # Upload the individual file
                result = upload_evidence_handler(file, uploader_id, collection_method)
                
                # Success result
                logger.info(f"Batch upload - file {idx+1} succeeded: id={result['id']}, filename={file.filename}")
                results.append(BatchUploadResult(
                    original_filename=file.filename or "unknown",
                    id=result["id"],
                    sha256_hash=result["sha256_hash"],
                    status=201,
                    error=None
                ))
                
            except ValueError as e:
                # Validation error (400)
                error_msg = str(e)
                logger.warning(f"Batch upload - file {idx+1} validation error: {error_msg}, filename={file.filename}")
                results.append(BatchUploadResult(
                    original_filename=file.filename or "unknown",
                    status=400,
                    error=error_msg
                ))
                
            except UploadError as e:
                # Upload processing error
                error_msg = str(e)
                if "exceeds maximum limit" in error_msg or "exceeds maximum size for hash" in error_msg:
                    # File size error (413)
                    logger.warning(f"Batch upload - file {idx+1} size error: {error_msg}, filename={file.filename}")
                    results.append(BatchUploadResult(
                        original_filename=file.filename or "unknown",
                        status=413,
                        error=error_msg
                    ))
                else:
                    # Processing error (500)
                    logger.error(f"Batch upload - file {idx+1} processing error: {error_msg}, filename={file.filename}")
                    results.append(BatchUploadResult(
                        original_filename=file.filename or "unknown",
                        status=500,
                        error="Processing failed"
                    ))
                    
            except OSError as e:
                # Handle disk space and file I/O errors
                logger.error(f"Batch upload - file {idx+1} I/O error: {e}, filename={file.filename}")
                results.append(BatchUploadResult(
                    original_filename=file.filename or "unknown",
                    status=500,
                    error="File storage error or insufficient disk space"
                ))
                
            except sqlite3.DatabaseError as e:
                # Handle database errors
                logger.error(f"Batch upload - file {idx+1} database error: {e}, filename={file.filename}")
                results.append(BatchUploadResult(
                    original_filename=file.filename or "unknown",
                    status=500,
                    error="Database error occurred"
                ))
                
            except sqlite3.Error as e:
                # Handle other SQLite errors
                logger.error(f"Batch upload - file {idx+1} SQLite error: {e}, filename={file.filename}")
                results.append(BatchUploadResult(
                    original_filename=file.filename or "unknown",
                    status=500,
                    error="Database operation failed"
                ))
                
            except Exception as e:
                # Unexpected error
                error_msg = str(e)
                logger.error(f"Batch upload - file {idx+1} unexpected error: {error_msg}, filename={file.filename}")
                results.append(BatchUploadResult(
                    original_filename=file.filename or "unknown",
                    status=500,
                    error="Internal server error"
                ))
        
        # Determine overall status code
        status_code = 207  # Multi-Status by default
        
        # Check if all succeeded (should return 200)
        if all(r.status == 201 for r in results):
            status_code = 200
            logger.info(f"Batch upload completed successfully: {len(results)} files, uploader={uploader_id}")
        
        # Check if all failed (should return 400)
        elif all(r.status >= 400 for r in results):
            status_code = 400
            logger.warning(f"Batch upload completely failed: all {len(results)} files failed, uploader={uploader_id}")
        
        else:
            logger.info(f"Batch upload partially successful: {sum(1 for r in results if r.status == 201)}/{len(results)} files, uploader={uploader_id}")
        
        return BatchUploadResponse(results=results)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in batch upload endpoint: {e}, uploader={uploader_id}")
        raise HTTPException(status_code=500, detail="Internal server error during batch upload")


# ============================================================================
# Evidence Retrieval Endpoints
# ============================================================================

@app.get("/evidence/{evidence_id}", response_model=EvidenceRecord, status_code=200)
async def get_evidence_record(evidence_id: str):
    """
    Retrieve a complete evidence record by ID.
    
    Queries the database for the evidence record and logs a chain of custody access entry.
    
    Requirements: 9.1, 9.2, 9.3, 9.7, 11.3, 8.1, 8.2, 8.3, 8.4
    
    Args:
        evidence_id: Unique identifier (UUID) of the evidence record
        
    Returns:
        200 OK: Complete evidence record JSON with all fields
        
    Raises:
        404 Not Found: If evidence record does not exist
        500 Internal Server Error: If database error occurs
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query evidence record by ID
        try:
            cursor.execute(
                """
                SELECT id, original_filename, file_size, mime_type, file_extension, 
                       sha256_hash, uploader_id, collection_method, upload_timestamp,
                       creation_timestamp, modification_timestamp, extracted_metadata
                FROM evidence_records
                WHERE id = ?
                """,
                (evidence_id,)
            )
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error retrieving evidence {evidence_id}: {e}")
            conn.close()
            raise HTTPException(status_code=500, detail="Database error occurred")
        except sqlite3.Error as e:
            logger.error(f"SQLite error retrieving evidence {evidence_id}: {e}")
            conn.close()
            raise HTTPException(status_code=500, detail="Database query failed")
        
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            logger.warning(f"Evidence record not found: {evidence_id}")
            raise HTTPException(status_code=404, detail="Evidence record not found")
        
        # Convert row to dictionary
        evidence = {
            'id': row[0],
            'original_filename': row[1],
            'file_size': row[2],
            'mime_type': row[3],
            'file_extension': row[4],
            'sha256_hash': row[5],
            'uploader_id': row[6],
            'collection_method': row[7],
            'upload_timestamp': row[8],
            'creation_timestamp': row[9],
            'modification_timestamp': row[10],
            'extracted_metadata': row[11]
        }
        
        # Parse extracted_metadata if it's a JSON string
        if evidence['extracted_metadata']:
            try:
                import json
                evidence['extracted_metadata'] = json.loads(evidence['extracted_metadata'])
            except (json.JSONDecodeError, TypeError):
                # If metadata is invalid JSON, store as None
                logger.warning(f"Invalid metadata JSON for evidence {evidence_id}")
                evidence['extracted_metadata'] = None
        
        # Log chain of custody entry for ACCESS action (non-blocking)
        try:
            create_chain_of_custody_entry(conn, evidence_id, "ACCESS", notes="Evidence record retrieved")
        except Exception as e:
            # Non-blocking: log error but don't raise
            logger.error(f"Failed to log custody entry for access to {evidence_id}: {e}")
        
        conn.close()
        
        logger.info(f"Evidence record retrieved: {evidence_id}")
        return EvidenceRecord(**evidence)
        
    except HTTPException:
        raise
    except sqlite3.DatabaseError as e:
        logger.error(f"Database error retrieving evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred")
    except sqlite3.Error as e:
        logger.error(f"SQLite error retrieving evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database operation failed")
    except Exception as e:
        logger.error(f"Unexpected error retrieving evidence record {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during evidence retrieval")


@app.get("/evidence/{evidence_id}/file", status_code=200)
async def download_evidence_file(evidence_id: str):
    """
    Download the evidence file associated with an ID.
    
    Retrieves the file from storage and returns it with appropriate Content-Type header.
    Logs a chain of custody access entry.
    
    Requirements: 9.4, 9.5, 9.6, 9.7, 8.1, 8.2, 8.3, 8.4
    
    Args:
        evidence_id: Unique identifier (UUID) of the evidence record
        
    Returns:
        200 OK: File content with Content-Type header matching the stored MIME type
        
    Raises:
        404 Not Found: If evidence record or file does not exist
        500 Internal Server Error: If database error or file read error occurs
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query to get file_extension and mime_type
        try:
            cursor.execute(
                """
                SELECT file_extension, mime_type
                FROM evidence_records
                WHERE id = ?
                """,
                (evidence_id,)
            )
        except sqlite3.DatabaseError as e:
            conn.close()
            logger.error(f"Database error retrieving file metadata for {evidence_id}: {e}")
            raise HTTPException(status_code=500, detail="Database error occurred")
        except sqlite3.Error as e:
            conn.close()
            logger.error(f"SQLite error retrieving file metadata for {evidence_id}: {e}")
            raise HTTPException(status_code=500, detail="Database query failed")
        
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            logger.warning(f"Evidence file not found (record missing): {evidence_id}")
            raise HTTPException(status_code=404, detail="Evidence file not found")
        
        file_extension = row[0]
        mime_type = row[1]
        
        # Construct file path
        file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.{file_extension}"
        
        # Check if file exists
        if not file_path.exists():
            conn.close()
            logger.warning(f"Evidence file not found (file missing from storage): {evidence_id}")
            raise HTTPException(status_code=404, detail="Evidence file not found")
        
        # Log chain of custody entry for ACCESS action (non-blocking)
        try:
            create_chain_of_custody_entry(conn, evidence_id, "ACCESS", notes="Evidence file downloaded")
        except Exception as e:
            # Non-blocking: log error but don't raise
            logger.error(f"Failed to log custody entry for file access {evidence_id}: {e}")
        
        conn.close()
        
        logger.info(f"Evidence file downloaded: {evidence_id}")
        
        # Return file with Content-Type header
        return FileResponse(
            path=file_path,
            media_type=mime_type,
            filename=f"{evidence_id}.{file_extension}"
        )
        
    except HTTPException:
        raise
    except OSError as e:
        logger.error(f"File read error downloading evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="File read error")
    except sqlite3.DatabaseError as e:
        logger.error(f"Database error downloading evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred")
    except sqlite3.Error as e:
        logger.error(f"SQLite error downloading evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database operation failed")
    except Exception as e:
        logger.error(f"Unexpected error downloading evidence file {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during file download")


@app.get("/evidence/{evidence_id}/custody", response_model=List[ChainOfCustodyEntry], status_code=200)
async def get_custody_chain(evidence_id: str):
    """
    Retrieve the complete chain of custody for an evidence record.
    
    Queries all custody entries for the specified evidence ID and returns them
    sorted by timestamp in ascending order. This provides an audit trail of all
    access and verification actions performed on the evidence.
    
    Requirements: 11.5, 11.6, 11.7, 8.1, 8.2, 8.3, 8.4
    
    Args:
        evidence_id: Unique identifier (UUID) of the evidence record
        
    Returns:
        200 OK: JSON array of chain of custody entries sorted by timestamp
                [{id, evidence_id, action_type, timestamp, notes}, ...]
        
    Raises:
        404 Not Found: If evidence record does not exist
        500 Internal Server Error: If database error occurs
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First, verify the evidence record exists
        try:
            cursor.execute(
                """
                SELECT id FROM evidence_records WHERE id = ?
                """,
                (evidence_id,)
            )
        except sqlite3.DatabaseError as e:
            conn.close()
            logger.error(f"Database error verifying evidence {evidence_id}: {e}")
            raise HTTPException(status_code=500, detail="Database error occurred")
        except sqlite3.Error as e:
            conn.close()
            logger.error(f"SQLite error verifying evidence {evidence_id}: {e}")
            raise HTTPException(status_code=500, detail="Database query failed")
        
        if not cursor.fetchone():
            conn.close()
            logger.warning(f"Evidence record not found for custody query: {evidence_id}")
            raise HTTPException(status_code=404, detail="Evidence record not found")
        
        # Retrieve all custody entries for this evidence, sorted by timestamp ascending
        try:
            entries = get_chain_of_custody_entries(conn, evidence_id)
        except sqlite3.DatabaseError as e:
            conn.close()
            logger.error(f"Database error retrieving custody entries for {evidence_id}: {e}")
            raise HTTPException(status_code=500, detail="Database error occurred")
        except sqlite3.Error as e:
            conn.close()
            logger.error(f"SQLite error retrieving custody entries for {evidence_id}: {e}")
            raise HTTPException(status_code=500, detail="Database query failed")
        
        conn.close()
        
        logger.info(f"Chain of custody retrieved for evidence {evidence_id}: {len(entries)} entries")
        
        # Convert to ChainOfCustodyEntry models
        return [ChainOfCustodyEntry(**entry) for entry in entries]
        
    except HTTPException:
        raise
    except sqlite3.DatabaseError as e:
        logger.error(f"Database error retrieving custody chain for evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred")
    except sqlite3.Error as e:
        logger.error(f"SQLite error retrieving custody chain for evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database operation failed")
    except Exception as e:
        logger.error(f"Unexpected error retrieving custody chain for evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during custody retrieval")



# ============================================================================
# Integrity Verification Endpoint
# ============================================================================

@app.post("/evidence/{evidence_id}/verify", response_model=VerificationResult, status_code=200)
async def verify_evidence(evidence_id: str):
    """
    Verify the integrity of stored evidence by recomputing its SHA-256 hash.
    
    Retrieves the original hash from the evidence record, recomputes the SHA-256
    hash of the stored file, and compares them. Returns PASS if hashes match
    (file is unmodified) or FAIL if they differ (potential tampering detected).
    
    Logs a chain of custody entry documenting the verification with its result.
    
    Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.9, 8.1, 8.2, 8.3, 8.4
    
    Args:
        evidence_id: Unique identifier (UUID) of the evidence record to verify
        
    Returns:
        200 OK: Verification result JSON containing:
                {status, original_hash, computed_hash, verification_timestamp}
                Status is "PASS" for unmodified files or "FAIL" for tampering detected
        
    Raises:
        404 Not Found: If evidence record does not exist
        500 Internal Server Error: If file is missing from storage or hash computation fails
    """
    try:
        conn = get_db_connection()
        
        # Call the verification function
        result = verify_evidence_integrity(conn, evidence_id)
        
        conn.close()
        
        logger.info(f"Evidence verification completed: {evidence_id}, result={result['status']}")
        return VerificationResult(**result)
        
    except EvidenceNotFoundError as e:
        # Evidence record not found -> 404
        error_msg = str(e)
        logger.warning(f"Verification evidence not found: {error_msg}")
        raise HTTPException(status_code=404, detail="Evidence record not found")
        
    except EvidenceFileNotFoundError as e:
        # Evidence file missing from storage -> 500
        error_msg = str(e)
        logger.error(f"Verification evidence file missing: {error_msg}")
        raise HTTPException(status_code=500, detail="Evidence file missing from storage")
        
    except HashTimeoutError as e:
        # Hash computation exceeded timeout -> 500
        error_msg = str(e)
        logger.error(f"Verification hash computation timeout: {error_msg}")
        raise HTTPException(status_code=500, detail="Verification timeout")
        
    except HashComputationError as e:
        # Hash computation error (file I/O, etc) -> 500
        error_msg = str(e)
        logger.error(f"Verification hash computation error: {error_msg}")
        raise HTTPException(status_code=500, detail="Hash computation error during verification")
        
    except OSError as e:
        # File I/O error
        logger.error(f"File I/O error during verification of evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="File read error during verification")
        
    except sqlite3.DatabaseError as e:
        # Database error
        logger.error(f"Database error during verification of evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred during verification")
        
    except sqlite3.Error as e:
        # SQLite error
        logger.error(f"SQLite error during verification of evidence {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database operation failed during verification")
        
    except Exception as e:
        # Unexpected error
        error_msg = str(e)
        logger.error(f"Unexpected error during verification of evidence {evidence_id}: {error_msg}")
        raise HTTPException(status_code=500, detail="Internal server error during verification")


# ============================================================================
# Authentication Engine Endpoints
# ============================================================================

from typing import Optional
from fastapi import Query, Request
from .authentication.analyzer import AuthenticationAnalyzer
from .authentication.schemas import AuthenticationResultResponse

# Initialize analyzer
_auth_analyzer = AuthenticationAnalyzer()


@app.post("/api/v1/evidence/{evidence_id}/authenticate", response_model=AuthenticationResultResponse, status_code=201)
async def authenticate_evidence(
    evidence_id: str,
    force_reanalysis: bool = Query(False, description="Skip cache and re-analyze"),
    actor_id: str = Query(None, description="Identifier of requesting actor"),
    request: Request = None
):
    """
    Analyze evidence file for authenticity.
    
    Performs authentication analysis on image or video files, generating signals
    for various authenticity checks (EXIF, headers, compression, codecs, etc).
    Returns HTTP 201 for new analysis or 200 for cached results.
    
    Query Parameters:
    - force_reanalysis: bool (default false) - Skip cache and re-analyze
    - actor_id: str (optional) - Identifier of requesting user/system
    
    Request Headers Used:
    - X-Forwarded-For or Remote-Addr: client_ip
    - User-Agent: user_agent string
    
    Requirements: 2.1-2.10, 7.1-7.10
    
    Returns:
    - 201: New analysis completed
    - 200: Cached analysis returned
    - 400: Unsupported file type
    - 404: Evidence not found
    - 408: Analysis timeout
    - 409: Analysis in progress
    - 413: File too large
    - 500: Processing error
    """
    try:
        # Capture request context
        client_ip = request.client.host if request and request.client else "unknown"
        user_agent = request.headers.get("user-agent", "") if request else ""
        request_context = {
            "client_ip": client_ip,
            "user_agent": user_agent
        }
        
        # Default actor_id if not provided
        if not actor_id:
            actor_id = "SYSTEM"
        
        # Perform authentication analysis
        result = _auth_analyzer.analyze_evidence(
            evidence_id=evidence_id,
            force_reanalysis=force_reanalysis,
            actor_id=actor_id,
            request_context=request_context
        )
        
        # Determine if this is a new analysis or cached result
        # For simplicity, always return 201 (this could be enhanced to track new vs cached)
        status_code = 201
        
        logger.info(f"Evidence authenticated: {evidence_id}, verdict={result['verdict']}, status={status_code}")
        
        # Convert result dict to response model
        return AuthenticationResultResponse(**result)
        
    except ValueError as e:
        # Validation error
        error_msg = str(e)
        logger.warning(f"Authentication validation error for {evidence_id}: {error_msg}")
        
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="Evidence not found")
        elif "unsupported file type" in error_msg.lower():
            raise HTTPException(status_code=400, detail="Unsupported file type for authentication analysis")
        elif "exceeds maximum size" in error_msg.lower():
            raise HTTPException(status_code=413, detail="File too large for authentication analysis (max 1 GB)")
        else:
            raise HTTPException(status_code=400, detail=error_msg)
    
    except OSError as e:
        # File access error
        error_msg = str(e)
        logger.error(f"File access error during authentication of {evidence_id}: {error_msg}")
        raise HTTPException(status_code=500, detail="Could not access evidence file")
    
    except RuntimeError as e:
        # Processing error
        error_msg = str(e)
        logger.error(f"Processing error during authentication of {evidence_id}: {error_msg}")
        raise HTTPException(status_code=500, detail="Authentication analysis failed")
    
    except Exception as e:
        # Unexpected error
        error_msg = str(e)
        logger.error(f"Unexpected error during authentication of {evidence_id}: {error_msg}")
        raise HTTPException(status_code=500, detail="Internal server error during authentication analysis")


@app.get("/api/v1/evidence/{evidence_id}/authentication", response_model=AuthenticationResultResponse, status_code=200)
async def get_authentication_result(evidence_id: str):
    """
    Retrieve authentication analysis result for evidence.
    
    Returns previously computed authentication analysis result if it exists.
    Results are cached for 24 hours.
    
    Requirements: 8.1-8.4
    
    Returns:
    - 200: Result found and returned
    - 404: No analysis results found
    - 500: Database error
    """
    try:
        from .authentication.storage import AuthenticationStorage
        
        storage = AuthenticationStorage()
        result = storage.get_result(evidence_id)
        
        if not result:
            logger.warning(f"No authentication results found for evidence {evidence_id}")
            raise HTTPException(status_code=404, detail="No authentication results found for this evidence")
        
        logger.info(f"Authentication result retrieved for evidence {evidence_id}")
        
        # Convert result object to response model
        result_dict = result.to_dict()
        return AuthenticationResultResponse(**result_dict)
        
    except HTTPException:
        raise
    except sqlite3.Error as e:
        logger.error(f"Database error retrieving authentication result for {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred")
    except Exception as e:
        logger.error(f"Unexpected error retrieving authentication result for {evidence_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during result retrieval")
