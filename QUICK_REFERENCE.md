# ForensiX - Quick Reference Guide

## What is ForensiX?

A forensic evidence management and authentication platform that helps investigators:
1. Securely upload evidence files
2. Verify file integrity using cryptography
3. Track who accessed evidence (chain of custody)
4. Authenticate images and videos for tampering

---

## Quick Start

### Install & Run

```bash
# Clone
git clone https://github.com/harshidev58-cpu/Forensiq.git
cd Forensiq

# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python database_setup.py

# Run
python main.py
# API available at http://localhost:5000
```

---

## Core Operations

### 1️⃣ Upload Evidence

```bash
curl -X POST http://localhost:5000/api/v1/evidence/upload \
  -F "file=@photo.jpg" \
  -F "uploader_id=detective_001" \
  -F "collection_method=physical_seizure"
```

**Response:**
```json
{
  "evidence_id": "uuid-123",
  "filename": "photo.jpg",
  "sha256_hash": "a1b2c3d4e5f6...",
  "status": "RECEIVED"
}
```

---

### 2️⃣ Verify File Integrity

```bash
curl -X POST http://localhost:5000/api/v1/evidence/uuid-123/verify \
  -H "Content-Type: application/json" \
  -d '{"provided_hash": "a1b2c3d4e5f6..."}'
```

**Response:**
```json
{
  "verified": true,
  "match": true,
  "status": "VERIFIED"
}
```

---

### 3️⃣ Authenticate File

```bash
curl -X POST http://localhost:5000/api/v1/evidence/uuid-123/authenticate \
  -G -d "force_reanalysis=false" -d "actor_id=investigator_001"
```

**Response:**
```json
{
  "verdict": "AUTHENTIC",
  "confidence_score": 91,
  "signals_detected": [
    {"signal_name": "EXIF_VALIDITY", "score": 95},
    {"signal_name": "HEADER_INTEGRITY", "score": 98},
    {"signal_name": "DIMENSIONS_VALID", "score": 90},
    {"signal_name": "COLOR_SPACE_VALID", "score": 92},
    {"signal_name": "THUMBNAIL_CONSISTENT", "score": 88},
    {"signal_name": "COMPRESSION_ANALYSIS", "score": 85}
  ],
  "explanation": "This evidence file appears to be authentic..."
}
```

---

### 4️⃣ View Chain of Custody

```bash
curl http://localhost:5000/api/v1/evidence/uuid-123/custody
```

**Response:**
```json
{
  "evidence_id": "uuid-123",
  "events": [
    {
      "action_type": "UPLOAD",
      "actor_id": "detective_001",
      "timestamp": "2026-10-05T14:23:45Z",
      "client_ip": "192.168.1.100"
    },
    {
      "action_type": "AUTHENTICATE",
      "actor_id": "investigator_001",
      "timestamp": "2026-10-05T14:25:30Z",
      "client_ip": "192.168.1.101"
    }
  ]
}
```

---

## API Endpoints Reference

### Upload & Fingerprint

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/v1/evidence/upload` | Upload single file |
| `POST` | `/api/v1/evidence/batch/upload` | Batch upload |
| `GET` | `/api/v1/evidence/{id}` | Get file info |
| `GET` | `/api/v1/evidence/{id}/download` | Download file |
| `POST` | `/api/v1/evidence/{id}/verify` | Verify integrity |
| `GET` | `/api/v1/evidence/{id}/custody` | View audit trail |

### Authentication

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/v1/evidence/{id}/authenticate` | Analyze file |
| `GET` | `/api/v1/authentication/{result_id}` | Get result |

---

## Understanding Verdicts

### AUTHENTIC ✅
- **Confidence**: ≥ 85%
- **Meaning**: File appears original and unmodified
- **Action**: Safe to use as evidence in court

### SUSPICIOUS ⚠️
- **Confidence**: 50-84%
- **Meaning**: File shows some anomalies or ambiguities
- **Action**: Requires manual investigation before use

### TAMPERED ❌
- **Confidence**: < 50%
- **Meaning**: File shows signs of modification or corruption
- **Action**: Likely unreliable, exclude from evidence

---

## Understanding Signals

Each signal is a test performed on the file:

### Image Signals
- **EXIF_VALIDITY**: Is EXIF metadata present and correct?
- **HEADER_INTEGRITY**: Is the file header valid?
- **DIMENSIONS_VALID**: Are dimensions reasonable?
- **COLOR_SPACE_VALID**: Is color space standard?
- **THUMBNAIL_CONSISTENT**: Does thumbnail match image?
- **COMPRESSION_ANALYSIS**: How much re-encoding detected?

### Video Signals
- **CONTAINER_VALID**: Is the video container valid?
- **CODEC_CONSISTENT**: Are codecs declared correctly?
- **FRAME_INTEGRITY**: Are frames structurally sound?
- **AUDIO_VALID**: Is audio data valid?
- **TIMESTAMPS_CONSISTENT**: Are frame timestamps sequential?

---

## Database Schema

```sql
-- Evidence files
CREATE TABLE evidence_files (
  id TEXT PRIMARY KEY,
  original_filename TEXT,
  mime_type TEXT,
  file_size_bytes INTEGER,
  sha256_hash TEXT,
  storage_uri TEXT,
  uploader_id TEXT,
  collection_method TEXT,
  status TEXT,
  created_at TEXT,
  updated_at TEXT
);

-- Chain of custody
CREATE TABLE chain_of_custody_events (
  id TEXT PRIMARY KEY,
  evidence_id TEXT,
  action_type TEXT,
  actor_id TEXT,
  timestamp TEXT,
  client_ip TEXT,
  user_agent TEXT,
  details TEXT  -- JSON
);

-- Authentication results
CREATE TABLE authentication_results (
  id TEXT PRIMARY KEY,
  evidence_id TEXT UNIQUE,
  confidence_score INTEGER,
  verdict TEXT,
  signals_detected TEXT,  -- JSON
  explanation TEXT,
  analyzed_at TEXT,
  analyzer_version TEXT
);
```

---

## Common Workflows

### Workflow 1: Upload & Verify

```
Upload → Get Hash → Verify Later → ✓ Confirmed
```

### Workflow 2: Upload & Authenticate

```
Upload → Authenticate → Verdict → Report
```

### Workflow 3: Complete Investigation

```
Upload → Verify → Authenticate → View Custody → Report
```

---

## Error Handling

### Common Errors

| Status | Error | Solution |
|--------|-------|----------|
| 400 | Unsupported file type | Use JPG/PNG for images, MP4/MOV for videos |
| 404 | Evidence not found | Check evidence_id is correct |
| 409 | Concurrent analysis | Wait for first analysis to complete |
| 413 | File too large | Max 1 GB per file |
| 408 | Analysis timeout | File too complex, try again |
| 500 | Server error | Check logs, restart app |

---

## Performance Tips

- **Caching**: Results cached for 24 hours, reuse results if available
- **Batch Upload**: Upload multiple files in one request for efficiency
- **File Size**: Keep files under 500 MB for best performance
- **Network**: Use LAN for faster uploads than WAN

---

## Security Best Practices

✅ Always verify hash after download  
✅ Check chain of custody regularly  
✅ Use strong uploader_id to track access  
✅ Store database backups securely  
✅ Review suspicious authentication verdicts manually  
✅ Never ignore CRITICAL signals  

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_authentication_analyzer.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Result: 215/215 tests passing ✅
```

---

## Configuration

Edit `src/forensix/config.py`:

```python
# File upload
MAX_FILE_SIZE_MB = 500
ALLOWED_MIME_TYPES = {...}

# Authentication
AUTHENTIC_THRESHOLD = 85      # >= 85% = AUTHENTIC
SUSPICIOUS_THRESHOLD = 50     # 50-84% = SUSPICIOUS
# < 50% = TAMPERED

# Performance
AUTHENTICATION_TIMEOUT = 300  # 5 minutes
CACHE_DURATION_HOURS = 24

# Storage
EVIDENCE_STORAGE_PATH = "./evidence_storage"
DATABASE_PATH = "./forensix.db"
```

---

## File Organization

```
ForensiX/
├── src/forensix/
│   ├── app.py                    # Main API
│   ├── authentication/           # Auth module
│   ├── upload_handler.py        # Upload logic
│   ├── hashing.py               # Hash functions
│   ├── custody.py               # Audit logging
│   └── ...
├── tests/                        # 215 test cases
├── evidence_storage/             # Uploaded files
├── forensix.db                   # Database
├── README.md                     # Project overview
└── PLATFORM_WALKTHROUGH.md      # Detailed guide
```

---

## Important Concepts

**Evidence ID**: Unique identifier for each file (UUID)  
**Hash**: SHA-256 cryptographic signature of file  
**Signal**: Individual authenticity check (score 0-100)  
**Verdict**: Final conclusion (AUTHENTIC/SUSPICIOUS/TAMPERED)  
**Chain of Custody**: Audit trail of all file accesses  
**Confidence Score**: Average of all signals (0-100%)  

---

## Getting Help

📖 **Detailed Guide**: Read `PLATFORM_WALKTHROUGH.md`  
📋 **API Docs**: See `AUTHENTICATION_API.md`  
📊 **Status**: Check `PROJECT_STATUS.md`  
💬 **Issues**: https://github.com/harshidev58-cpu/Forensiq/issues  

---

## Key Metrics

- ✅ 215/215 tests passing
- ⚡ <500ms image analysis
- ⚡ <2s video analysis
- 📊 6+ signals per image
- 📊 4+ signals per video
- 💾 1 GB max file size
- ⏱️ 5 minute timeout
- 📅 24 hour cache

---

**ForensiX: The platform for modern forensic investigations**

Last Updated: October 5, 2026
