# ForensiX - System Architecture Diagrams

## 1. High-Level System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      FORENSIC INVESTIGATOR                      │
│                   (Command Line / API Client)                   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   REST API      │
                    │  (FastAPI)      │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼─────┐      ┌──────▼──────┐      ┌──────▼──────┐
   │  UPLOAD   │      │   VERIFY    │      │ AUTHENTICATE│
   │  HANDLER  │      │             │      │             │
   └────┬─────┘      └──────┬──────┘      └──────┬──────┘
        │                   │                    │
   ┌────▼─────────┐    ┌────▼───────┐      ┌────▼─────────┐
   │ • Hash Gen   │    │ • Hash Calc │     │ • Image      │
   │ • Metadata   │    │ • Verify    │     │   Analyzer   │
   │ • Storage    │    │             │     │ • Video      │
   │ • Custody    │    │             │     │   Analyzer   │
   └────┬─────────┘    └────┬───────┘      └────┬─────────┘
        │                   │                    │
        └───────────────────┼────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  DATABASE &    │
                    │  FILE STORAGE  │
                    │                │
                    │ • SQLite DB    │
                    │ • Evidence     │
                    │   Storage Dir  │
                    └────────────────┘
```

---

## 2. Data Flow - Upload & Verify

```
UPLOAD FLOW:
═══════════════════════════════════════════════════════════════

┌─────────────────┐
│  Client uploads │
│   evidence.jpg  │
└────────┬────────┘
         │
         ▼
    ┌────────────┐
    │ Validation │◄─── Check file exists, size, type
    └────┬───────┘
         │
         ▼
    ┌─────────────────┐
    │ Calculate Hash  │◄─── SHA-256
    │   (a1b2c3...)   │     cryptographic signature
    └────┬────────────┘
         │
         ▼
    ┌──────────────────┐
    │ Extract Metadata │◄─── EXIF for photos
    │                  │     Duration, codecs for video
    └────┬─────────────┘
         │
         ▼
    ┌──────────────────┐
    │ Store File to    │◄─── ./evidence_storage/uuid.bin
    │ ./evidence_      │     Keep original format
    │ storage/         │
    └────┬─────────────┘
         │
         ▼
    ┌──────────────────────┐
    │ Create DB Record     │◄─── INSERT evidence_files
    │ evidence_files       │     - id, hash, metadata
    └────┬─────────────────┘
         │
         ▼
    ┌──────────────────────┐
    │ Log Custody Event    │◄─── INSERT chain_of_custody
    │ UPLOAD action        │     - actor, timestamp, IP
    └────┬─────────────────┘
         │
         ▼
    ┌─────────────────┐
    │ Return Response │◄─── evidence_id, hash, status
    └─────────────────┘


VERIFY FLOW:
═══════════════════════════════════════════════════════════════

┌────────────────────┐
│ Client provides:   │
│ - evidence_id      │
│ - provided_hash    │
└────────┬───────────┘
         │
         ▼
    ┌─────────────────┐
    │ Query Database  │◄─── SELECT evidence_files
    │ Get file path   │
    └────┬────────────┘
         │
         ▼
    ┌──────────────────┐
    │ Read File from   │◄─── Read from storage
    │ Storage          │
    └────┬─────────────┘
         │
         ▼
    ┌──────────────────┐
    │ Recalculate Hash │◄─── SHA-256 of file content
    │                  │
    └────┬─────────────┘
         │
         ▼
    ┌──────────────────────┐
    │ Compare Hashes       │◄─── original_hash == provided_hash
    │                      │
    └────┬─────────────────┘
         │
         ▼
    ┌──────────────────────┐
    │ Log Custody Event    │◄─── VERIFY action
    │ VERIFY action        │
    └────┬─────────────────┘
         │
         ▼
    ┌────────────────────────┐
    │ Return Verification    │◄─── verified: true/false
    │ Result                 │     match: true/false
    └────────────────────────┘
```

---

## 3. Data Flow - Authentication Analysis

```
AUTHENTICATION FLOW:
═══════════════════════════════════════════════════════════════

┌─────────────────────────┐
│ Client requests:        │
│ POST /authenticate      │
│ evidence_id: uuid-123   │
└────────┬────────────────┘
         │
         ▼
    ┌──────────────────────────┐
    │ Check Cache              │◄─── Is result < 24hrs old?
    │ (unless force_reanalysis)│
    └────┬─────────┬───────────┘
         │         │
      YES│         │NO
         ▼         ▼
    ┌────────┐  ┌──────────────────┐
    │ Return │  │ Retrieve File    │
    │ Cached │  │ from Storage     │
    │ Result │  └────┬─────────────┘
    │ (200)  │       │
    └────────┘       ▼
                ┌─────────────────────┐
                │ Check MIME Type     │◄─── image/* or video/*?
                └────┬────────┬───────┘
                     │        │
                  IMG │        │ VIDEO
                     ▼        ▼
            ┌─────────────────────────────┐
            │  IMAGE ANALYZER             │
            │  Generate 6+ Signals:       │
            │  • EXIF_VALIDITY            │
            │  • HEADER_INTEGRITY         │
            │  • DIMENSIONS_VALID         │
            │  • COLOR_SPACE_VALID        │
            │  • THUMBNAIL_CONSISTENT     │
            │  • COMPRESSION_ANALYSIS     │
            └────┬────────────────────────┘
                 │
            ┌────┴──────────────────────────────┐
            │  VIDEO ANALYZER                    │
            │  Generate 5+ Signals:              │
            │  • CONTAINER_VALID                 │
            │  • CODEC_CONSISTENT                │
            │  • FRAME_INTEGRITY                 │
            │  • AUDIO_VALID                     │
            │  • TIMESTAMPS_CONSISTENT           │
            └─────────┬──────────────────────────┘
                      │
                      ▼
            ┌──────────────────────────┐
            │ Signal Aggregation        │
            │                           │
            │ Calculate Average Score   │
            │ (all signals combined)    │
            │                           │
            │ Apply Verdict Rules:      │
            │ ≥85% + NO CRITICAL        │
            │   → AUTHENTIC             │
            │ 50-84%                    │
            │   → SUSPICIOUS            │
            │ <50% + CRITICAL           │
            │   → TAMPERED              │
            └────┬─────────────────────┘
                 │
                 ▼
        ┌────────────────────────┐
        │ Generate Explanation   │◄─── Human-readable summary
        │ (max 5000 chars)       │     • Key signals
        │                        │     • Verdict interpretation
        └────┬───────────────────┘
             │
             ▼
        ┌────────────────────────┐
        │ Store in Database      │◄─── INSERT authentication_results
        │ authentication_results │
        └────┬───────────────────┘
             │
             ▼
        ┌────────────────────────┐
        │ Log Custody Event      │◄─── AUTHENTICATE action
        │ AUTHENTICATE action    │     verdict, confidence_score
        └────┬───────────────────┘
             │
             ▼
        ┌────────────────────────┐
        │ Return Result (201)    │◄─── verdict, confidence_score
        │ New Analysis           │     signals, explanation
        └────────────────────────┘
```

---

## 4. Signal Generation - Image Analysis

```
IMAGE FILE (JPEG/PNG/GIF)
│
├─ SIGNAL 1: EXIF VALIDITY
│  ├─ Extract EXIF metadata
│  ├─ Check for DateTimeOriginal
│  ├─ Compare with file modification time
│  └─ Score: 95 (complete) → 60 (missing) → 40 (inconsistent)
│
├─ SIGNAL 2: HEADER INTEGRITY
│  ├─ Read first 4 bytes
│  ├─ Check magic number (0xFFD8FFEO for JPEG)
│  └─ Score: 98 (valid) → 20 (corrupt)
│
├─ SIGNAL 3: DIMENSIONS
│  ├─ Parse image dimensions
│  ├─ Check if reasonable (100-10000 pixels)
│  └─ Score: 90 (normal) → 45 (anomalous)
│
├─ SIGNAL 4: COLOR SPACE
│  ├─ Detect color mode (RGB, RGBA, CMYK, etc)
│  ├─ Check if standard (RGB, grayscale)
│  └─ Score: 92 (standard) → 70 (unusual)
│
├─ SIGNAL 5: THUMBNAIL
│  ├─ Check if thumbnail exists (JPEG)
│  ├─ Compare thumbnail with image
│  └─ Score: 88 (consistent) → 75 (missing) → 55 (mismatch)
│
└─ SIGNAL 6: COMPRESSION
   ├─ Analyze JPEG compression
   ├─ Look for re-encoding artifacts
   └─ Score: 85 (single-gen) → 50 (multiple-gen)

AGGREGATE: (95+98+90+92+88+85)/6 = 91 → AUTHENTIC
```

---

## 5. Signal Generation - Video Analysis

```
VIDEO FILE (MP4/MOV/AVI/MKV)
│
├─ SIGNAL 1: CONTAINER VALIDITY
│  ├─ Parse container headers
│  ├─ Check moov/mdat atoms
│  └─ Score: 96 (valid) → 15 (invalid)
│
├─ SIGNAL 2: CODEC CONSISTENCY
│  ├─ Check declared codec
│  ├─ Detect actual codec
│  └─ Score: 94 (match) → 25 (mismatch)
│
├─ SIGNAL 3: FRAME INTEGRITY
│  ├─ Extract total frame count
│  ├─ Extract frame rate
│  ├─ Calculate expected: duration × fps
│  └─ Score: 92 (consistent) → 55 (anomaly)
│
├─ SIGNAL 4: AUDIO VALIDITY
│  ├─ Check audio stream (if exists)
│  ├─ Verify codec and bitrate
│  └─ Score: 89 (valid) → 75 (missing) → 50 (invalid)
│
└─ SIGNAL 5: TIMESTAMPS
   ├─ Extract frame timestamps
   ├─ Check if sequential
   └─ Score: 90 (sequential) → 50 (anomalies)

AGGREGATE: (96+94+92+89+90)/5 = 92.2 → AUTHENTIC
```

---

## 6. Verdict Determination Logic

```
┌─────────────────────────────┐
│ Calculate Confidence Score   │
│ (average of all signals)    │
└──────────────┬──────────────┘
               │
        ┌──────▼──────┐
        │ confidence  │
        │     score   │
        └──────┬──────┘
               │
    ┌──────────┴──────────┐
    │                     │
    ▼                     ▼
┌─────────────┐    ┌──────────────┐
│ Check for   │    │ Apply Thresholds
│ CRITICAL    │    │
│ Signals?    │    │ score >= 85?
└──┬────┬─────┘    │
   │    │          │ score >= 50?
YES│    │NO        └────┬──┬──┬─┐
   │    │               │  │  │ │
   │    ▼               ▼  ▼  ▼ ▼
   │  ┌─────────────┐ ┌─┐┌──┐┌──┐
   │  │ Has signals │ │ ││  ││NO│
   │  │ to check?   │ │ ││  │└──┘
   │  └─────────────┘ │Y││Y │
   │                  │E││E │
   │                  │S││S │
   ▼                  │ ││  │
┌────────────┐        │ ││  │
│ TAMPERED   │        │ ││  │
│ (forced by │        │ ││  │
│ CRITICAL)  │        │ ││  │
└────────────┘        │ ││  │
                      ▼ ▼│  │
                   ┌────────┐│
                   │AUTHENTIC││
                   │ (≥85)   ││
                   └────────┘│
                      ▲ SUSPICIOUS
                      │ (50-84)
                      │
                  ┌───┴────┐
                  │         │
                  ▼         ▼
              TAMPERED  AUTHENTIC
              (<50%)     (≥85%)
```

---

## 7. Confidence Score Mapping

```
CONFIDENCE SCALE:
═════════════════════════════════════════════════════════════

100% ┃ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
90%  ┃ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ AUTHENTIC ░░░░░
85%  ┃ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ THRESHOLD  ░░░░░
80%  ┃ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
     ┃
70%  ┃ ╔════════════════════════════════════════════════════╗
60%  ┃ ║         SUSPICIOUS / AMBIGUOUS                     ║
50%  ┃ ║  (Requires Manual Review)                          ║
     ┃ ╚════════════════════════════════════════════════════╝
40%  ┃ ┌─────────────────────────────────────────────────┐
30%  ┃ │ TAMPERED / UNRELIABLE                           │
20%  ┃ │ (Do not use as evidence)                        │
10%  ┃ └─────────────────────────────────────────────────┘
 0%  ┃
```

---

## 8. Chain of Custody Timeline

```
TIME ──────────────────────────────────────────────────────────►

T₁ │ UPLOAD
   │ ├─ File: evidence.jpg
   │ ├─ Uploader: detective_smith_badge_12345
   │ ├─ IP: 192.168.1.100
   │ └─ Hash: a1b2c3d4e5f6...
   │
T₂ │ ACCESS
   │ ├─ By: detective_smith_badge_12345
   │ ├─ IP: 192.168.1.100
   │ └─ Purpose: View evidence record
   │
T₃ │ VERIFY
   │ ├─ By: detective_smith_badge_12345
   │ ├─ Result: VERIFIED
   │ └─ Hash Match: ✓
   │
T₄ │ AUTHENTICATE
   │ ├─ By: investigator_001
   │ ├─ IP: 192.168.1.101
   │ └─ Verdict: AUTHENTIC (91%)
   │
T₅ │ ACCESS
   │ ├─ By: prosecutor_johnson_badge_67890
   │ ├─ IP: 192.168.1.102
   │ └─ Purpose: Prepare for trial
   │

CUSTODY CHAIN STATUS: ✓ INTACT
- No breaks in chain
- All actors identified
- All timestamps recorded
- All actions audited
```

---

## 9. Database Relationships

```
EVIDENCE_FILES
├─ id (UUID)
├─ original_filename
├─ mime_type
├─ file_size_bytes
├─ sha256_hash ◄──────────┐
├─ storage_uri            │
├─ uploader_id            │
├─ collection_method      │
├─ status                 │
├─ created_at             │
└─ updated_at             │
                          │
CHAIN_OF_CUSTODY_EVENTS   │
├─ id (UUID)              │
├─ evidence_id ───────────┼────────┐
├─ action_type            │        │
├─ actor_id               │        │
├─ timestamp              │        │
├─ client_ip              │        │
├─ user_agent             │        │
└─ details (JSON)         │        │
                          │        │
AUTHENTICATION_RESULTS    │        │
├─ id (UUID)              │        │
├─ evidence_id ───────────┼────────┤ (FOREIGN KEY)
├─ confidence_score       │        │
├─ verdict                │        │
├─ signals_detected (JSON)│        │
├─ explanation            │        │
├─ analyzed_at            │        │
└─ analyzer_version       │        │
                          └────────┘
```

---

## 10. Processing Pipeline

```
CLIENT REQUEST
│
├─ INPUT VALIDATION
│  ├─ Check parameters
│  ├─ Sanitize input
│  └─ Verify authentication
│
├─ BUSINESS LOGIC
│  ├─ Query database
│  ├─ Check cache
│  ├─ Route to handler
│  └─ Perform operation
│
├─ DATA PERSISTENCE
│  ├─ Update database
│  ├─ Log events
│  └─ Ensure atomicity
│
├─ ERROR HANDLING
│  ├─ Try-catch blocks
│  ├─ Validation errors
│  ├─ Database errors
│  └─ File system errors
│
└─ RESPONSE GENERATION
   ├─ Format response
   ├─ Set status code
   ├─ Include headers
   └─ Return to client

CLIENT RESPONSE
```

---

## 11. Security Layers

```
┌──────────────────────────────────────────────────────┐
│ LAYER 1: INPUT VALIDATION                            │
│ ├─ Check file size                                   │
│ ├─ Verify MIME type                                  │
│ ├─ Sanitize filename                                 │
│ └─ Validate JSON                                     │
└──────────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────┐
│ LAYER 2: AUTHENTICATION & AUTHORIZATION              │
│ ├─ Verify actor_id                                   │
│ ├─ Check request IP                                  │
│ ├─ Validate user_agent                               │
│ └─ Enforce permissions                               │
└──────────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────┐
│ LAYER 3: DATA PROTECTION                             │
│ ├─ SHA-256 cryptographic hashing                     │
│ ├─ File integrity verification                       │
│ ├─ Parameterized SQL queries                         │
│ └─ Transaction management                            │
└──────────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────┐
│ LAYER 4: AUDIT & LOGGING                             │
│ ├─ Chain of custody events                           │
│ ├─ Actor tracking                                    │
│ ├─ IP address logging                                │
│ └─ Action timestamps                                 │
└──────────────────────────────────────────────────────┘
```

---

## 12. Performance Bottlenecks & Optimization

```
OPERATION              │ BASELINE  │ OPTIMIZED │ METHOD
───────────────────────┼───────────┼───────────┼─────────────────
SHA-256 Hash (100MB)   │ 500ms     │ 200ms     │ Buffered I/O
Image Analysis         │ 1500ms    │ 400ms     │ Lazy loading
Video Analysis         │ 5000ms    │ 2000ms    │ Stream parsing
Database Query         │ 50ms      │ 5ms       │ Indexes
Cache Lookup           │ 100ms     │ <1ms      │ In-memory
File I/O (1MB)         │ 100ms     │ 10ms      │ Buffering
Signal Aggregation     │ 50ms      │ 5ms       │ Vectorization
Response JSON Encode   │ 50ms      │ 10ms      │ Native encode

KEY OPTIMIZATIONS:
• Database indexes on: evidence_id, verdict, analyzed_at
• 24-hour result caching
• Buffered file reading (64KB chunks)
• Lazy metadata extraction
• Signal parallel processing
```

---

**ForensiX Architecture: Secure, Scalable, Auditable**
