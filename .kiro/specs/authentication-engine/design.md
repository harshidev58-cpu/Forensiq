# Design Document: Authentication Engine Module

## Overview

The Authentication Engine module adds intelligent authenticity verification to ForensiX by analyzing digital evidence files for signs of tampering, manipulation, or inauthenticity. Unlike the Upload & Fingerprint module which focuses on integrity hashing and metadata extraction, the Authentication Engine applies sophisticated heuristics and signal-based analysis to assess evidence credibility.

The module integrates seamlessly with existing infrastructure—evidence records created by Upload & Fingerprint flow directly into the Authentication Engine. No tables or endpoints are duplicated; instead, new tables and endpoints extend the system.

### Design Philosophy: Signal-Based Authenticity Assessment

This design uses a **signal-based approach** where each authentication check produces a signal with its own score and severity. Signals are combined using weighted averaging to produce a final confidence score and verdict. This design allows:

- **Transparency**: Investigators see exactly which checks passed/failed
- **Auditability**: Each signal is logged in detail for forensic review
- **Extensibility**: New signals can be added without changing core logic
- **Accuracy**: Multi-signal consensus reduces false positives

## Architecture

### System Architecture

The Authentication Engine integrates with the existing Upload & Fingerprint module:

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI REST Layer                      │
│  (Upload, Retrieval, Verification endpoints) + NEW: Auth    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Service Layer                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  EXISTING: Upload, Fingerprint, Custody, Verify     │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  NEW: Authentication Analyzer                         │  │
│  │  ├─ Image Analyzer (EXIF, header, compression)      │  │
│  │  ├─ Video Analyzer (container, codec, frames)       │  │
│  │  └─ Signal Aggregator (weighted scoring)            │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Persistence Layer                          │
│  ┌─────────────────────────────────────────────────────┐  │
│  │   SQLite Database (NEW table: authentication_results)   │  │
│  │   (Existing: evidence_records, chain_of_custody)   │  │
│  └─────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐ │
│  │   Local File Storage (./evidence_storage/)           │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow: Authentication Request

```
Client → POST /api/v1/evidence/{evidence_id}/authenticate
    ↓
[Retrieve evidence record from evidence_records]
    ↓
[Verify file exists in storage]
    ↓
[Retrieve file from ./evidence_storage/]
    ↓
[Route to appropriate analyzer based on mime_type]
    ↓
[Image Analyzer] OR [Video Analyzer]
    ↓
[Perform individual signal checks]
    ↓
[Aggregate signals with weighted scoring]
    ↓
[Generate verdict and explanation]
    ↓
[INSERT into authentication_results table]
    ↓
[Log chain of custody: AUTHENTICATE action]
    ↓
Client ← HTTP 201/200 {authentication_result JSON}
```

## Components and Interfaces

### 1. Authentication Analyzer (Main Orchestrator)

**Responsibility**: Coordinates the authentication analysis workflow

**Interface**:
```python
class AuthenticationAnalyzer:
    def analyze_evidence(
        self,
        evidence_id: str,
        force_reanalysis: bool = False,
        actor_id: str = "SYSTEM",
        request_context: dict = None
    ) -> dict:
        """
        Main entry point for authentication analysis.
        
        Returns:
        {
            "id": "uuid",
            "evidence_id": "uuid",
            "confidence_score": 0-100,
            "verdict": "AUTHENTIC|SUSPICIOUS|TAMPERED",
            "signals_detected": [...],
            "explanation": "string",
            "analyzed_at": "ISO8601",
            "analyzer_version": "string"
        }
        """
```

**Workflow**:
1. Retrieve evidence record and verify it exists
2. Check if cached results exist and force_reanalysis=false → return cached
3. Load file from storage
4. Route to Image or Video Analyzer based on mime_type
5. Collect all signals from analyzer
6. Aggregate signals into confidence_score and verdict
7. Store results in authentication_results table
8. Log chain of custody event
9. Return result

### 2. Image Analyzer

**Responsibility**: Perform image-specific authenticity checks

**Signals Performed**:
1. **EXIF Metadata Validation**
   - Check EXIF presence, completeness, and consistency
   - Verify DateTimeOriginal vs. file modification time
   - Check GPS coordinate plausibility

2. **Image Header Validation**
   - Validate JPEG/PNG/GIF magic numbers
   - Check dimensions and size indicators
   - Detect header corruption

3. **Thumbnail Analysis** (JPEG only)
   - Check embedded thumbnail presence and size
   - Verify thumbnail-to-image size ratio

4. **Color Space Analysis**
   - Verify standard color spaces (RGB, CMYK, Grayscale)
   - Detect non-standard or unusual profiles

5. **Compression Analysis**
   - Analyze JPEG quantization tables
   - Detect multiple compression generations (re-compression artifact)
   - Score based on compression consistency

**Libraries Used**:
- PIL/Pillow: Image loading and EXIF extraction
- struct: Binary header parsing
- piexif: Advanced EXIF analysis

**Output**: Array of Signal objects (see data models)

### 3. Video Analyzer

**Responsibility**: Perform video-specific authenticity checks

**Signals Performed**:
1. **Container Integrity**
   - Validate MP4/MOV/AVI container format
   - Check atom/box structure
   - Verify declared vs. actual duration

2. **Codec Analysis**
   - Verify declared vs. actual codec
   - Check for standard vs. unusual codec combinations
   - Validate codec parameters

3. **Frame Metadata**
   - Check frame count consistency
   - Verify frame rate throughout file
   - Detect frame drops or duplicates

4. **Timestamp Consistency**
   - Verify creation metadata timestamp
   - Check for timestamp gaps or overlaps
   - Score based on consistency

5. **Audio Stream Integrity**
   - Verify audio codec and sample rate
   - Check audio-video sync metadata

6. **File Size vs. Metadata**
   - Verify file size matches declared duration/bitrate
   - Detect truncated files

**Libraries Used**:
- pymediainfo: Comprehensive video metadata extraction
- ffmpeg-python: Low-level stream analysis (optional)
- struct: Binary container parsing

**Output**: Array of Signal objects

### 4. Signal Aggregator

**Responsibility**: Combine individual signals into final verdict and confidence score

**Algorithm**:
1. Collect all signals from Image/Video Analyzer
2. For each signal, extract: severity, score, category
3. Weight signals by severity:
   - CRITICAL: 40% weight
   - WARNING: 30% weight
   - INFO: 10% weight
4. Compute weighted average confidence_score (0-100)
5. Determine verdict:
   - AUTHENTIC: confidence_score >= 85 AND no CRITICAL signals
   - SUSPICIOUS: confidence_score 50-84 OR some WARNING signals
   - TAMPERED: confidence_score < 50 OR CRITICAL signals detected
6. Generate human-readable explanation based on signals

**Output**: verdict, confidence_score, explanation

### 5. FastAPI Endpoints

#### POST /api/v1/evidence/{evidence_id}/authenticate

```python
@app.post(
    "/api/v1/evidence/{evidence_id}/authenticate",
    response_model=AuthenticationResultResponse,
    status_code=201  # 201 for new analysis, 200 for cached
)
async def authenticate_evidence(
    evidence_id: str,
    force_reanalysis: bool = Query(False),
    actor_id: str = Query(None),
    request: Request
) -> AuthenticationResultResponse:
    """
    Analyze evidence file for authenticity.
    
    Query Parameters:
    - force_reanalysis: bool (default false) - Skip cache and re-analyze
    - actor_id: str (optional) - Identifier of requesting user/system
    
    Request Headers Used:
    - X-Forwarded-For or Remote-Addr: client_ip
    - User-Agent: user_agent string
    
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
```

#### GET /api/v1/evidence/{evidence_id}/authentication

```python
@app.get(
    "/api/v1/evidence/{evidence_id}/authentication",
    response_model=AuthenticationResultResponse,
    status_code=200
)
async def get_authentication_result(
    evidence_id: str
) -> AuthenticationResultResponse:
    """
    Retrieve authentication analysis result for evidence.
    
    Returns:
    - 200: Result found
    - 404: No analysis results found
    - 500: Database error
    """
```

### 6. Data Models

#### Signal (JSON Structure)
```python
@dataclass
class Signal:
    signal_name: str  # e.g., "EXIF_COMPLETE"
    category: str     # "METADATA", "STRUCTURE", "ENCODING", "TIMESTAMP"
    severity: str     # "INFO", "WARNING", "CRITICAL"
    score: int        # 0-100 (0=clean, 100=tampering)
    message: str      # Human-readable message
    details: Optional[dict]  # Specific findings
```

#### AuthenticationResult (Database Model)
```python
@dataclass
class AuthenticationResult:
    id: str                      # UUID
    evidence_id: str             # FK to evidence_records
    confidence_score: int        # 0-100
    verdict: str                 # "AUTHENTIC", "SUSPICIOUS", "TAMPERED"
    signals_detected: List[Signal]  # JSON array
    explanation: str             # Max 5000 chars
    analyzed_at: str             # ISO 8601 UTC
    analyzer_version: str        # e.g., "1.0.0"
    created_at: str              # Timestamp
    updated_at: str              # Timestamp
```

#### AuthenticationResultResponse (Pydantic Model)
```python
class AuthenticationResultResponse(BaseModel):
    id: str
    evidence_id: str
    confidence_score: int = Field(..., ge=0, le=100)
    verdict: str = Field(..., description="AUTHENTIC, SUSPICIOUS, or TAMPERED")
    signals_detected: List[dict]
    explanation: str
    analyzed_at: str
    analyzer_version: str
```

### 7. Database Schema

#### authentication_results Table
```sql
CREATE TABLE IF NOT EXISTS authentication_results (
    id TEXT PRIMARY KEY,                      -- UUID
    evidence_id TEXT NOT NULL UNIQUE,         -- FK to evidence_records.id
    confidence_score INTEGER NOT NULL,        -- 0-100
    verdict TEXT NOT NULL,                    -- "AUTHENTIC", "SUSPICIOUS", "TAMPERED"
    signals_detected TEXT NOT NULL,           -- JSON array of signals
    explanation TEXT NOT NULL,                -- Max 5000 chars
    analyzed_at TEXT NOT NULL,                -- ISO 8601 UTC
    analyzer_version TEXT NOT NULL,           -- e.g., "1.0.0"
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evidence_id) REFERENCES evidence_records(id) ON DELETE CASCADE
)

CREATE INDEX idx_evidence_id ON authentication_results(evidence_id)
CREATE INDEX idx_verdict ON authentication_results(verdict)
CREATE INDEX idx_analyzed_at ON authentication_results(analyzed_at)
CREATE INDEX idx_confidence_score ON authentication_results(confidence_score)
```

## Correctness Properties

### Property 1: Signal Completeness

*For any* image file analysis, the system SHALL produce at least 5 distinct signals (EXIF, Header, Thumbnail, ColorSpace, Compression).

*For any* video file analysis, the system SHALL produce at least 6 distinct signals (Container, Codec, Frame, Timestamp, Audio, FileSize).

**Validates: Requirement 5.2**

### Property 2: Verdict Consistency

*For any* evidence file, if all signals have score > 80, the verdict SHALL be AUTHENTIC.

*For any* evidence file, if any CRITICAL signal is detected, the verdict SHALL be TAMPERED.

**Validates: Requirement 3.8, 4.8**

### Property 3: Confidence Score Range

*For any* authentication analysis, the confidence_score SHALL be an integer in range [0, 100] inclusive.

**Validates: Requirement 1.1, 5.1**

### Property 4: Signal Score Validity

*For any* signal in signals_detected, the score SHALL be an integer in range [0, 100] inclusive.

**Validates: Requirement 5.1**

### Property 5: Result Uniqueness

*For any* evidence_id, at most one active authentication_result SHALL exist (no duplicates unless force_reanalysis=true creates a new record).

**Validates: Requirement 1.1, 1.4**

### Property 6: Chain of Custody Integration

*For any* authentication analysis performed, a chain of custody event with action_type="AUTHENTICATE" SHALL be created.

**Validates: Requirement 6.1**

### Property 7: Cache Consistency

*For any* evidence_id with existing results and force_reanalysis=false, the returned result SHALL be identical to the previously stored result (no drift).

**Validates: Requirement 9.1**

### Property 8: File Size Limit Enforcement

*For any* file larger than 1 GB, the system SHALL reject authentication analysis with HTTP 413.

**Validates: Requirement 10.3**

### Property 9: Timeout Enforcement

*For any* authentication analysis that exceeds 5 minutes, the system SHALL abort and return HTTP 408.

**Validates: Requirement 10.1**

### Property 10: Unsupported Type Rejection

*For any* evidence file with mime_type NOT starting with "image/" or "video/", the system SHALL reject with HTTP 400.

**Validates: Requirement 2.5**

## Error Handling

### Atomic Operations

Authentication result creation uses database transactions:
```python
try:
    # 1. Insert authentication_result
    # 2. Create custody event
    db.commit()
except Exception:
    db.rollback()
    raise
```

### Non-Blocking Custody Logging

Custody logging failures don't block analysis completion:
```python
try:
    log_custody_event(...)
except Exception as e:
    logger.error(f"Custody logging failed: {e}")
    # Continue - don't raise
```

### File Access Error Handling

File not found or access denied returns clear HTTP 500:
```python
try:
    file = open(storage_path, 'rb')
except FileNotFoundError:
    raise HTTPException(status_code=500, detail="Evidence file not found in storage")
except PermissionError:
    raise HTTPException(status_code=500, detail="Permission denied accessing evidence file")
```

### Error Response Codes

- **HTTP 400 (Bad Request)**: Unsupported file type
- **HTTP 404 (Not Found)**: Evidence record not found, no prior analysis
- **HTTP 408 (Request Timeout)**: Analysis exceeded 5 minute timeout
- **HTTP 409 (Conflict)**: Analysis already in progress for this evidence
- **HTTP 413 (Payload Too Large)**: File exceeds 1 GB limit
- **HTTP 500 (Internal Server Error)**: File access error, processing error, database error

## Testing Strategy

### Unit Tests

- Signal generation accuracy (each analyzer produces correct signals)
- Signal scoring correctness (score ranges 0-100, severity-based weighting)
- Verdict logic (correct verdict for various signal combinations)
- Threshold testing (exact boundary conditions: 85% for AUTHENTIC, 50% for SUSPICIOUS)

### Integration Tests

- End-to-end image authentication (upload → analyze → verify signals)
- End-to-end video authentication
- Cache behavior (cached result returned on second request)
- Force reanalysis (new analysis performed when requested)
- Chain of custody logging integration

### Property-Based Tests

- Signal Completeness (Property 1)
- Verdict Consistency (Property 2)
- Confidence Score Range (Property 3)
- File Size Limit Enforcement (Property 8)
- Timeout Enforcement (Property 9)

### Edge Cases

- Zero-byte files
- Corrupted image/video files
- Files with missing EXIF/metadata
- Files at exact 1 GB boundary
- Concurrent analysis requests
- Database failure during result storage
- Analysis exceeding 5-minute timeout

</content>
</invoke>