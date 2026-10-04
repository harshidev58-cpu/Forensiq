# Integration Guide: Authentication Engine & Upload & Fingerprint

## Overview

The Authentication Engine module is designed as a **non-invasive extension** of the Upload & Fingerprint module. It adds new capabilities without modifying existing database tables, endpoints, or business logic.

## No Duplicated Tables

The Authentication Engine **reuses existing tables**:

### evidence_records (Used As-Is)
```sql
-- Existing table - NO CHANGES
evidence_records (
    id TEXT PRIMARY KEY,
    original_filename TEXT,
    mime_type TEXT,
    file_size INTEGER,
    sha256_hash TEXT,
    uploader_id TEXT,
    collection_method TEXT,
    upload_timestamp TEXT,
    created_at DATETIME,
    ... other fields ...
)

-- Authentication Engine reads from:
-- - mime_type: to determine Image vs. Video analyzer
-- - sha256_hash: for comparison during analysis
-- - file size: to check 1 GB limit
-- - uploader_id: optional actor_id fallback
```

### chain_of_custody_events (Extended, Not Modified)
```sql
-- Existing table - NO SCHEMA CHANGES
chain_of_custody_events (
    id UUID PRIMARY KEY,
    evidence_id UUID (FK),
    action_type TEXT,        -- "AUTHENTICATE" is NEW action type (value)
    actor_id TEXT,           -- Now populated from request
    timestamp TEXT,
    client_ip TEXT,          -- Now used for authentication requests
    user_agent TEXT,         -- Now used for authentication requests
    details JSON             -- Now includes verdict, confidence_score
)

-- Authentication Engine adds:
-- - action_type: "AUTHENTICATE" (new value, table not modified)
-- - Populates existing fields: actor_id, client_ip, user_agent
-- - Stores in existing details JSON: verdict, confidence_score, signal_count
```

### NEW: authentication_results Table Only

```sql
-- ONLY NEW TABLE ADDED
authentication_results (
    id UUID PRIMARY KEY,
    evidence_id UUID NOT NULL UNIQUE,  -- FK to evidence_records
    confidence_score INT,              -- 0-100
    verdict TEXT,                       -- AUTHENTIC|SUSPICIOUS|TAMPERED
    signals_detected TEXT,              -- JSON array of signals
    explanation TEXT,
    analyzed_at TEXT,
    analyzer_version TEXT,
    created_at DATETIME,
    updated_at DATETIME
)
```

## No Duplicated Endpoints

The Authentication Engine **adds new endpoints** without touching existing ones:

### Existing Endpoints (Unchanged)
```
POST /api/v1/evidence/upload
GET /api/v1/evidence/{evidence_id}
GET /api/v1/evidence/{evidence_id}/download
POST /api/v1/evidence/{evidence_id}/verify
GET /api/v1/evidence/{evidence_id}/custody
```

### NEW Endpoints Added
```
POST /api/v1/evidence/{evidence_id}/authenticate       -- NEW
GET /api/v1/evidence/{evidence_id}/authentication      -- NEW
```

## Data Flow: How They Work Together

### Scenario 1: Upload and Authenticate Evidence

```
Step 1: Investigator uploads evidence (Upload & Fingerprint)
├─ POST /api/v1/evidence/upload
├─ Stores file in ./evidence_storage/{uuid}.ext
├─ Creates record in evidence_records
├─ Logs "UPLOAD" in chain_of_custody_events
└─ Returns evidence_id: "abc123"

Step 2: Investigator requests authentication (NEW)
├─ POST /api/v1/evidence/abc123/authenticate
├─ Retrieves evidence_records entry for abc123
│  ├─ mime_type determines analyzer (Image vs. Video)
│  ├─ file size checked against 1 GB limit
│  └─ file path: ./evidence_storage/{uuid}.ext
├─ Runs Image or Video Analyzer based on mime_type
├─ Generates signals and verdict
├─ Stores result in authentication_results
├─ Logs "AUTHENTICATE" in chain_of_custody_events with verdict
└─ Returns confidence_score, verdict, signals_detected

Step 3: Investigator reviews chain of custody (Existing endpoint, extended view)
├─ GET /api/v1/evidence/abc123/custody
├─ Returns events including:
│  ├─ UPLOAD (original upload)
│  ├─ ACCESS (if record was retrieved)
│  ├─ VERIFY (if integrity was checked)
│  └─ AUTHENTICATE (NEW - with verdict and score) ← NEW
└─ Provides complete audit trail
```

## Database Schema: Clean Integration

```
Before Authentication Engine:
┌─────────────────────────────────────┐
│      evidence_records               │
│  (Upload & Fingerprint)             │
├─────────────────────────────────────┤
│ ├─ evidence_files data              │
│ ├─ SHA-256 hash                     │
│ ├─ EXIF/video metadata              │
│ └─ file path & storage info         │
└─────────────────────────────────────┘
            │
            │ (FK)
            ↓
┌─────────────────────────────────────┐
│  chain_of_custody_events            │
│  (Upload & Fingerprint)             │
├─────────────────────────────────────┤
│ ├─ UPLOAD events                    │
│ ├─ ACCESS events                    │
│ └─ VERIFY events                    │
└─────────────────────────────────────┘


After Authentication Engine (Non-Invasive Addition):
┌─────────────────────────────────────┐
│      evidence_records               │
│  (Upload & Fingerprint)             │
├─────────────────────────────────────┤
│ ├─ evidence_files data              │
│ ├─ SHA-256 hash                     │
│ ├─ EXIF/video metadata              │
│ └─ file path & storage info         │
└─────────────────────────────────────┘
            │
            ├─────────────┐
            │ (FK)        │ (FK)
            ↓             ↓
    ┌──────────────────────────────┐   ┌─────────────────────────────────┐
    │ chain_of_custody_events      │   │ authentication_results (NEW)    │
    │ (Upload & Fingerprint)       │   │ (Authentication Engine)         │
    ├──────────────────────────────┤   ├─────────────────────────────────┤
    │ ├─ UPLOAD events             │   │ ├─ confidence_score (0-100)     │
    │ ├─ ACCESS events             │   │ ├─ verdict (3 values)           │
    │ ├─ VERIFY events             │   │ ├─ signals_detected (JSON)      │
    │ └─ AUTHENTICATE events (NEW) │   │ ├─ explanation (text)           │
    └──────────────────────────────┘   │ └─ analyzer_version             │
                                        └─────────────────────────────────┘
```

## Configuration Changes: Minimal

### Before: config.py (Upload & Fingerprint)
```python
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_BATCH_FILES = 100
MAX_BATCH_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', ... 'csv'}
MIME_TYPE_MAP = { 'jpg': 'image/jpeg', ... }
# ... other constants
```

### After: config.py (Extended, Not Replaced)
```python
# EXISTING CONSTANTS (unchanged)
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_BATCH_FILES = 100
MAX_BATCH_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', ... 'csv'}
MIME_TYPE_MAP = { 'jpg': 'image/jpeg', ... }

# NEW CONSTANTS (Authentication Engine)
AUTHENTICATION_TIMEOUT = 300  # 5 minutes
MAX_AUTH_FILE_SIZE = 1 * 1024 * 1024 * 1024  # 1 GB
ANALYZER_VERSION = "1.0.0"
SUPPORTED_AUTH_TYPES = {"image/*", "video/*"}
```

No existing constants are modified—only new ones are added.

## Directory Structure: Clean Addition

```
CYbs/
├── src/forensix/
│   ├── app.py                          (ADD new endpoints, import auth module)
│   ├── config.py                       (ADD new constants)
│   ├── upload_handler.py               (UNCHANGED)
│   ├── verification.py                 (UNCHANGED)
│   ├── hashing.py                      (UNCHANGED)
│   ├── custody.py                      (UNCHANGED)
│   ├── metadata.py                     (UNCHANGED)
│   ├── timestamps.py                   (UNCHANGED)
│   ├── validation.py                   (UNCHANGED)
│   └── authentication/                 (NEW directory)
│       ├── __init__.py
│       ├── analyzer.py                 (Main orchestrator)
│       ├── image_analyzer.py           (Image-specific checks)
│       ├── video_analyzer.py           (Video-specific checks)
│       ├── aggregator.py               (Signal aggregation)
│       ├── models.py                   (Signal and Result models)
│       ├── storage.py                  (Database operations)
│       └── errors.py                   (Authentication-specific exceptions)
│
├── tests/
│   ├── test_upload_handler.py          (UNCHANGED)
│   ├── test_verification.py            (UNCHANGED)
│   ├── test_hashing.py                 (UNCHANGED)
│   └── authentication/                 (NEW directory)
│       ├── test_image_analyzer.py
│       ├── test_video_analyzer.py
│       ├── test_aggregator.py
│       ├── test_endpoints.py
│       └── test_integration.py
│
├── database_setup.py                   (ADD authentication_results table migration)
└── forensix.db                         (ADD authentication_results table)
```

## API Version Compatibility

The Authentication Engine uses the same API versioning scheme:

```
Existing endpoints: /api/v1/evidence/*
New endpoints:      /api/v1/evidence/{id}/authenticate    ← Same version
                    /api/v1/evidence/{id}/authentication   ← Same version
```

This ensures:
- Clients don't need to update version in URLs
- Single API version for both modules
- Backward compatibility guaranteed

## Dependency Flow

```
Upload & Fingerprint Module
    ↓
    └─→ Creates evidence_records + chain_of_custody_events
            ↓
            └─→ Authentication Engine reads these tables
                    ├─→ Queries evidence_records for file info
                    ├─→ Reads file from ./evidence_storage/
                    └─→ Writes to authentication_results (NEW)
                        └─→ Extends chain_of_custody_events (new action type)
```

Authentication Engine is **read-only** for Upload & Fingerprint tables:
- Does NOT modify evidence_records
- Does NOT modify chain_of_custody_events structure
- ONLY ADDS: authentication_results table
- ONLY EXTENDS: chain_of_custody_events values

## Migration Path

### Step 1: Database Migration
```bash
# Run migration to add authentication_results table
python -c "
from forensix.authentication.storage import migrate_authentication_schema
migrate_authentication_schema()
"
```

### Step 2: Configuration
```python
# In config.py, add new constants (done in this spec)
# Existing constants remain unchanged
```

### Step 3: Application Update
```python
# In app.py:
from forensix.authentication.analyzer import AuthenticationAnalyzer

# Add new routes (endpoints 7.1 and 7.2 from tasks)
@app.post("/api/v1/evidence/{evidence_id}/authenticate")
async def authenticate_evidence(...):
    ...

@app.get("/api/v1/evidence/{evidence_id}/authentication")
async def get_authentication_result(...):
    ...
```

### Step 4: Testing
- Run existing Upload & Fingerprint tests (should all pass unchanged)
- Run new Authentication Engine tests
- Run integration tests (upload → authenticate → retrieve)

## Backward Compatibility Guarantee

✓ Existing database tables remain unchanged  
✓ Existing API endpoints unchanged  
✓ Existing client code continues to work  
✓ No breaking changes to Upload & Fingerprint module  
✓ New functionality is purely additive  

A client using only Upload & Fingerprint will not be affected by Authentication Engine installation.

## Summary

The Authentication Engine achieves **clean separation of concerns** by:

1. **Reading**: From existing evidence_records and chain_of_custody_events tables
2. **Writing**: To new authentication_results table ONLY
3. **Extending**: Chain of custody with new action type (AUTHENTICATE) without schema changes
4. **Adding**: New endpoints without touching existing ones
5. **Isolating**: All authentication code in new src/forensix/authentication/ directory

Result: A modular, maintainable extension that forensic investigators can deploy alongside Upload & Fingerprint without any operational complexity.

