# Authentication Engine API Documentation

## Overview

The Authentication Engine module extends ForensiX with intelligent authenticity verification for digital evidence. It analyzes images and videos for signs of tampering, manipulation, or inauthenticity using a signal-based approach.

## Architecture

### Core Components

1. **ImageAnalyzer**: Performs image-specific checks
   - EXIF metadata validation
   - Image header validation (JPEG, PNG, GIF)
   - Thumbnail analysis (JPEG only)
   - Color space analysis
   - Compression artifacts detection

2. **VideoAnalyzer**: Performs video-specific checks
   - Container integrity (MP4, AVI)
   - Codec consistency
   - Frame metadata consistency
   - Timestamp consistency
   - Audio stream integrity
   - File size vs metadata

3. **SignalAggregator**: Combines signals into verdict
   - Calculates confidence score (0-100)
   - Determines verdict (AUTHENTIC, SUSPICIOUS, TAMPERED)
   - Generates human-readable explanation

4. **AuthenticationStorage**: Manages database operations
   - Persists results with caching (24-hour TTL)
   - Retrieves results by evidence ID
   - Queries by verdict

## API Endpoints

### POST /api/v1/evidence/{evidence_id}/authenticate

Analyze evidence file for authenticity.

**Query Parameters:**
- `force_reanalysis` (boolean, default: false) - Skip cache and re-analyze
- `actor_id` (string, optional) - Identifier of requesting user/system

**Request Headers (Captured):**
- `User-Agent` - Client user agent
- `X-Forwarded-For` or `Remote-Addr` - Client IP address

**Response Codes:**
- `201 Created` - New analysis completed
- `200 OK` - Cached result returned
- `400 Bad Request` - Unsupported file type
- `404 Not Found` - Evidence not found
- `408 Request Timeout` - Analysis exceeded timeout
- `409 Conflict` - Analysis already in progress
- `413 Payload Too Large` - File exceeds 1 GB
- `500 Internal Server Error` - Processing error

**Response Body:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "evidence_id": "550e8400-e29b-41d4-a716-446655440001",
  "confidence_score": 85,
  "verdict": "AUTHENTIC",
  "signals_detected": [
    {
      "signal_name": "HEADER_VALID",
      "category": "STRUCTURE",
      "severity": "INFO",
      "score": 5,
      "message": "JPEG header valid (magic number correct)",
      "details": {"format": "JPEG", "magic_valid": true}
    },
    {
      "signal_name": "EXIF_COMPLETE",
      "category": "METADATA",
      "severity": "INFO",
      "score": 10,
      "message": "EXIF metadata complete with 3 standard tags",
      "details": {"tags_found": {"DateTime": "...", "Model": "..."}}
    }
  ],
  "explanation": "Authentication Analysis Result: AUTHENTIC\nConfidence Score: 85%\n...",
  "analyzed_at": "2024-01-15T10:30:45.123Z",
  "analyzer_version": "1.0.0"
}
```

### GET /api/v1/evidence/{evidence_id}/authentication

Retrieve authentication analysis result for evidence.

**Response Codes:**
- `200 OK` - Result found
- `404 Not Found` - No analysis results found
- `500 Internal Server Error` - Database error

**Response Body:** Same as POST endpoint response

## Signal Types

### Image Signals

| Signal Name | Category | Severity Range | Score Range | Meaning |
|---|---|---|---|---|
| EXIF_COMPLETE | METADATA | INFO | 10 | All standard EXIF tags present |
| EXIF_MISSING | METADATA | WARNING | 50 | No EXIF metadata found |
| EXIF_INCONSISTENT | METADATA | WARNING | 45 | EXIF dates don't match file timestamps |
| HEADER_VALID | STRUCTURE | INFO | 5 | Image header is valid |
| HEADER_CORRUPTED | STRUCTURE | CRITICAL | 85 | Image header is corrupted |
| DIMENSIONS_VALID | STRUCTURE | INFO | 5 | Image dimensions are valid |
| DIMENSIONS_INVALID | STRUCTURE | WARNING | 50 | Invalid or zero dimensions |
| THUMBNAIL_PRESENT | STRUCTURE | INFO | 10 | JPEG has embedded thumbnail |
| THUMBNAIL_MISSING | STRUCTURE | INFO | 15 | JPEG has no thumbnail |
| COLORSPACE_STANDARD | ENCODING | INFO | 10 | Standard color space (RGB, CMYK, etc) |
| COLORSPACE_ANOMALOUS | ENCODING | WARNING | 40 | Unusual color space detected |
| COMPRESSION_SINGLE | ENCODING | INFO | 15 | Single JPEG compression generation |
| COMPRESSION_MULTIPLE_GENERATIONS | ENCODING | WARNING | 60 | Multiple compression generations detected |

### Video Signals

| Signal Name | Category | Severity Range | Score Range | Meaning |
|---|---|---|---|---|
| CONTAINER_VALID | STRUCTURE | INFO | 5 | Container format is valid |
| CONTAINER_CORRUPTED | STRUCTURE | CRITICAL | 85 | Container corrupted/invalid |
| CONTAINER_MALFORMED | STRUCTURE | CRITICAL | 80 | Container structure invalid |
| CODEC_STANDARD | ENCODING | INFO | 10 | Standard codec detected |
| CODEC_UNUSUAL | ENCODING | WARNING | 35 | Unusual codec detected |
| FRAMERATE_STANDARD | METADATA | INFO | 5 | Standard frame rate |
| FRAMERATE_ANOMALOUS | METADATA | WARNING | 30 | Unusual frame rate |
| AUDIO_PRESENT | STRUCTURE | INFO | 5 | Audio stream detected |
| AUDIO_MISSING | STRUCTURE | INFO | 20 | No audio stream |
| SIZE_METADATA_MATCH | STRUCTURE | INFO | 10 | File size matches metadata |
| FILE_EMPTY | STRUCTURE | CRITICAL | 90 | File is empty |
| FILE_TOO_SMALL | STRUCTURE | CRITICAL | 85 | File suspiciously small |

## Verdict Determination

The Authentication Engine produces one of three verdicts:

### AUTHENTIC (≥85% confidence AND no CRITICAL signals)
- File appears unmodified and authentic
- All key checks passed without significant issues
- **Recommendation**: File can be considered authentic for investigation

### SUSPICIOUS (50-84% confidence OR some WARNING signals)
- File shows some anomalies or ambiguous characteristics
- Further manual review recommended
- **Recommendation**: Investigate specific findings before drawing conclusions

### TAMPERED (< 50% confidence OR CRITICAL signals detected)
- File shows signs of tampering or significant manipulation
- Critical issues detected suggesting integrity compromise
- **Recommendation**: Treat as potentially unreliable evidence

## Confidence Score Interpretation

- **90-100**: Highly confident evidence is authentic
- **75-89**: Confident evidence is authentic with minor anomalies
- **50-74**: Uncertain - mixed signals, further review needed
- **25-49**: Likely tampered with multiple anomalies detected
- **0-24**: Highly confident evidence is tampered or inauthentic

## Caching Behavior

- Results are cached in database for 24 hours
- Use `force_reanalysis=true` query parameter to bypass cache
- Cache prevents re-analysis of the same file within 24 hours
- Reduces processing load for frequently-analyzed files

## Error Handling

### Common Error Responses

**404 Evidence Not Found**
```json
{
  "status_code": 404,
  "error": "NotFound",
  "message": "Evidence record not found",
  "evidence_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

**400 Unsupported File Type**
```json
{
  "status_code": 400,
  "error": "BadRequest",
  "message": "Unsupported file type for authentication analysis",
  "detail": "Only image/* and video/* files are supported"
}
```

**413 File Too Large**
```json
{
  "status_code": 413,
  "error": "PayloadTooLarge",
  "message": "File too large for authentication analysis (max 1 GB)",
  "evidence_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

**408 Timeout**
```json
{
  "status_code": 408,
  "error": "Timeout",
  "message": "Analysis timeout - file too large or processing took too long",
  "evidence_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

## Usage Examples

### Example 1: Analyze a JPEG Image

```bash
curl -X POST "http://localhost:8000/api/v1/evidence/550e8400-e29b-41d4-a716-446655440001/authenticate" \
  -H "User-Agent: ForensiX-Client/1.0" \
  -G \
  -d "actor_id=investigator-123"
```

Response (201 Created):
```json
{
  "id": "uuid",
  "evidence_id": "550e8400-e29b-41d4-a716-446655440001",
  "confidence_score": 85,
  "verdict": "AUTHENTIC",
  "signals_detected": [...],
  "explanation": "Authentication Analysis Result: AUTHENTIC...",
  "analyzed_at": "2024-01-15T10:30:45.123Z",
  "analyzer_version": "1.0.0"
}
```

### Example 2: Force Re-analysis

```bash
curl -X POST "http://localhost:8000/api/v1/evidence/550e8400-e29b-41d4-a716-446655440001/authenticate?force_reanalysis=true" \
  -H "User-Agent: ForensiX-Client/1.0"
```

### Example 3: Retrieve Cached Result

```bash
curl -X GET "http://localhost:8000/api/v1/evidence/550e8400-e29b-41d4-a716-446655440001/authentication"
```

Response (200 OK):
```json
{
  "id": "uuid",
  "evidence_id": "550e8400-e29b-41d4-a716-446655440001",
  "confidence_score": 85,
  "verdict": "AUTHENTIC",
  "signals_detected": [...],
  "explanation": "...",
  "analyzed_at": "2024-01-15T10:30:45.123Z",
  "analyzer_version": "1.0.0"
}
```

## Chain of Custody Integration

Every authentication analysis creates a custody event with:
- Action type: `AUTHENTICATE`
- Timestamp of analysis
- Client IP address (from request)
- User Agent (from request headers)
- Verdict and confidence score

This ensures complete audit trail of all authenticity verifications.

## Performance Characteristics

- Typical image analysis: < 10 seconds
- Typical video analysis: < 30 seconds
- Cached result retrieval: < 1 second
- Maximum timeout: 5 minutes
- Maximum file size: 1 GB

## Database Schema

### authentication_results Table

```sql
CREATE TABLE authentication_results (
    id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL UNIQUE,
    confidence_score INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    signals_detected TEXT NOT NULL,
    explanation TEXT NOT NULL,
    analyzed_at TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evidence_id) REFERENCES evidence_records(id) ON DELETE CASCADE
)
```

## Integration with Existing ForensiX

- Uses existing `evidence_records` table (no duplication)
- Uses existing `custody_entries` table for chain of custody
- Reads evidence files from existing `./evidence_storage/` directory
- Queries evidence metadata from existing `evidence_records` table
- Non-blocking custody logging (doesn't fail analysis if logging fails)

## Supported File Formats

### Images
- JPEG/JPG (.jpg, .jpeg)
- PNG (.png)
- GIF (.gif)
- BMP (.bmp)

### Videos
- MP4 (.mp4)
- MOV (.mov)
- AVI (.avi)

## Requirements Coverage

This implementation validates the following requirements:

- **Req 1**: Authentication Results Table (schema, indexes, storage)
- **Req 2**: Authentication Endpoint (POST analyze, GET retrieve)
- **Req 3**: Image Authentication Analysis (EXIF, headers, thumbnails, color space, compression)
- **Req 4**: Video Authentication Analysis (container, codec, frames, timestamps, audio, size)
- **Req 5**: Signal Structure (individual signals with name, category, severity, score, message, details)
- **Req 6**: Chain of Custody Integration (AUTHENTICATE events with context)
- **Req 7**: Error Handling (400, 404, 408, 409, 413, 500 status codes)
- **Req 8**: Authentication Result Retrieval (GET endpoint, pagination support)
- **Req 9**: Performance and Caching (24-hour TTL, force_reanalysis bypass)
- **Req 10**: Limits and Quotas (5-minute timeout, 1 GB file size limit)

## Testing

Run the authentication test suite:

```bash
# Integration tests
pytest tests/test_authentication_integration.py -v

# Image analyzer tests
pytest tests/test_authentication_image_analyzer.py -v

# All tests
pytest tests/ -k authentication -v
```

## Limitations

- FFprobe not required (basic video analysis only)
- Piexif not required (basic EXIF analysis using PIL)
- Analysis focused on structure and metadata, not deep ML-based detection
- Video analysis limited to container and basic metadata (no frame-by-frame analysis)
- No audio spectrum analysis

## Future Enhancements

- Deep learning-based fake detection
- Face recognition and consistency analysis
- Advanced audio analysis and lip-sync detection
- Blockchain-based evidence certification
- Integration with external verification services
- Bayesian network for evidence scoring
- Machine learning-based anomaly detection
