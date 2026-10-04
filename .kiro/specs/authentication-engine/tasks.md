# Implementation Plan: Authentication Engine Module

## Overview

This implementation plan provides a structured task list for building the Authentication Engine module as an extension to the existing Upload & Fingerprint module. The Authentication Engine adds intelligent authenticity verification without modifying existing tables or endpoints.

**Key Principles**:
- Extends existing Upload & Fingerprint infrastructure (no table duplication)
- Implements signal-based authenticity analysis for images and videos
- Integrates with existing chain of custody logging
- Uses caching to optimize repeated analyses
- Provides clear error handling and descriptive verdicts

## Tasks

### 1. Database Schema Extension

- [x] 1.1 Create authentication_results table migration
  - Create `authentication_results` table in SQLite with schema from design doc
  - Columns: id, evidence_id (FK, UNIQUE), confidence_score, verdict, signals_detected (JSON), explanation, analyzed_at, analyzer_version, created_at, updated_at
  - Create indexes on: evidence_id, verdict, analyzed_at, confidence_score
  - Create migration script that adds table to existing forensix.db
  - _Requirements: 1.1, 1.2_

- [~] 1.2 Verify schema compatibility with existing tables
  - Verify foreign key references work correctly
  - Test cascading deletes
  - Verify indexes created successfully
  - _Requirements: 1.1_

### 2. Authentication Analyzer Core

- [x] 2.1 Implement AuthenticationAnalyzer class
  - Create `src/forensix/authentication/analyzer.py`
  - Implement main orchestrator: `analyze_evidence(evidence_id, force_reanalysis, actor_id, request_context)`
  - Handle evidence record retrieval and validation
  - Route to Image or Video analyzer based on mime_type
  - Cache result checking (return existing if force_reanalysis=false)
  - Store results in database
  - Log chain of custody event
  - _Requirements: 2.1, 2.2, 9.1, 6.1_

- [x] 2.2 Implement configuration and constants
  - Add constants in config.py: AUTHENTICATION_TIMEOUT (5 min), MAX_AUTH_FILE_SIZE (1 GB), ANALYZER_VERSION
  - Define supported mime types for authentication (image/*, video/*)
  - Implement analyzer version string format
  - _Requirements: 10.1, 10.3_

### 3. Image Authentication Analyzer

- [~] 3.1 Implement image signal generators
  - Create `src/forensix/authentication/image_analyzer.py`
  - Implement EXIF metadata validation signal
    - Check EXIF presence (EXIF_COMPLETE vs EXIF_MISSING)
    - Verify DateTimeOriginal consistency with file modification time
    - Check GPS coordinate plausibility
  - Implement image header validation signal
    - Validate JPEG/PNG/GIF magic numbers
    - Check dimensions and size indicators
  - Implement thumbnail analysis signal (JPEG only)
  - Implement color space analysis signal
  - Implement compression artifacts detection signal (JPEG)
  - _Requirements: 3.1-3.8, 5.1_

- [~] 3.2 Implement image analyzer aggregation
  - Collect all signals from image checks
  - Combine into signals_detected JSON array
  - Compute weighted confidence score from signals
  - Determine verdict based on score and signal severity
  - Generate human-readable explanation
  - _Requirements: 3.8, 5.1-5.4_

### 4. Video Authentication Analyzer

- [~] 4.1 Implement video signal generators
  - Create `src/forensix/authentication/video_analyzer.py`
  - Implement container integrity signal (MP4/MOV/AVI validation)
  - Implement codec consistency signal (declared vs actual codec)
  - Implement frame metadata consistency signal (frame count, frame rate)
  - Implement timestamp consistency signal
  - Implement audio stream integrity signal (if audio present)
  - Implement file size vs metadata signal
  - _Requirements: 4.1-4.7, 5.1_

- [~] 4.2 Implement video analyzer aggregation
  - Collect all signals from video checks
  - Combine into signals_detected JSON array
  - Compute weighted confidence score from signals
  - Determine verdict based on score and signal severity
  - Generate human-readable explanation
  - _Requirements: 4.8, 5.1-5.4_

### 5. Signal and Result Models

- [~] 5.1 Implement Signal data model
  - Create `src/forensix/authentication/models.py`
  - Implement Signal dataclass with: signal_name, category, severity, score, message, details
  - Implement validation: score in [0,100], severity in [INFO, WARNING, CRITICAL]
  - Implement JSON serialization for database storage
  - _Requirements: 5.1, 5.2_

- [~] 5.2 Implement AuthenticationResult data model
  - Implement AuthenticationResult dataclass matching database schema
  - Implement Pydantic response model for API
  - Add validation: confidence_score in [0,100], verdict in [AUTHENTIC, SUSPICIOUS, TAMPERED]
  - Implement JSON serialization/deserialization
  - _Requirements: 1.1, 5.1_

### 6. Signal Aggregation and Verdict Logic

- [~] 6.1 Implement SignalAggregator
  - Create `src/forensix/authentication/aggregator.py`
  - Implement weighted averaging algorithm
    - CRITICAL signals: 40% weight
    - WARNING signals: 30% weight
    - INFO signals: 10% weight
  - Calculate final confidence_score (0-100)
  - Implement verdict logic:
    - AUTHENTIC: confidence >= 85 AND no CRITICAL signals
    - SUSPICIOUS: confidence 50-84 OR some WARNING signals
    - TAMPERED: confidence < 50 OR CRITICAL signals present
  - _Requirements: 5.2, 5.3_

- [~] 6.2 Implement explanation generator
  - Generate human-readable summary of analysis results
  - Highlight most significant signals
  - Explain detected anomalies
  - Provide investigator recommendations
  - Max 5000 characters
  - _Requirements: 5.4_

### 7. API Endpoints

- [~] 7.1 Implement POST /api/v1/evidence/{evidence_id}/authenticate endpoint
  - Accept evidence_id as path parameter
  - Accept query parameters: force_reanalysis (boolean), actor_id (string)
  - Validate evidence exists (404 if not)
  - Validate file type (400 if unsupported)
  - Call AuthenticationAnalyzer.analyze_evidence()
  - Return HTTP 201 for new analysis, 200 for cached
  - Map exceptions to HTTP status codes (400, 404, 408, 409, 413, 500)
  - Add to `src/forensix/app.py`
  - _Requirements: 2.1-2.10, 7.1-7.10_

- [~] 7.2 Implement GET /api/v1/evidence/{evidence_id}/authentication endpoint
  - Accept evidence_id as path parameter
  - Query authentication_results table
  - Return 200 with result if found
  - Return 404 if no results exist
  - Add to `src/forensix/app.py`
  - _Requirements: 8.1-8.4_

### 8. Database Operations

- [~] 8.1 Implement authentication result persistence
  - Create `src/forensix/authentication/storage.py`
  - Implement function to insert authentication_result into database
  - Handle UNIQUE constraint on evidence_id (update vs insert logic)
  - Return generated/existing result ID
  - Use transactions with rollback on error
  - _Requirements: 1.1, 1.3, 1.4_

- [~] 8.2 Implement result retrieval from database
  - Implement function to fetch authentication_result by evidence_id
  - Implement pagination support for querying by verdict
  - Convert database rows to AuthenticationResult objects
  - _Requirements: 8.1-8.4_

### 9. Chain of Custody Integration

- [~] 9.1 Integrate with existing custody logging
  - Modify AuthenticationAnalyzer to log "AUTHENTICATE" action in chain_of_custody_events
  - Capture client_ip from request context
  - Capture user_agent from request headers
  - Include verdict and confidence_score in details JSON
  - Use non-blocking error handling (don't fail analysis if custody logging fails)
  - _Requirements: 6.1-6.3_

### 10. Error Handling and Validation

- [~] 10.1 Implement comprehensive error handling
  - Handle evidence not found (HTTP 404)
  - Handle file not accessible from storage (HTTP 500)
  - Handle unsupported file type (HTTP 400)
  - Handle analysis timeout > 5 minutes (HTTP 408)
  - Handle concurrent analysis (HTTP 409)
  - Handle file size > 1 GB (HTTP 413)
  - Handle database errors (HTTP 500)
  - Log all errors with evidence_id and context
  - _Requirements: 7.1-7.6_

- [~] 10.2 Implement timeout and resource limits
  - Set 5-minute timeout for analyze_evidence() function
  - Enforce 1 GB file size limit before analysis
  - Log processing time for each analysis
  - Return appropriate error if limits exceeded
  - _Requirements: 10.1-10.5_

### 11. Caching and Performance

- [~] 11.1 Implement result caching
  - Check for existing authentication_results in database
  - Return cached results if less than 24 hours old
  - If force_reanalysis=true, bypass cache
  - Verify cache hit/miss in logging
  - _Requirements: 9.1, 9.2_

- [~] 11.2 Optimize database and file I/O
  - Implement connection pooling for SQLite
  - Use buffered file I/O for large file reads
  - Add database indexes for faster queries
  - _Requirements: 9.3, 9.4_

### 12. Request Context and Logging

- [~] 12.1 Implement request context capture
  - Extract client_ip from request (X-Forwarded-For or remote address)
  - Extract user_agent from headers
  - Capture actor_id from query parameter
  - Include in custody event details
  - _Requirements: 6.1, 2.8, 2.9_

- [~] 12.2 Implement comprehensive logging
  - Log all authentication attempts with evidence_id
  - Log analysis result and verdict
  - Log processing time
  - Log any errors encountered
  - Use existing logging infrastructure
  - _Requirements: 10.5_

### 13. Unit Tests for Image Analysis

- [~] 13.1 Write image analyzer unit tests
  - Test EXIF signal generation (complete, missing, inconsistent)
  - Test header validation (valid vs corrupted)
  - Test thumbnail analysis (present, missing, inconsistent)
  - Test color space detection (standard vs anomalous)
  - Test compression artifacts (single vs multiple generations)
  - Verify each signal returns score in [0,100]
  - Use sample image files for testing
  - _Requirements: 3.1-3.8_

### 14. Unit Tests for Video Analysis

- [~] 14.1 Write video analyzer unit tests
  - Test container integrity signal
  - Test codec consistency signal
  - Test frame metadata consistency
  - Test timestamp consistency
  - Test audio stream integrity (if audio present)
  - Test file size vs metadata signal
  - Verify each signal returns score in [0,100]
  - Use sample video files for testing
  - _Requirements: 4.1-4.8_

### 15. Unit Tests for Aggregation and Verdict

- [~] 15.1 Write signal aggregation tests
  - Test weighted averaging algorithm
  - Test verdict logic boundaries (85%, 50%)
  - Test CRITICAL signal handling (forces TAMPERED)
  - Test confidence score range validation [0,100]
  - Test with various signal combinations
  - _Requirements: 5.2, 5.3, 6.1, 6.2_

### 16. Integration Tests

- [~] 16.1 Write end-to-end authentication tests
  - Test full image authentication workflow
  - Test full video authentication workflow
  - Verify results stored in database correctly
  - Verify chain of custody event created
  - Test caching behavior (cached result returned)
  - Test force_reanalysis bypasses cache
  - _Requirements: 2.1-2.10, 6.1-6.3, 9.1, 9.2_

- [~] 16.2 Write error handling tests
  - Test evidence not found (404)
  - Test file not accessible (500)
  - Test unsupported file type (400)
  - Test timeout handling (408)
  - Test file size limit (413)
  - Test concurrent analysis (409)
  - _Requirements: 7.1-7.6_

### 17. API Tests

- [~] 17.1 Write POST /authenticate endpoint tests
  - Test successful analysis returns 201
  - Test cached result returns 200
  - Test force_reanalysis parameter
  - Test actor_id parameter
  - Test error responses (400, 404, 408, 409, 413, 500)
  - Verify response structure matches schema
  - _Requirements: 2.1-2.10_

- [~] 17.2 Write GET /authentication endpoint tests
  - Test result retrieval returns 200
  - Test not found returns 404
  - Test response structure matches schema
  - _Requirements: 8.1-8.4_

### 18. Performance and Load Testing

- [~] 18.1 Test analysis timeout enforcement
  - Verify 5-minute timeout is enforced
  - Test with large files near 1 GB
  - Verify timeout returns HTTP 408
  - _Requirements: 10.1, 10.2_

- [~] 18.2 Test file size limit enforcement
  - Test files just under 1 GB (should pass)
  - Test files just over 1 GB (should reject with 413)
  - Test with various file types
  - _Requirements: 10.3, 10.4_

### 19. Documentation and Examples

- [~] 19.1 Create API documentation
  - Document POST /authenticate endpoint with examples
  - Document GET /authentication endpoint with examples
  - Document request/response schemas
  - Document error responses with examples
  - Document query parameters

- [~] 19.2 Create usage examples
  - Example: Authenticate an image file
  - Example: Authenticate a video file
  - Example: Retrieve cached results
  - Example: Force re-analysis
  - Include sample request/response JSON

### 20. Checkpoint and Validation

- [~] 20.1 Final integration validation
  - Verify all database tables and indexes created
  - Verify all API endpoints functional
  - Verify end-to-end workflow (upload → authenticate → retrieve)
  - Verify chain of custody logging works
  - Verify error handling for all error paths
  - Run full test suite (all tests passing)

- [~] 20.2 Performance validation
  - Verify typical image analysis completes in < 10 seconds
  - Verify typical video analysis completes in < 30 seconds
  - Verify caching returns results in < 1 second
  - Verify timeout enforcement at 5 minutes
  - Verify file size limit at 1 GB

- [~] 20.3 Production readiness check
  - Verify logging is comprehensive
  - Verify error messages are descriptive
  - Verify database transactions are atomic
  - Verify custody logging non-blocking
  - Verify all requirements covered

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "2.2"] },
    { "id": 1, "tasks": ["1.2", "3.1", "4.1"] },
    { "id": 2, "tasks": ["5.1", "5.2", "3.2", "4.2"] },
    { "id": 3, "tasks": ["6.1", "6.2"] },
    { "id": 4, "tasks": ["7.1", "7.2", "8.1", "8.2"] },
    { "id": 5, "tasks": ["9.1", "10.1", "10.2"] },
    { "id": 6, "tasks": ["11.1", "11.2", "12.1", "12.2"] },
    { "id": 7, "tasks": ["13.1", "14.1", "15.1"] },
    { "id": 8, "tasks": ["16.1", "16.2", "17.1", "17.2"] },
    { "id": 9, "tasks": ["18.1", "18.2"] },
    { "id": 10, "tasks": ["19.1", "19.2"] },
    { "id": 11, "tasks": ["20.1", "20.2", "20.3"] }
  ]
}
```

## Notes

- **Dependencies on Upload & Fingerprint**:
  - Uses existing evidence_records table (no duplication)
  - Uses existing chain_of_custody_events table (no duplication)
  - Reads evidence files from ./evidence_storage/
  - Queries evidence metadata from evidence_records

- **Key Implementation Considerations**:
  - Image analysis uses PIL/Pillow, piexif for EXIF extraction
  - Video analysis uses pymediainfo for container/stream analysis
  - Signal-based approach allows for easy addition of new checks
  - Caching optimizes repeated analysis requests
  - Timeout prevents analysis of extremely large files
  - Weighted signal scoring produces reliable verdicts

- **Testing Coverage**:
  - Unit tests for each analyzer (image, video)
  - Unit tests for signal aggregation and verdict logic
  - Integration tests for full workflows
  - API tests for all endpoints
  - Error handling tests for all error paths
  - Performance tests for timeout and size limits

</content>
</invoke>