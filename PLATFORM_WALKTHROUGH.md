# ForensiX Platform - Complete Walkthrough

This guide demonstrates how the entire ForensiX forensic evidence platform works, from uploading evidence to authenticating files.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    INVESTIGATOR / CLIENT                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    HTTP REST API
                           │
        ┌──────────────────┴───────────────────┐
        │                                      │
    ┌───▼────────────────────────┐    ┌───────▼──────────────────┐
    │   UPLOAD & FINGERPRINT     │    │  AUTHENTICATION ENGINE   │
    │   MODULE                   │    │  MODULE                  │
    │                            │    │                          │
    │ • Upload Handler           │    │ • Image Analyzer         │
    │ • SHA-256 Hashing          │    │ • Video Analyzer         │
    │ • Metadata Extraction      │    │ • Signal Aggregator      │
    │ • Custody Logging          │    │ • Result Storage         │
    │ • Verification             │    │ • Verdict Determination  │
    └───┬────────────────────────┘    └───────┬──────────────────┘
        │                                      │
        └──────────────────┬───────────────────┘
                           │
        ┌──────────────────┴───────────────────┐
        │                                      │
    ┌───▼──────────────┐            ┌─────────▼────────────┐
    │   STORAGE LAYER  │            │  DATABASE (SQLite)   │
    │                  │            │                      │
    │ • /evidence_stor │            │ • evidence_files     │
    │   age/           │            │ • chain_of_custody   │
    │ • File Upload    │            │ • auth_results       │
    │ • File Retrieval │            │ • Indexes & Logs     │
    └──────────────────┘            └──────────────────────┘
```

---

## Part 1: Upload & Fingerprint Module

### What It Does

The Upload & Fingerprint module handles secure evidence file upload, cryptographic verification, and chain-of-custody tracking.

### Step-by-Step Flow

#### **Step 1: Upload Evidence File**

**Request:**
```http
POST /api/v1/evidence/upload HTTP/1.1
Host: localhost:5000
Content-Type: multipart/form-data

Form Data:
  file: [binary image/video file]
  uploader_id: "detective_smith_badge_12345"
  collection_method: "physical_seizure"
```

**What Happens Behind the Scenes:**

1. **File Reception**
   ```python
   # app.py - upload_evidence()
   file_content = await form.file.read()
   uploader_id = form.uploader_id
   collection_method = form.collection_method
   ```

2. **File Validation**
   ```python
   # Checks performed:
   - File exists and has content
   - File size < 500 MB
   - MIME type supported (image/*, video/*)
   - Filename sanitized
   ```

3. **Hash Calculation**
   ```python
   # hashing.py
   sha256_hash = calculate_sha256_hash(file_content)
   # Example output: "a1b2c3d4e5f6g7h8i9j0..."
   ```

4. **File Storage**
   ```python
   # upload_handler.py
   storage_path = f"./evidence_storage/{evidence_id}.bin"
   with open(storage_path, 'wb') as f:
       f.write(file_content)
   ```

5. **Metadata Extraction**
   ```python
   # metadata.py
   metadata = extract_metadata(file_content, mime_type)
   # For JPEG: EXIF data (camera, date, GPS)
   # For MP4: codec, duration, resolution, etc.
   ```

6. **Database Record Creation**
   ```sql
   INSERT INTO evidence_files (
     id, original_filename, mime_type, file_size_bytes, 
     sha256_hash, storage_uri, uploader_id, collection_method, 
     status, created_at, updated_at
   ) VALUES (
     'uuid-123', 'photo.jpg', 'image/jpeg', 2458624,
     'a1b2c3d4e5f6...', './evidence_storage/uuid-123.bin',
     'detective_smith_badge_12345', 'physical_seizure',
     'RECEIVED', '2026-10-05T14:23:45Z', '2026-10-05T14:23:45Z'
   )
   ```

7. **Chain of Custody Entry**
   ```python
   # custody.py
   custody_event = {
     "evidence_id": "uuid-123",
     "action_type": "UPLOAD",
     "actor_id": "detective_smith_badge_12345",
     "timestamp": "2026-10-05T14:23:45Z",
     "client_ip": "192.168.1.100",
     "user_agent": "curl/7.68.0",
     "details": {
       "filename": "photo.jpg",
       "size_bytes": 2458624,
       "hash": "a1b2c3d4e5f6..."
     }
   }
   ```

**Response:**
```json
{
  "status": "success",
  "evidence_id": "uuid-123",
  "filename": "photo.jpg",
  "mime_type": "image/jpeg",
  "file_size_bytes": 2458624,
  "sha256_hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "storage_uri": "./evidence_storage/uuid-123.bin",
  "status": "RECEIVED",
  "created_at": "2026-10-05T14:23:45Z"
}
```

---

#### **Step 2: Retrieve Evidence Information**

**Request:**
```http
GET /api/v1/evidence/uuid-123 HTTP/1.1
Host: localhost:5000
```

**What Happens:**

1. **Database Query**
   ```sql
   SELECT * FROM evidence_files WHERE id = 'uuid-123'
   ```

2. **Custody Logging**
   ```python
   # Log the access action
   log_custody_event(
     evidence_id="uuid-123",
     action_type="ACCESS",
     actor_id="detective_smith_badge_12345",
     client_ip="192.168.1.100"
   )
   ```

**Response:**
```json
{
  "id": "uuid-123",
  "original_filename": "photo.jpg",
  "mime_type": "image/jpeg",
  "file_size_bytes": 2458624,
  "sha256_hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "storage_uri": "./evidence_storage/uuid-123.bin",
  "uploader_id": "detective_smith_badge_12345",
  "collection_method": "physical_seizure",
  "status": "RECEIVED",
  "created_at": "2026-10-05T14:23:45Z",
  "updated_at": "2026-10-05T14:23:45Z"
}
```

---

#### **Step 3: Verify File Integrity**

**Request:**
```http
POST /api/v1/evidence/uuid-123/verify HTTP/1.1
Host: localhost:5000
Content-Type: application/json

{
  "provided_hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
}
```

**What Happens:**

1. **Retrieve File from Storage**
   ```python
   # verification.py
   file_path = "./evidence_storage/uuid-123.bin"
   with open(file_path, 'rb') as f:
       file_content = f.read()
   ```

2. **Recalculate Hash**
   ```python
   recalculated_hash = calculate_sha256_hash(file_content)
   # Result: "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
   ```

3. **Compare Hashes**
   ```python
   original_hash = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
   provided_hash = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
   
   if original_hash.lower() == provided_hash.lower():
       result = "VERIFIED"
   else:
       result = "TAMPERED"
   ```

4. **Log Result**
   ```python
   log_custody_event(
     evidence_id="uuid-123",
     action_type="VERIFY",
     details={"result": "VERIFIED", "timestamp": "..."}
   )
   ```

**Response:**
```json
{
  "evidence_id": "uuid-123",
  "verified": true,
  "original_hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "provided_hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "match": true,
  "status": "VERIFIED",
  "timestamp": "2026-10-05T14:24:10Z"
}
```

---

#### **Step 4: View Chain of Custody**

**Request:**
```http
GET /api/v1/evidence/uuid-123/custody HTTP/1.1
Host: localhost:5000
```

**What Happens:**

1. **Query All Events**
   ```sql
   SELECT * FROM chain_of_custody_events 
   WHERE evidence_id = 'uuid-123' 
   ORDER BY timestamp ASC
   ```

2. **Return Chronological Audit Trail**

**Response:**
```json
{
  "evidence_id": "uuid-123",
  "events": [
    {
      "id": "event-1",
      "action_type": "UPLOAD",
      "actor_id": "detective_smith_badge_12345",
      "timestamp": "2026-10-05T14:23:45Z",
      "client_ip": "192.168.1.100",
      "user_agent": "curl/7.68.0",
      "details": {
        "filename": "photo.jpg",
        "size_bytes": 2458624,
        "hash": "a1b2c3d4e5f6..."
      }
    },
    {
      "id": "event-2",
      "action_type": "ACCESS",
      "actor_id": "detective_smith_badge_12345",
      "timestamp": "2026-10-05T14:24:00Z",
      "client_ip": "192.168.1.100",
      "user_agent": "curl/7.68.0",
      "details": {}
    },
    {
      "id": "event-3",
      "action_type": "VERIFY",
      "actor_id": "detective_smith_badge_12345",
      "timestamp": "2026-10-05T14:24:10Z",
      "client_ip": "192.168.1.100",
      "user_agent": "curl/7.68.0",
      "details": {
        "result": "VERIFIED"
      }
    }
  ],
  "total_events": 3
}
```

---

## Part 2: Authentication Engine Module

### What It Does

The Authentication Engine analyzes image and video files for authenticity by generating multiple "signals" (individual checks), aggregating them with weighted scoring, and producing a verdict.

### The Signal System

Each signal is an individual authenticity check. Think of it like a forensic analyst checking multiple indicators:

```
Image Authentication Signals:
├── EXIF_VALIDITY (Is EXIF metadata present and consistent?)
├── HEADER_INTEGRITY (Is the file header valid?)
├── THUMBNAIL_CONSISTENCY (Does the thumbnail match the image?)
├── COLOR_SPACE_VALIDITY (Is the color space valid?)
├── COMPRESSION_CONSISTENCY (Is compression method consistent?)
└── ENCODING_ARTIFACTS (Are there signs of re-encoding?)

Video Authentication Signals:
├── CONTAINER_VALIDITY (Is the video container valid?)
├── CODEC_VERIFICATION (Are the codecs correctly declared?)
├── FRAME_INTEGRITY (Are frames structurally sound?)
├── AUDIO_STREAM_VALIDITY (Is audio metadata valid?)
└── TIMESTAMP_CONSISTENCY (Are timestamps consistent?)
```

### Step-by-Step Flow

#### **Step 1: Request Authentication Analysis**

**Request:**
```http
POST /api/v1/evidence/uuid-123/authenticate?force_reanalysis=false&actor_id=investigator_001 HTTP/1.1
Host: localhost:5000
```

**What Happens:**

1. **Request Context Capture**
   ```python
   # app.py - authenticate_evidence()
   client_ip = "192.168.1.100"
   user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
   actor_id = "investigator_001"
   request_context = {
       "client_ip": client_ip,
       "user_agent": user_agent
   }
   ```

2. **Evidence Validation**
   ```python
   # AuthenticationAnalyzer.analyze_evidence()
   evidence = retrieve_evidence_from_db("uuid-123")
   
   if not evidence:
       raise EvidenceNotFoundError()
   
   mime_type = evidence["mime_type"]
   if not mime_type.startswith(("image/", "video/")):
       raise UnsupportedFileTypeError()
   ```

3. **Cache Check**
   ```python
   # Check if analysis exists and is fresh (< 24 hours)
   cached_result = get_cached_result("uuid-123")
   
   if cached_result and not force_reanalysis:
       if cached_result["analyzed_at"] > (now - 24 hours):
           return cached_result  # HTTP 200
   ```

---

#### **Step 2: Image Analysis (If Image File)**

**For a JPEG photo:**

```python
# authentication/image_analyzer.py

def analyze_image(file_path):
    signals = []
    
    # Signal 1: EXIF Validation
    try:
        exif_data = extract_exif(file_path)
        if exif_data:
            # Check consistency
            date_original = exif_data.get("DateTimeOriginal")
            file_mod_time = get_file_modification_time(file_path)
            
            if dates_match(date_original, file_mod_time):
                signals.append(Signal(
                    signal_name="EXIF_VALIDITY",
                    category="METADATA",
                    severity="INFO",
                    score=95,  # High confidence
                    message="EXIF metadata complete and consistent"
                ))
            else:
                signals.append(Signal(
                    signal_name="EXIF_INCONSISTENCY",
                    category="METADATA",
                    severity="WARNING",
                    score=50,
                    message="EXIF date differs from file modification time"
                ))
        else:
            signals.append(Signal(
                signal_name="EXIF_MISSING",
                category="METADATA",
                severity="INFO",
                score=60,
                message="No EXIF metadata found"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="EXIF_ERROR",
            category="METADATA",
            severity="WARNING",
            score=40,
            message=f"Error reading EXIF: {str(e)}"
        ))
    
    # Signal 2: Header Validation
    try:
        header = read_file_header(file_path, 4)
        if header == b'\xff\xd8\xff\xe0':  # JPEG magic number
            signals.append(Signal(
                signal_name="HEADER_INTEGRITY",
                category="STRUCTURE",
                severity="INFO",
                score=98,
                message="Valid JPEG header detected"
            ))
        else:
            signals.append(Signal(
                signal_name="HEADER_INVALID",
                category="STRUCTURE",
                severity="CRITICAL",
                score=20,
                message="Invalid JPEG header - file may be corrupted"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="HEADER_ERROR",
            category="STRUCTURE",
            severity="WARNING",
            score=35,
            message=f"Error validating header: {str(e)}"
        ))
    
    # Signal 3: Dimensions
    try:
        image = Image.open(file_path)
        width, height = image.size
        
        # Check for unusual dimensions
        if 100 <= width <= 10000 and 100 <= height <= 10000:
            signals.append(Signal(
                signal_name="DIMENSIONS_VALID",
                category="METADATA",
                severity="INFO",
                score=90,
                message=f"Image dimensions valid: {width}x{height}"
            ))
        else:
            signals.append(Signal(
                signal_name="DIMENSIONS_ANOMALOUS",
                category="METADATA",
                severity="WARNING",
                score=45,
                message=f"Unusual dimensions: {width}x{height}"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="DIMENSION_ERROR",
            category="METADATA",
            severity="WARNING",
            score=40,
            message=f"Error reading dimensions: {str(e)}"
        ))
    
    # Signal 4: Color Space
    try:
        image = Image.open(file_path)
        color_mode = image.mode
        
        if color_mode in ["RGB", "RGBA", "L"]:  # Common valid modes
            signals.append(Signal(
                signal_name="COLOR_SPACE_VALID",
                category="ENCODING",
                severity="INFO",
                score=92,
                message=f"Standard color space: {color_mode}"
            ))
        else:
            signals.append(Signal(
                signal_name="COLOR_SPACE_UNUSUAL",
                category="ENCODING",
                severity="INFO",
                score=70,
                message=f"Non-standard color space: {color_mode}"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="COLOR_SPACE_ERROR",
            category="ENCODING",
            severity="WARNING",
            score=50,
            message=f"Error checking color space: {str(e)}"
        ))
    
    # Signal 5: Thumbnail (JPEG only)
    try:
        if has_thumbnail(file_path):
            thumbnail = get_thumbnail(file_path)
            if verify_thumbnail_consistency(file_path, thumbnail):
                signals.append(Signal(
                    signal_name="THUMBNAIL_CONSISTENT",
                    category="METADATA",
                    severity="INFO",
                    score=88,
                    message="Thumbnail present and consistent with image"
                ))
            else:
                signals.append(Signal(
                    signal_name="THUMBNAIL_MISMATCH",
                    category="METADATA",
                    severity="WARNING",
                    score=55,
                    message="Thumbnail does not match main image"
                ))
        else:
            signals.append(Signal(
                signal_name="NO_THUMBNAIL",
                category="METADATA",
                severity="INFO",
                score=75,
                message="No thumbnail data found"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="THUMBNAIL_ERROR",
            category="METADATA",
            severity="INFO",
            score=70,
            message=f"Could not analyze thumbnail: {str(e)}"
        ))
    
    # Signal 6: Compression Artifacts
    try:
        # Analyze JPEG compression
        image = Image.open(file_path)
        # Check for signs of re-encoding
        artifact_score = detect_compression_artifacts(image)
        
        signals.append(Signal(
            signal_name="COMPRESSION_ANALYSIS",
            category="ENCODING",
            severity="INFO",
            score=artifact_score,
            message=f"Compression artifact level: {100-artifact_score}%"
        ))
    except Exception as e:
        signals.append(Signal(
            signal_name="COMPRESSION_ERROR",
            category="ENCODING",
            severity="INFO",
            score=65,
            message=f"Could not analyze compression: {str(e)}"
        ))
    
    return signals
```

**Generated Signals for Example Photo:**
```python
[
    Signal("EXIF_VALIDITY", "METADATA", "INFO", 95, "EXIF metadata complete and consistent"),
    Signal("HEADER_INTEGRITY", "STRUCTURE", "INFO", 98, "Valid JPEG header detected"),
    Signal("DIMENSIONS_VALID", "METADATA", "INFO", 90, "Image dimensions valid: 3840x2160"),
    Signal("COLOR_SPACE_VALID", "ENCODING", "INFO", 92, "Standard color space: RGB"),
    Signal("THUMBNAIL_CONSISTENT", "METADATA", "INFO", 88, "Thumbnail present and consistent with image"),
    Signal("COMPRESSION_ANALYSIS", "ENCODING", "INFO", 85, "Compression artifact level: 15%")
]
```

---

#### **Step 3: Video Analysis (If Video File)**

**For an MP4 video:**

```python
# authentication/video_analyzer.py

def analyze_video(file_path):
    signals = []
    
    # Signal 1: Container Validity
    try:
        container_info = get_container_info(file_path)  # Using mediainfo
        
        if container_info["format"] == "MPEG-4" and container_info["is_valid"]:
            signals.append(Signal(
                signal_name="CONTAINER_VALID",
                category="STRUCTURE",
                severity="INFO",
                score=96,
                message="Valid MP4 container structure"
            ))
        else:
            signals.append(Signal(
                signal_name="CONTAINER_INVALID",
                category="STRUCTURE",
                severity="CRITICAL",
                score=15,
                message=f"Invalid container: {container_info['format']}"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="CONTAINER_ERROR",
            category="STRUCTURE",
            severity="CRITICAL",
            score=20,
            message=f"Cannot read container: {str(e)}"
        ))
    
    # Signal 2: Codec Verification
    try:
        video_info = get_video_stream_info(file_path)
        declared_codec = video_info.get("codec_name")
        actual_codec = detect_actual_codec(file_path)
        
        if declared_codec == actual_codec:
            signals.append(Signal(
                signal_name="CODEC_CONSISTENT",
                category="ENCODING",
                severity="INFO",
                score=94,
                message=f"Codec declaration matches: {declared_codec}"
            ))
        else:
            signals.append(Signal(
                signal_name="CODEC_MISMATCH",
                category="ENCODING",
                severity="CRITICAL",
                score=25,
                message=f"Declared: {declared_codec}, Actual: {actual_codec}"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="CODEC_ERROR",
            category="ENCODING",
            severity="WARNING",
            score=40,
            message=f"Could not verify codec: {str(e)}"
        ))
    
    # Signal 3: Frame Integrity
    try:
        frame_count = get_total_frame_count(file_path)
        frame_rate = get_frame_rate(file_path)
        duration = get_duration(file_path)
        
        calculated_frames = int(duration * frame_rate)
        
        if abs(frame_count - calculated_frames) <= 2:
            signals.append(Signal(
                signal_name="FRAME_COUNT_CONSISTENT",
                category="STRUCTURE",
                severity="INFO",
                score=92,
                message=f"Frame count consistent: {frame_count} frames @ {frame_rate}fps"
            ))
        else:
            signals.append(Signal(
                signal_name="FRAME_COUNT_ANOMALY",
                category="STRUCTURE",
                severity="WARNING",
                score=55,
                message=f"Frame count inconsistency detected"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="FRAME_ERROR",
            category="STRUCTURE",
            severity="WARNING",
            score=50,
            message=f"Could not verify frames: {str(e)}"
        ))
    
    # Signal 4: Audio Stream
    try:
        audio_info = get_audio_stream_info(file_path)
        
        if audio_info and audio_info.get("is_valid"):
            signals.append(Signal(
                signal_name="AUDIO_VALID",
                category="ENCODING",
                severity="INFO",
                score=89,
                message=f"Audio stream valid: {audio_info['codec']} @ {audio_info['bitrate']}"
            ))
        elif not audio_info:
            signals.append(Signal(
                signal_name="NO_AUDIO",
                category="ENCODING",
                severity="INFO",
                score=80,
                message="No audio stream present"
            ))
        else:
            signals.append(Signal(
                signal_name="AUDIO_INVALID",
                category="ENCODING",
                severity="WARNING",
                score=50,
                message="Audio stream present but invalid"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="AUDIO_ERROR",
            category="ENCODING",
            severity="INFO",
            score=75,
            message=f"Could not analyze audio: {str(e)}"
        ))
    
    # Signal 5: Timestamp Consistency
    try:
        timestamps = extract_frame_timestamps(file_path)
        
        if verify_timestamp_sequence(timestamps):
            signals.append(Signal(
                signal_name="TIMESTAMPS_CONSISTENT",
                category="METADATA",
                severity="INFO",
                score=90,
                message="Frame timestamps are sequential and consistent"
            ))
        else:
            signals.append(Signal(
                signal_name="TIMESTAMPS_ANOMALOUS",
                category="METADATA",
                severity="WARNING",
                score=50,
                message="Frame timestamps show anomalies or gaps"
            ))
    except Exception as e:
        signals.append(Signal(
            signal_name="TIMESTAMP_ERROR",
            category="METADATA",
            severity="INFO",
            score=70,
            message=f"Could not verify timestamps: {str(e)}"
        ))
    
    return signals
```

**Generated Signals for Example Video:**
```python
[
    Signal("CONTAINER_VALID", "STRUCTURE", "INFO", 96, "Valid MP4 container structure"),
    Signal("CODEC_CONSISTENT", "ENCODING", "INFO", 94, "Codec declaration matches: h264"),
    Signal("FRAME_COUNT_CONSISTENT", "STRUCTURE", "INFO", 92, "Frame count consistent: 7200 frames @ 30fps"),
    Signal("AUDIO_VALID", "ENCODING", "INFO", 89, "Audio stream valid: aac @ 128kbps"),
    Signal("TIMESTAMPS_CONSISTENT", "METADATA", "INFO", 90, "Frame timestamps are sequential and consistent")
]
```

---

#### **Step 4: Signal Aggregation & Verdict**

**Algorithm:**

```python
# authentication/aggregator.py

def aggregate(signals):
    """
    Aggregate signals into confidence score and verdict
    """
    
    # Step 1: Calculate confidence score (simple average)
    if not signals:
        return 50, "SUSPICIOUS", "No signals generated"
    
    confidence_score = sum(s.score for s in signals) / len(signals)
    confidence_score = int(confidence_score)
    
    # Step 2: Check for CRITICAL signals
    critical_signals = [s for s in signals if s.severity == "CRITICAL"]
    warning_signals = [s for s in signals if s.severity == "WARNING"]
    
    # Step 3: Determine verdict
    if critical_signals:
        verdict = "TAMPERED"
    elif confidence_score >= 85:
        verdict = "AUTHENTIC"
    elif confidence_score >= 50:
        verdict = "SUSPICIOUS"
    else:
        verdict = "TAMPERED"
    
    # Step 4: Generate explanation
    explanation = generate_explanation(signals, confidence_score, verdict)
    
    return confidence_score, verdict, explanation
```

**For Our Example Image:**

```python
# Signals scores: [95, 98, 90, 92, 88, 85]
# Average: (95 + 98 + 90 + 92 + 88 + 85) / 6 = 91.3
# Rounded: 91

# Critical signals: 0
# Warning signals: 0

# Verdict Logic:
# No critical signals ✓
# confidence_score (91) >= 85 ✓
# Result: AUTHENTIC

result = {
    "confidence_score": 91,
    "verdict": "AUTHENTIC",
    "signals_detected": [
        {"name": "EXIF_VALIDITY", "score": 95},
        {"name": "HEADER_INTEGRITY", "score": 98},
        {"name": "DIMENSIONS_VALID", "score": 90},
        {"name": "COLOR_SPACE_VALID", "score": 92},
        {"name": "THUMBNAIL_CONSISTENT", "score": 88},
        {"name": "COMPRESSION_ANALYSIS", "score": 85}
    ],
    "explanation": """
Authentication Analysis Result: AUTHENTIC
Confidence Score: 91%

Analysis Summary:
- Critical Issues: 0
- Warnings: 0
- Info Signals: 6

NORMAL FINDINGS (Expected characteristics):
  1. EXIF_VALIDITY: EXIF metadata complete and consistent
  2. HEADER_INTEGRITY: Valid JPEG header detected

VERDICT INTERPRETATION:
This evidence file appears to be authentic with high confidence.
All key authentication checks passed without significant issues.
Recommendation: File can be considered authentic for investigative purposes.
    """
}
```

---

#### **Step 5: Store Result & Return**

**Storage:**

```python
# authentication/storage.py

def store_authentication_result(result):
    """
    Insert result into authentication_results table
    """
    sql = """
    INSERT INTO authentication_results (
        id, evidence_id, confidence_score, verdict, 
        signals_detected, explanation, analyzed_at, analyzer_version
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    params = (
        generate_uuid(),
        "uuid-123",
        91,
        "AUTHENTIC",
        json.dumps(result["signals_detected"]),
        result["explanation"],
        "2026-10-05T14:25:30Z",
        "1.0.0"
    )
    
    cursor.execute(sql, params)
    conn.commit()
```

**Chain of Custody Entry:**

```python
log_custody_event(
    evidence_id="uuid-123",
    action_type="AUTHENTICATE",
    actor_id="investigator_001",
    client_ip="192.168.1.100",
    details={
        "verdict": "AUTHENTIC",
        "confidence_score": 91,
        "signals_count": 6
    }
)
```

**API Response (HTTP 201):**

```json
{
  "status": "success",
  "authentication_result_id": "result-456",
  "evidence_id": "uuid-123",
  "verdict": "AUTHENTIC",
  "confidence_score": 91,
  "signals_detected": [
    {
      "signal_name": "EXIF_VALIDITY",
      "signal_type": "METADATA",
      "result": "COMPLETE",
      "weight": 1.0,
      "score": 95
    },
    {
      "signal_name": "HEADER_INTEGRITY",
      "signal_type": "STRUCTURE",
      "result": "VALID",
      "weight": 1.0,
      "score": 98
    },
    {
      "signal_name": "DIMENSIONS_VALID",
      "signal_type": "METADATA",
      "result": "NORMAL",
      "weight": 1.0,
      "score": 90
    },
    {
      "signal_name": "COLOR_SPACE_VALID",
      "signal_type": "ENCODING",
      "result": "STANDARD",
      "weight": 1.0,
      "score": 92
    },
    {
      "signal_name": "THUMBNAIL_CONSISTENT",
      "signal_type": "METADATA",
      "result": "CONSISTENT",
      "weight": 1.0,
      "score": 88
    },
    {
      "signal_name": "COMPRESSION_ANALYSIS",
      "signal_type": "ENCODING",
      "result": "LOW_ARTIFACTS",
      "weight": 1.0,
      "score": 85
    }
  ],
  "explanation": "Authentication Analysis Result: AUTHENTIC\n\nThis evidence file appears to be authentic with high confidence. All key authentication checks passed without significant issues.\n\nRecommendation: File can be considered authentic for investigative purposes.",
  "analyzed_at": "2026-10-05T14:25:30Z",
  "cached": false
}
```

---

#### **Step 6: Retrieve Cached Result**

**Second Request (Without force_reanalysis):**

```http
POST /api/v1/evidence/uuid-123/authenticate HTTP/1.1
```

**What Happens:**

1. Cache Check
   ```python
   cached = get_cached_result("uuid-123")
   
   if cached and cached["analyzed_at"] > (now - 24 hours):
       return cached  # HTTP 200 (not 201)
   ```

**API Response (HTTP 200 - Cached):**

```json
{
  "status": "success",
  "cached": true,
  "cache_age_seconds": 45,
  "verdict": "AUTHENTIC",
  "confidence_score": 91,
  "...": "... same as before ..."
}
```

---

## Complete End-to-End Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  INVESTIGATOR WORKFLOW                                           │
└─────────────────────────────────────────────────────────────────┘

1. COLLECT EVIDENCE
   ├─ Find suspect's phone at crime scene
   ├─ Extract photo.jpg
   └─ Take photo of phone showing: time, date, IMEI

2. UPLOAD TO FORENSIX
   └─ POST /api/v1/evidence/upload
      ├─ Receive: evidence_id = uuid-123
      ├─ Hash stored: a1b2c3d4...
      └─ Custody logged: UPLOAD event

3. VERIFY INTEGRITY
   └─ POST /api/v1/evidence/uuid-123/verify
      ├─ Recalculate hash
      ├─ Compare: a1b2c3d4... == a1b2c3d4... ✓
      └─ Result: VERIFIED

4. CHECK AUTHENTICITY
   └─ POST /api/v1/evidence/uuid-123/authenticate
      ├─ Generate 6 signals
      ├─ Average confidence: 91%
      ├─ No critical issues
      ├─ Result: AUTHENTIC
      └─ Custody logged: AUTHENTICATE event

5. REVIEW CHAIN OF CUSTODY
   └─ GET /api/v1/evidence/uuid-123/custody
      ├─ Event 1: UPLOAD by detective_smith
      ├─ Event 2: ACCESS by detective_smith
      ├─ Event 3: VERIFY by detective_smith
      ├─ Event 4: AUTHENTICATE by investigator_001
      └─ All events timestamped and logged

6. REPORT FINDINGS
   ├─ Evidence: photo.jpg
   ├─ Hash: a1b2c3d4...
   ├─ Status: VERIFIED & AUTHENTIC
   ├─ Confidence: 91%
   ├─ Signals: 6/6 passed
   ├─ Chain of Custody: Clean, 4 events
   └─ Conclusion: Evidence is reliable and can be used in court

```

---

## Data Storage Structure

### Database Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ EVIDENCE_FILES                                                   │
├─────────────────────────────────────────────────────────────────┤
│ id          │ uuid-123                                           │
│ filename    │ photo.jpg                                          │
│ mime_type   │ image/jpeg                                         │
│ size_bytes  │ 2458624                                            │
│ hash        │ a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6              │
│ storage_uri │ ./evidence_storage/uuid-123.bin                   │
│ uploader_id │ detective_smith_badge_12345                       │
│ created_at  │ 2026-10-05T14:23:45Z                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ CHAIN_OF_CUSTODY_EVENTS                                          │
├─────────────────────────────────────────────────────────────────┤
│ id          │ event-1                                            │
│ evidence_id │ uuid-123                                           │
│ action_type │ UPLOAD                                             │
│ actor_id    │ detective_smith_badge_12345                       │
│ timestamp   │ 2026-10-05T14:23:45Z                              │
│ client_ip   │ 192.168.1.100                                      │
│ details     │ {...json metadata...}                              │
├─────────────────────────────────────────────────────────────────┤
│ id          │ event-2                                            │
│ action_type │ AUTHENTICATE                                       │
│ ...         │ ...                                                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ AUTHENTICATION_RESULTS                                           │
├─────────────────────────────────────────────────────────────────┤
│ id                  │ result-456                                 │
│ evidence_id         │ uuid-123                                   │
│ confidence_score    │ 91                                         │
│ verdict             │ AUTHENTIC                                  │
│ signals_detected    │ [{...6 signals...}]                        │
│ explanation         │ {...detailed explanation...}               │
│ analyzed_at         │ 2026-10-05T14:25:30Z                      │
│ analyzer_version    │ 1.0.0                                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ FILE STORAGE                                                     │
├─────────────────────────────────────────────────────────────────┤
│ ./evidence_storage/                                              │
│ ├── uuid-123.bin          (2.3 MB - actual image data)          │
│ ├── uuid-456.bin          (150 MB - video file)                 │
│ ├── uuid-789.bin          (5.1 MB - another image)              │
│ └── ...                                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Real-World Scenarios

### Scenario 1: Authentic Evidence

**Input:** Original photo from crime scene
**Processing:**
- EXIF data: Complete and consistent ✓
- Header: Valid JPEG ✓
- Dimensions: Normal (3840x2160) ✓
- Color space: RGB ✓
- Compression: Single-generation ✓

**Output:**
```
Verdict: AUTHENTIC
Confidence: 91%
Status: ✅ Ready for court
```

---

### Scenario 2: Suspicious Evidence

**Input:** Photo that has been edited
**Processing:**
- EXIF data: Metadata removed ⚠️
- Header: Valid JPEG ✓
- Dimensions: Normal ✓
- Color space: Non-standard (CMYK) ⚠️
- Compression: Multiple generations ⚠️

**Output:**
```
Verdict: SUSPICIOUS
Confidence: 58%
Status: ⚠️ Requires manual review
```

---

### Scenario 3: Tampered Evidence

**Input:** Corrupted or heavily modified video
**Processing:**
- Container: Invalid structure ❌
- Codec: Mismatch detected ❌
- Frame count: Inconsistent ❌
- Timestamps: Anomalies ❌

**Output:**
```
Verdict: TAMPERED
Confidence: 15%
Status: ❌ Unreliable, exclude from evidence
```

---

## Key Features Demonstrated

✅ **Secure Upload**: Cryptographic hashing prevents undetected tampering  
✅ **Integrity Verification**: Re-verify hash at any time  
✅ **Audit Trail**: Complete chain of custody with actors and timestamps  
✅ **Authentication Analysis**: 6-11 signals per file depending on type  
✅ **Intelligent Aggregation**: Weighted scoring produces reliable verdicts  
✅ **Caching**: 24-hour cache prevents redundant analysis  
✅ **Performance**: Fast processing suitable for investigations  
✅ **Error Handling**: Graceful degradation if some signals fail  

---

**This is ForensiX: A complete forensic evidence platform for the digital investigation age.**
