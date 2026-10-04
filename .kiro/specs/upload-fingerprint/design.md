# Design Document

## Overview

The Upload & Fingerprint module is the foundational component of ForensiX, providing cryptographic fingerprinting, metadata extraction, and chain of custody logging for digital evidence files. This module accepts evidence uploads via HTTP API, computes SHA-256 hashes for integrity verification, extracts file system and embedded metadata (EXIF, video), and maintains a comprehensive audit trail.

### Design Philosophy: Hackathon-Optimized Architecture

This design is **optimized for rapid hackathon development** with the following simplifications:
- **Local filesystem storage** (`./evidence_storage/`) instead of cloud storage (S3)
- **SQLite** instead of PostgreSQL for zero-configuration setup
- **No deduplication logic** - every upload creates a new record with unique UUID
- **Extension-based MIME validation** instead of magic-byte sniffing
- **No file permissions complexity** - rely on filesystem defaults

Core forensic features are preserved: SHA-256 hashing, chain of custody, metadata extraction, and integrity verification.

## Architecture

### System Architecture

The Upload & Fingerprint module follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI REST Layer                      │
│  (Upload, Retrieval, Verification, Custody endpoints)       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Service Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ Upload       │  │ Fingerprint  │  │ Integrity       │  │
│  │ Handler      │  │ Generator    │  │ Verifier        │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ Metadata     │  │ Timestamp    │  │ Chain of        │  │
│  │ Extractor    │  │ Recorder     │  │ Custody Logger  │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Persistence Layer                          │
│  ┌─────────────────────────┐  ┌──────────────────────────┐ │
│  │   SQLite Database       │  │   Local File Storage     │ │
│  │   - evidence_records    │  │   ./evidence_storage/    │ │
│  │   - custody_entries     │  │   {uuid}.{ext}           │ │
│  └─────────────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

#### Upload Flow
```
Client → POST /evidence/upload
    ↓
[Validate request: size, extension, Uploader_ID, Collection_Method]
    ↓
[Generate UUID - no dedup check, every upload is unique]
    ↓
[Compute SHA-256 hash]
    ↓
[Extract metadata: file system, EXIF/video]
    ↓
[Capture timestamps: upload, creation, modification]
    ↓
[Write file to ./evidence_storage/{uuid}.{ext}]
    ↓
[INSERT into evidence_records table (SQLite)]
    ↓
[INSERT into custody_entries: action=UPLOAD]
    ↓
Client ← HTTP 201 {id, sha256, upload_timestamp}
```

#### Retrieval Flow
```
Client → GET /evidence/{id}
    ↓
[SELECT from evidence_records WHERE id = {id}]
    ↓
[INSERT into custody_entries: action=ACCESS]
    ↓
Client ← HTTP 200 {evidence_record JSON}
```

#### Verification Flow
```
Client → POST /evidence/{id}/verify
    ↓
[SELECT sha256 from evidence_records WHERE id = {id}]
    ↓
[Read file from ./evidence_storage/{id}.*]
    ↓
[Compute new SHA-256 hash]
    ↓
[Compare: new_hash == original_hash]
    ↓
[INSERT into custody_entries: action=VERIFY, notes=PASS/FAIL]
    ↓
Client ← HTTP 200 {status, original_hash, computed_hash, timestamp}
```

## Components and Interfaces

### Component Descriptions

#### 1. FastAPI REST Layer
- **Responsibility**: HTTP request/response handling, input validation, route definition
- **Technology**: FastAPI with Pydantic models for request/response validation
- **Error Handling**: Returns appropriate HTTP status codes (200, 201, 400, 404, 413, 500, 207)

#### 2. Upload Handler
- **Responsibility**: Orchestrates the complete upload workflow
- **Workflow**:
  1. Validate file size, extension, and required parameters
  2. Generate unique identifier (UUID4) - **every upload gets new UUID, no deduplication**
  3. Invoke Fingerprint Generator
  4. Invoke Metadata Extractor
  5. Invoke Timestamp Recorder
  6. Persist file to local storage (`./evidence_storage/{uuid}.{ext}`)
  7. Create Evidence Record in SQLite database
  8. Log Chain of Custody entry
  9. Return response or rollback on error

#### 3. Fingerprint Generator
- **Responsibility**: Compute SHA-256 hash of file contents
- **Algorithm**: Stream-based hashing (8KB chunks) to handle large files
- **Library**: Python hashlib
- **Timeout**: 300 seconds maximum

#### 4. Metadata Extractor
- **Responsibility**: Extract file system metadata and embedded metadata
- **Components**:
  - **File System Extractor**: filename, size, MIME type (via extension mapping), extension
  - **EXIF Extractor**: GPS, camera info, timestamps (for images)
  - **Video Metadata Extractor**: duration, resolution, codec (for videos)
- **Libraries**:
  - Pillow (PIL) for EXIF data
  - ffmpeg-python or pymediainfo for video metadata
- **MIME Type Detection**: Extension-based lookup (e.g., `.jpg` → `image/jpeg`)
  - **Future Enhancement**: Magic-byte sniffing with `python-magic` for robust validation (not required for hackathon)
- **Error Handling**: Return empty metadata object on extraction failure, continue processing

#### 5. Timestamp Recorder
- **Responsibility**: Capture upload, creation, and modification timestamps
- **Format**: ISO 8601 with timezone offset (UTC)
- **Precision**: Milliseconds
- **Source**: System clock (NTP-synchronized when available)

#### 6. Chain of Custody Logger
- **Responsibility**: Create audit trail entries for all evidence interactions
- **Action Types**: UPLOAD, ACCESS, VERIFY
- **Storage**: custody_entries table in SQLite
- **Non-blocking**: Failures logged but don't halt primary operations

#### 7. Integrity Verifier
- **Responsibility**: Re-hash stored files and compare against original hash
- **Workflow**:
  1. Retrieve original hash from evidence_records
  2. Retrieve file from storage
  3. Compute new SHA-256 hash
  4. Compare hashes
  5. Log Chain of Custody entry
  6. Return PASS/FAIL result

### API Endpoints

#### 1. Upload Evidence File
```
POST /evidence/upload
Content-Type: multipart/form-data

Request:
- file: binary (required)
- uploader_id: string (required)
- collection_method: string (required)

Response (201 Created):
{
  "id": "uuid",
  "sha256_hash": "hex_string",
  "upload_timestamp": "ISO8601",
  "original_filename": "string",
  "file_size": integer
}

Errors:
- 400: Invalid input (missing fields, unsupported format, 0 bytes)
- 413: File too large (>500 MB)
- 500: Processing error
```

#### 2. Batch Upload
```
POST /evidence/upload/batch
Content-Type: multipart/form-data

Request:
- files: array of binaries (max 100, max 2GB combined)
- uploader_id: string (required)
- collection_method: string (required)

Response (200/207/400):
{
  "results": [
    {
      "original_filename": "string",
      "id": "uuid",
      "sha256_hash": "hex_string",
      "status": 201,
      "error": null
    },
    {
      "original_filename": "string",
      "status": 400,
      "error": "Error message"
    }
  ]
}

Status Codes:
- 200: All succeeded
- 207: Partial success
- 400: All failed
- 413: Too many files or total size exceeded
```

#### 3. Get Evidence Record
```
GET /evidence/{id}

Response (200):
{
  "id": "uuid",
  "original_filename": "string",
  "file_size": integer,
  "mime_type": "string",
  "file_extension": "string",
  "sha256_hash": "hex_string",
  "uploader_id": "string",
  "collection_method": "string",
  "upload_timestamp": "ISO8601",
  "creation_timestamp": "ISO8601 or null",
  "modification_timestamp": "ISO8601 or null",
  "extracted_metadata": {object or null}
}

Errors:
- 404: Evidence not found
```

#### 4. Download Evidence File
```
GET /evidence/{id}/file

Response (200):
- Content-Type: {mime_type}
- Body: binary file content

Errors:
- 404: Evidence file not found
```

#### 5. Get Chain of Custody
```
GET /evidence/{id}/custody

Response (200):
[
  {
    "id": integer,
    "evidence_id": "uuid",
    "action_type": "UPLOAD|ACCESS|VERIFY",
    "timestamp": "ISO8601",
    "notes": "string or null"
  }
]

Errors:
- 404: Evidence not found
```

#### 6. Verify Integrity
```
POST /evidence/{id}/verify

Response (200):
{
  "status": "PASS|FAIL",
  "original_hash": "hex_string",
  "computed_hash": "hex_string",
  "verification_timestamp": "ISO8601"
}

Errors:
- 404: Evidence not found
- 500: File missing from storage or computation error
```

## Data Models

### Database Schema

**Database**: SQLite 3 (file-based, zero configuration)  
**Database File**: `./forensix.db`

#### evidence_records table
```sql
CREATE TABLE evidence_records (
    id TEXT PRIMARY KEY,                      -- UUID4 (every upload unique, no dedup)
    original_filename TEXT NOT NULL,          -- Max 255 chars
    file_size INTEGER NOT NULL,               -- Bytes
    mime_type TEXT NOT NULL,                  -- Max 100 chars (extension-based)
    file_extension TEXT NOT NULL,             -- Max 10 chars
    sha256_hash TEXT NOT NULL,                -- 64-char hex string
    uploader_id TEXT NOT NULL,                -- Max 100 chars
    collection_method TEXT NOT NULL,          -- Max 1000 chars
    upload_timestamp TEXT NOT NULL,           -- ISO 8601 UTC
    creation_timestamp TEXT,                  -- ISO 8601 UTC, nullable
    modification_timestamp TEXT,              -- ISO 8601 UTC, nullable
    extracted_metadata TEXT,                  -- JSON, max 1 MB, nullable
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sha256 ON evidence_records(sha256_hash);
CREATE INDEX idx_uploader ON evidence_records(uploader_id);
CREATE INDEX idx_upload_timestamp ON evidence_records(upload_timestamp);
```

#### custody_entries table
```sql
CREATE TABLE custody_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT NOT NULL,                -- FK to evidence_records.id
    action_type TEXT NOT NULL,                -- UPLOAD, ACCESS, VERIFY
    timestamp TEXT NOT NULL,                  -- ISO 8601 UTC with ms
    notes TEXT,                               -- Optional context
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evidence_id) REFERENCES evidence_records(id) ON DELETE CASCADE
);

CREATE INDEX idx_evidence_id ON custody_entries(evidence_id);
CREATE INDEX idx_action_type ON custody_entries(action_type);
CREATE INDEX idx_timestamp ON custody_entries(timestamp);
```

### Python Data Models

#### EvidenceUploadRequest (Pydantic Model)
```python
from pydantic import BaseModel, Field
from fastapi import UploadFile

class EvidenceUploadRequest(BaseModel):
    file: UploadFile
    uploader_id: str = Field(..., max_length=100)
    collection_method: str = Field(..., max_length=1000)
```

#### EvidenceRecord (Data Model)
```python
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class EvidenceRecord:
    id: str
    original_filename: str
    file_size: int
    mime_type: str
    file_extension: str
    sha256_hash: str
    uploader_id: str
    collection_method: str
    upload_timestamp: str
    creation_timestamp: Optional[str]
    modification_timestamp: Optional[str]
    extracted_metadata: Optional[Dict[str, Any]]
```

#### ChainOfCustodyEntry (Data Model)
```python
@dataclass
class ChainOfCustodyEntry:
    id: int
    evidence_id: str
    action_type: str  # UPLOAD, ACCESS, VERIFY
    timestamp: str
    notes: Optional[str]
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Required Parameter Validation

*For any* upload request missing required parameters (Uploader_ID or Collection_Method), the system SHALL reject the request with HTTP 400 error.

**Validates: Requirements 1.2, 1.3, 1.8**

### Property 2: File Extension Whitelist Enforcement

*For any* file with an allowed extension (jpg, jpeg, png, gif, bmp, mp4, mov, avi, txt, log, json, csv), the upload SHALL be accepted (subject to other validations), and *for any* file with a disallowed extension, the upload SHALL be rejected with HTTP 400 error.

**Validates: Requirements 1.4, 1.7**

### Property 3: File Size Boundary Validation

*For any* file with size greater than 500 MB, the upload SHALL be rejected with HTTP 413 error, and *for any* file with size 0 bytes, the upload SHALL be rejected with HTTP 400 error.

**Validates: Requirements 1.5, 1.6**

### Property 4: Unique Identifier Assignment

*For any* set of successful uploads, all assigned evidence identifiers SHALL be unique (no duplicates).

**Validates: Requirement 1.9**

### Property 5: Upload Response Completeness

*For any* successful upload, the HTTP 201 response SHALL contain the unique identifier, SHA-256 hash, upload timestamp, original filename, and file size.

**Validates: Requirements 1.11, 7.8**

### Property 6: Hash Computation Idempotence

*For any* evidence file, computing the SHA-256 hash multiple times SHALL always produce identical results.

**Validates: Requirement 2.4**

### Property 7: Hash Format Validity

*For any* uploaded file, the stored SHA-256 hash SHALL be a valid 64-character hexadecimal string.

**Validates: Requirements 2.1, 2.3**

### Property 8: Timestamp Format Compliance

*For any* successful upload, all timestamps (upload, creation, modification) SHALL be in valid ISO 8601 format with UTC timezone and millisecond precision.

**Validates: Requirements 3.1, 3.4**

### Property 9: File Metadata Completeness

*For any* uploaded file, the evidence record SHALL contain original filename, file size, MIME type, and file extension fields populated with accurate values matching the uploaded file.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

### Property 10: EXIF Extraction Non-Blocking

*For any* image file (jpg, jpeg, png), EXIF extraction failure SHALL NOT prevent upload completion; the system SHALL store empty metadata and continue processing.

**Validates: Requirement 5.5**

### Property 11: Video Metadata Extraction Non-Blocking

*For any* video file (mp4, mov, avi), video metadata extraction failure SHALL NOT prevent upload completion; the system SHALL store empty metadata and continue processing.

**Validates: Requirement 6.6**

### Property 12: Metadata JSON Format

*For any* file with extracted metadata (EXIF or video), the stored metadata SHALL be valid JSON format.

**Validates: Requirements 5.6, 6.7**

### Property 13: Evidence Record Persistence Completeness

*For any* successful upload, the created evidence record SHALL contain all required fields: ID, original filename, file size, MIME type, file extension, SHA-256 hash, uploader ID, collection method, upload timestamp, and extracted metadata (or null).

**Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.6, 7.7**

### Property 14: Upload-Retrieve Round Trip

*For any* uploaded evidence file, retrieving the evidence record by ID SHALL return an evidence record with metadata matching the original upload (filename, size, hash, timestamps, uploader info).

**Validates: Requirements 9.1, 9.2**

### Property 15: File Storage Round Trip

*For any* uploaded evidence file, downloading the file by ID SHALL return content with identical SHA-256 hash to the original upload.

**Validates: Requirements 9.4, 9.5**

### Property 16: Chain of Custody Logging on Access

*For any* successful evidence record retrieval or file download, a chain of custody entry with action type "ACCESS" SHALL be created with the evidence ID and timestamp.

**Validates: Requirements 9.7, 11.3**

### Property 17: Batch Upload Independence

*For any* batch upload containing both valid and invalid files, all valid files SHALL be processed successfully regardless of invalid files failing, and the response SHALL indicate individual status for each file.

**Validates: Requirements 10.2, 10.3, 10.4, 10.5**

### Property 18: Chain of Custody Entry Creation

*For any* upload, access, or verification action, a corresponding chain of custody entry SHALL be created with the appropriate action type (UPLOAD, ACCESS, VERIFY), evidence ID, and timestamp.

**Validates: Requirements 11.1, 11.2, 11.3, 11.4**

### Property 19: Chain of Custody Retrieval Completeness

*For any* evidence ID with logged actions, the GET /evidence/{id}/custody endpoint SHALL return all chain of custody entries for that evidence, sorted by timestamp in ascending order.

**Validates: Requirements 11.5, 11.6**

### Property 20: Integrity Verification Round Trip

*For any* unmodified evidence file stored in the system, integrity verification SHALL return status "PASS" with computed hash matching the original hash.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

### Property 21: Integrity Verification Detects Tampering

*For any* evidence file that has been modified after upload, integrity verification SHALL return status "FAIL" with computed hash differing from the original hash.

**Validates: Requirements 12.4, 12.6**

### Property 22: Verification Custody Logging

*For any* integrity verification (PASS or FAIL), a chain of custody entry with action type "VERIFY" and verification result SHALL be created.

**Validates: Requirements 11.4, 12.9**

## Error Handling

### Atomic Operations

All database operations use transactions with automatic rollback on failure:
```python
try:
    # 1. Store file
    # 2. Insert evidence_record
    # 3. Insert custody_entry
    db_conn.commit()
except Exception:
    db_conn.rollback()
    # Clean up stored file
    raise
```

### Non-Blocking Custody Logging

Chain of custody logging failures are logged but don't block primary operations:
```python
try:
    create_chain_of_custody_entry(...)
except Exception as e:
    logger.error(f"Custody logging failed: {e}")
    # Continue - don't raise
```

### Graceful Metadata Extraction Failures

EXIF/video extraction failures return empty dicts and continue:
```python
try:
    metadata = extract_exif_metadata(path)
except Exception:
    metadata = {}  # Store empty, continue processing
```

### Error Response Codes

The system uses standard HTTP status codes for error conditions:

- **HTTP 400 (Bad Request)**: Invalid input (missing required fields, unsupported format, 0-byte files)
- **HTTP 404 (Not Found)**: Evidence record or file not found
- **HTTP 413 (Payload Too Large)**: File exceeds size limits (500 MB for single, 2 GB for batch, 10 GB for hashing)
- **HTTP 500 (Internal Server Error)**: Processing errors (storage failure, hash timeout, database errors)
- **HTTP 207 (Multi-Status)**: Batch operations with partial success

## Testing Strategy

### Dual Testing Approach

This module uses **both unit tests and property-based tests** for comprehensive coverage:

- **Unit tests**: Verify specific examples, edge cases, and error conditions
- **Property-based tests**: Verify universal properties across randomized inputs (minimum 100 iterations per property)

Each property test references its corresponding design document property using the tag format:
**Feature: upload-fingerprint, Property {number}: {property_text}**

### Property-Based Testing

**Library**: Use a standard property-based testing library for the target language:
- Python: **Hypothesis** (recommended)
- JavaScript/TypeScript: fast-check
- Java: jqwik
- Scala: ScalaCheck

**Configuration**:
- Minimum 100 iterations per property test
- Each test must reference its design property in comments/tags
- Use appropriate generators for file extensions, sizes, strings, etc.

**Property Test Coverage**:
- Required parameter validation (Property 1)
- File extension and size validation (Properties 2, 3)
- Unique identifier assignment (Property 4)
- Hash computation idempotence (Property 6)
- Round-trip properties: upload-retrieve, upload-download, integrity verification (Properties 14, 15, 20)
- Chain of custody logging (Properties 16, 18, 19, 22)
- Batch operation independence (Property 17)
- Metadata extraction error handling (Properties 10, 11)

### Unit Tests

Unit tests cover specific scenarios and integration points:

- Hash computation accuracy with known test vectors (e.g., SHA-256 of empty file)
- EXIF extraction with sample images containing GPS coordinates, camera info, timestamps
- Video metadata extraction with sample videos of various codecs and resolutions
- Timestamp formatting and UTC conversion edge cases
- Database CRUD operations (insert, select, update, delete)
- API endpoint error responses (400, 404, 413, 500) with specific payloads
- Specific edge cases: 0-byte files, files at exact size limits (500 MB), missing metadata

### Integration Tests

Integration tests verify end-to-end workflows:

- Complete upload flow from HTTP request to database persistence and file storage
- Batch upload with mixed success/failure scenarios (some valid, some invalid files)
- Evidence retrieval with custody logging verification
- Integrity verification PASS/FAIL scenarios (unmodified vs. modified files)
- Error rollback atomicity (database failure triggers file cleanup)
- Chain of custody timeline accuracy and ordering

### Edge Cases

Edge cases to explicitly test:

- Zero-byte files (should reject with 400)
- Files at exact size limits (500 MB for upload, 2 GB for batch)
- Files just under and just over size limits
- Missing EXIF/video metadata in otherwise valid files
- Corrupted image/video files that fail metadata extraction
- Files with unusual but valid extensions (e.g., uppercase .JPG)
- Concurrent uploads to the same system
- Database connection failures during upload
- Disk space exhaustion during file write

