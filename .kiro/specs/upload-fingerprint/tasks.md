# Implementation Plan: Upload & Fingerprint Module

## Overview

This implementation plan provides a streamlined, hackathon-optimized task list for the Upload & Fingerprint module. The infrastructure layer (database, config, FastAPI app skeleton) is already complete. Remaining tasks focus on implementing core forensic functionality: hash computation, metadata extraction, upload workflow, retrieval endpoints, and integrity verification.

**Simplified Architecture:**
- Local filesystem storage (`./evidence_storage/`) - no cloud complexity
- SQLite database (zero-config) - already set up
- Extension-based MIME validation - simple and fast
- No deduplication - every upload gets unique UUID
- All core forensic features preserved: SHA-256, chain of custody, metadata extraction, verification

## Tasks

- [x] 1. Implement SHA-256 hashing and timestamp utilities
  - [x] 1.1 Create hash computation module
    - Implement `compute_sha256_hash(file_path: str, timeout: int = 300) -> str` in `src/forensix/hashing.py`
    - Use hashlib with streaming (8KB chunks) to handle large files efficiently
    - Handle timeout (300s max) and I/O errors with appropriate exceptions
    - Return 64-character hexadecimal hash string
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  
  - [ ]* 1.2 Write unit tests for hash computation
    - Test idempotence: same file hashed twice produces identical results
    - Test with known SHA-256 test vectors (e.g., empty file, small text file)
    - Test timeout handling
    - _Requirements: 2.4_
  
  - [x] 1.3 Create timestamp capture module
    - Implement `capture_timestamps(file_path: str) -> dict` in `src/forensix/timestamps.py`
    - Return dict with `upload_timestamp` (current UTC), `creation_timestamp` (st_ctime), `modification_timestamp` (st_mtime)
    - Format all timestamps in ISO 8601 with millisecond precision and UTC timezone
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 2. Implement metadata extraction modules
  - [x] 2.1 Create file metadata extraction function
    - Implement `extract_file_metadata(file: UploadFile, file_path: str) -> dict` in `src/forensix/metadata.py`
    - Extract: original_filename, file_size (bytes), file_extension (lowercase, no dot)
    - Use `get_mime_type_from_extension()` from config for MIME type
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  
  - [x] 2.2 Implement EXIF metadata extraction
    - Implement `extract_exif_metadata(file_path: str) -> dict` in `src/forensix/metadata.py`
    - Use Pillow (PIL) to extract GPS coordinates (lat/long), camera info (make, model), DateTimeOriginal
    - Return empty dict `{}` on any extraction failure (graceful degradation)
    - Only process image extensions: jpg, jpeg, png
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  
  - [x] 2.3 Implement video metadata extraction
    - Implement `extract_video_metadata(file_path: str) -> dict` in `src/forensix/metadata.py`
    - Use ffmpeg-python or pymediainfo to extract: duration, resolution (width/height), codec, creation_timestamp
    - Return empty dict `{}` on any extraction failure (graceful degradation)
    - Only process video extensions: mp4, mov, avi
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  
  - [ ]* 2.4 Write unit tests for metadata extraction
    - Test EXIF extraction with sample images (with/without GPS, camera info)
    - Test video extraction with sample videos
    - Test graceful failure with corrupted or metadata-free files
    - _Requirements: 5.5, 6.6_

- [x] 3. Checkpoint - Core utilities complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement chain of custody logging
  - [x] 4.1 Create chain of custody logging module
    - Implement `create_chain_of_custody_entry(conn: sqlite3.Connection, evidence_id: str, action_type: str, notes: str = None)` in `src/forensix/custody.py`
    - Capture timestamp in ISO 8601 with millisecond precision (UTC)
    - INSERT into `custody_entries` table with action_type (UPLOAD, ACCESS, VERIFY)
    - Use non-blocking error handling: catch all exceptions, log errors, but never raise (custody failures don't block operations)
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.8_
  
  - [ ]* 4.2 Write unit tests for custody logging
    - Test successful entry creation for UPLOAD, ACCESS, VERIFY actions
    - Test non-blocking behavior: simulate database error, verify no exception raised
    - _Requirements: 11.8_

- [x] 5. Implement input validation and upload orchestration
  - [x] 5.1 Create input validation module
    - Implement validation functions in `src/forensix/validation.py`:
      - `validate_file_size(file_size: int)`: reject if 0 bytes (ValueError: "File size must be greater than 0 bytes") or >500MB (ValueError: "File size exceeds maximum limit of 500 MB")
      - `validate_file_extension(filename: str)`: extract extension, check against ALLOWED_EXTENSIONS, raise ValueError with supported formats message if invalid
      - `validate_required_params(uploader_id: str, collection_method: str)`: raise ValueError("Uploader_ID and Collection_Method are required") if missing
    - _Requirements: 1.5, 1.6, 1.7, 1.8_
  
  - [x] 5.2 Implement main upload orchestration function
    - Implement `upload_evidence_handler(file: UploadFile, uploader_id: str, collection_method: str) -> dict` in `src/forensix/upload_handler.py`
    - Workflow:
      1. Validate inputs (size, extension, required params)
      2. Generate UUID4 for evidence ID (no deduplication)
      3. Save temp file, compute SHA-256 hash
      4. Extract file metadata, EXIF/video metadata, timestamps
      5. Move file to `./evidence_storage/{uuid}.{ext}`
      6. Open SQLite transaction: INSERT evidence_record, log custody entry (UPLOAD), commit
      7. Return dict: {id, sha256_hash, upload_timestamp, original_filename, file_size}
    - Implement atomic rollback: on any error, delete file from evidence_storage, rollback transaction
    - _Requirements: 1.9, 1.10, 1.11, 7.8, 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [ ]* 5.3 Write integration tests for upload handler
    - Test successful upload end-to-end (file in ./evidence_storage/, record in DB)
    - Test atomic rollback on database failure
    - Test all validation error paths
    - _Requirements: 8.5_

- [x] 6. Implement FastAPI upload endpoints
  - [x] 6.1 Create POST /evidence/upload endpoint
    - Define Pydantic models: `EvidenceUploadResponse(id, sha256_hash, upload_timestamp, original_filename, file_size)`
    - Accept Form parameters: file (UploadFile), uploader_id (str), collection_method (str)
    - Call `upload_evidence_handler()`, return HTTP 201 with response model
    - Map exceptions: ValueError → 400, file size errors → 413, others → 500
    - Add endpoint to `src/forensix/app.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.11, 7.8_
  
  - [x] 6.2 Create POST /evidence/upload/batch endpoint
    - Accept multiple files (Form: files, uploader_id, collection_method)
    - Validate max 100 files and 2GB combined size (reject with 413 if exceeded)
    - Process each file independently using `upload_evidence_handler()`
    - Continue processing remaining files even if one fails
    - Return HTTP 207 (Multi-Status) with array: [{original_filename, id, sha256_hash, status, error}, ...]
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [ ]* 6.3 Write API tests for upload endpoints
    - Test successful single upload (201 response)
    - Test batch upload with mixed success/failure (207 response)
    - Test validation errors (400, 413)
    - _Requirements: 1.5, 1.6, 1.7, 1.8, 10.4_

- [x] 7. Checkpoint - Upload functionality complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement evidence retrieval endpoints
  - [~] 8.1 Create GET /evidence/{id} endpoint
    - Query `evidence_records` table by id
    - Log chain of custody entry: action_type="ACCESS"
    - Return HTTP 200 with complete evidence record JSON (all fields)
    - Return HTTP 404 with message "Evidence record not found" if id not found
    - Add endpoint to `src/forensix/app.py`
    - _Requirements: 9.1, 9.2, 9.3, 9.7, 11.3_
  
  - [~] 8.2 Create GET /evidence/{id}/file endpoint
    - Query database to get file_extension and mime_type for given id
    - Construct file path: `./evidence_storage/{id}.{ext}`
    - Log chain of custody entry: action_type="ACCESS"
    - Return HTTP 200 with file content and Content-Type header
    - Return HTTP 404 with message "Evidence file not found" if file doesn't exist
    - _Requirements: 9.4, 9.5, 9.6, 9.7_
  
  - [ ]* 8.3 Write API tests for retrieval endpoints
    - Test successful record retrieval (200)
    - Test successful file download with correct Content-Type
    - Test 404 for invalid IDs
    - Verify custody logging on access
    - _Requirements: 9.3, 9.6, 9.7_

- [ ] 9. Implement chain of custody retrieval endpoint
  - [~] 9.1 Create GET /evidence/{id}/custody endpoint
    - Query all custody entries WHERE evidence_id = {id} from `custody_entries` table
    - Sort by timestamp ascending
    - Return HTTP 200 with JSON array: [{id, evidence_id, action_type, timestamp, notes}, ...]
    - Return HTTP 404 with message "Evidence record not found" if evidence_id doesn't exist
    - Add endpoint to `src/forensix/app.py`
    - _Requirements: 11.5, 11.6, 11.7_
  
  - [ ]* 9.2 Write API tests for custody endpoint
    - Test retrieval with multiple custody entries (UPLOAD, ACCESS, VERIFY)
    - Verify timestamp ascending order
    - _Requirements: 11.6, 11.7_

- [x] 10. Implement integrity verification
  - [x] 10.1 Create integrity verification module
    - Implement `verify_evidence_integrity(evidence_id: str) -> dict` in `src/forensix/verification.py`
    - Retrieve original sha256_hash from evidence_records WHERE id = evidence_id
    - Retrieve file from `./evidence_storage/{evidence_id}.{ext}` and compute new SHA-256 hash
    - Compare hashes: match → status="PASS", mismatch → status="FAIL"
    - Log chain of custody entry: action_type="VERIFY", notes=f"Result: {status}"
    - Return dict: {status, original_hash, computed_hash, verification_timestamp}
    - Raise ValueError("Evidence record not found") if id doesn't exist
    - Raise FileNotFoundError("Evidence file missing from storage") if file not found
    - _Requirements: 12.2, 12.3, 12.4, 12.5, 12.6, 12.8, 12.9_
  
  - [x] 10.2 Create POST /evidence/{id}/verify endpoint
    - Call `verify_evidence_integrity(evidence_id)`
    - Return HTTP 200 with verification result JSON (for both PASS and FAIL)
    - Return HTTP 404 if ValueError raised
    - Return HTTP 500 if FileNotFoundError or computation error
    - Add endpoint to `src/forensix/app.py`
    - _Requirements: 12.1, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10_
  
  - [ ]* 10.3 Write API tests for verification
    - Test successful verification with PASS result (unmodified file)
    - Test FAIL result by manually corrupting file in ./evidence_storage/
    - Verify custody logging for VERIFY action
    - _Requirements: 12.5, 12.6, 12.9_

- [x] 11. Implement error handling and logging
  - [x] 11.1 Add structured error logging
    - Add Python logging configuration in `src/forensix/app.py` (log to console and file)
    - Log all errors with timestamp, evidence_id (where applicable), and error details
    - Ensure consistent error message format across all endpoints
    - _Requirements: 8.4_
  
  - [x] 11.2 Add comprehensive error handling
    - Wrap all database operations in try-except blocks
    - Handle SQLite errors gracefully (return HTTP 500 with descriptive message)
    - Handle disk space exhaustion (catch OSError during file write, return HTTP 500)
    - Add error handling to all endpoints
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 12. Final checkpoint and end-to-end validation
  - Ensure all tests pass, ask the user if questions arise.
  - Verify complete workflow: upload → file stored in ./evidence_storage/ → database record created → retrieval works → verification works → custody log accurate
  - Test atomic rollback: simulate database failure, confirm file is cleaned up
  - Verify chain of custody logging for all actions: UPLOAD, ACCESS, VERIFY

## Notes

- **Infrastructure Already Complete:**
  - SQLite database schema (`evidence_records`, `custody_entries` tables) ✓
  - Database initialization script (`database_setup.py`) ✓
  - Configuration constants (`src/forensix/config.py`) ✓
  - FastAPI app skeleton with health check (`src/forensix/app.py`) ✓
  - Evidence storage directory (`./evidence_storage/`) ✓

- **Hackathon Simplifications:**
  - Local filesystem storage (no S3, no cloud SDKs)
  - SQLite (no PostgreSQL setup needed)
  - Extension-based MIME detection (no magic-byte libraries)
  - No deduplication logic (simpler, faster)

- **Core Forensic Features Preserved:**
  - SHA-256 cryptographic hashing (streaming for large files)
  - Chain of custody logging (UPLOAD, ACCESS, VERIFY) with millisecond timestamps
  - EXIF metadata extraction (GPS, camera, timestamps)
  - Video metadata extraction (duration, resolution, codec)
  - Integrity verification (re-hash and compare)
  - Atomic rollback (file cleanup + database transaction)

- **Testing:**
  - Tasks marked with `*` are optional test tasks (can skip for faster MVP)
  - Unit tests for core utilities (hashing, timestamps, metadata extraction)
  - Integration tests for upload workflow and endpoints
  - API tests for all endpoints (upload, retrieval, custody, verification)

- **Python Implementation:**
  - FastAPI for REST API
  - sqlite3 (stdlib) for database
  - Pillow for EXIF extraction
  - ffmpeg-python or pymediainfo for video metadata
  - hashlib (stdlib) for SHA-256

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "4.1"] },
    { "id": 4, "tasks": ["4.2", "5.1"] },
    { "id": 5, "tasks": ["5.2"] },
    { "id": 6, "tasks": ["5.3", "6.1"] },
    { "id": 7, "tasks": ["6.2"] },
    { "id": 8, "tasks": ["6.3", "8.1", "8.2"] },
    { "id": 9, "tasks": ["8.3", "9.1"] },
    { "id": 10, "tasks": ["9.2", "10.1"] },
    { "id": 11, "tasks": ["10.2"] },
    { "id": 12, "tasks": ["10.3", "11.1"] },
    { "id": 13, "tasks": ["11.2"] }
  ]
}
```
