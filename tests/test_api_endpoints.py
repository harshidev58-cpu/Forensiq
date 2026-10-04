"""
API integration tests for FastAPI upload endpoints.
Tests the HTTP endpoints /evidence/upload and /evidence/upload/batch.
"""

import json
import sqlite3
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.forensix.app import app, get_db_connection
from src.forensix.config import DATABASE_PATH, EVIDENCE_STORAGE_DIR


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def setup_test_env():
    """Set up test environment."""
    # Ensure storage directory exists
    EVIDENCE_STORAGE_DIR.mkdir(exist_ok=True)
    
    # Ensure database exists
    if not DATABASE_PATH.exists():
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from database_setup import create_database
        create_database()
    
    yield
    
    # Cleanup after tests
    # Remove all uploaded files
    for file_path in EVIDENCE_STORAGE_DIR.glob("*.jpg"):
        try:
            file_path.unlink()
        except Exception:
            pass
    for file_path in EVIDENCE_STORAGE_DIR.glob("*.mp4"):
        try:
            file_path.unlink()
        except Exception:
            pass
    for file_path in EVIDENCE_STORAGE_DIR.glob("*.txt"):
        try:
            file_path.unlink()
        except Exception:
            pass


class TestUploadEndpoint:
    """Tests for POST /evidence/upload endpoint."""
    
    def test_upload_single_jpg_success(self, client, setup_test_env):
        """Test successful upload of a single JPG file."""
        jpg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00' + b'\x00' * 100
        
        response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Mobile device extraction"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify response structure
        assert "id" in data
        assert "sha256_hash" in data
        assert "upload_timestamp" in data
        assert "original_filename" in data
        assert "file_size" in data
        
        # Verify response values
        assert data["original_filename"] == "test.jpg"
        assert data["file_size"] == len(jpg_content)
        assert len(data["sha256_hash"]) == 64
        assert len(data["id"]) == 36
        
        # Verify file was stored
        stored_file = EVIDENCE_STORAGE_DIR / f"{data['id']}.jpg"
        assert stored_file.exists()
    
    def test_upload_single_mp4_success(self, client, setup_test_env):
        """Test successful upload of a single MP4 file."""
        mp4_content = b'\x00\x00\x00\x20ftypmp41' + b'\x00' * 100
        
        response = client.post(
            "/evidence/upload",
            files={"file": ("video.mp4", BytesIO(mp4_content), "video/mp4")},
            data={
                "uploader_id": "analyst_001",
                "collection_method": "Security camera footage"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "video.mp4"
        assert data["file_size"] == len(mp4_content)
    
    def test_upload_missing_file(self, client, setup_test_env):
        """Test upload endpoint rejects request with missing file."""
        response = client.post(
            "/evidence/upload",
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_upload_missing_uploader_id(self, client, setup_test_env):
        """Test upload endpoint rejects request with missing uploader_id."""
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "collection_method": "Test collection"
            }
        )
        
        assert response.status_code == 422  # FastAPI validation error
    
    def test_upload_missing_collection_method(self, client, setup_test_env):
        """Test upload endpoint rejects request with missing collection_method."""
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001"
            }
        )
        
        assert response.status_code == 422  # FastAPI validation error
    
    def test_upload_empty_file(self, client, setup_test_env):
        """Test upload endpoint rejects zero-byte files with 400 error."""
        response = client.post(
            "/evidence/upload",
            files={"file": ("empty.jpg", BytesIO(b""), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "0 bytes" in data["detail"]
    
    def test_upload_oversized_file(self, client, setup_test_env):
        """Test upload endpoint rejects files over 500MB with 413 error."""
        # Create content larger than 500MB limit
        large_content = b"x" * (500 * 1024 * 1024 + 1)
        
        response = client.post(
            "/evidence/upload",
            files={"file": ("large.jpg", BytesIO(large_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        assert response.status_code == 413
        data = response.json()
        assert "detail" in data
        assert "exceeds maximum limit" in data["detail"]
    
    def test_upload_unsupported_extension(self, client, setup_test_env):
        """Test upload endpoint rejects unsupported file extensions with 400 error."""
        exe_content = b"MZ\x90\x00" + b"\x00" * 50
        
        response = client.post(
            "/evidence/upload",
            files={"file": ("malware.exe", BytesIO(exe_content), "application/octet-stream")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "Unsupported file format" in data["detail"] or "Supported formats" in data["detail"]
    
    def test_upload_response_has_valid_hash(self, client, setup_test_env):
        """Test that upload response contains valid SHA-256 hash."""
        # Use known content for reproducible hash
        known_content = b"This is test evidence content for hash validation."
        
        response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(known_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Hash test"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # SHA-256 should be valid hex string of 64 chars
        hash_value = data["sha256_hash"]
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)
    
    def test_upload_response_has_iso8601_timestamp(self, client, setup_test_env):
        """Test that upload response contains ISO 8601 formatted timestamp."""
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Timestamp test"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify ISO 8601 format (YYYY-MM-DDTHH:MM:SS.xxx+00:00 or Z)
        timestamp = data["upload_timestamp"]
        assert "T" in timestamp  # Date/time separator
        assert (timestamp.endswith("Z") or timestamp.endswith("+00:00"))  # UTC timezone
        parts = timestamp.replace("+00:00", "").replace("Z", "").split("T")
        assert len(parts) == 2
        assert "-" in parts[0]  # Date has dashes


class TestBatchUploadEndpoint:
    """Tests for POST /evidence/upload/batch endpoint."""
    
    def test_batch_upload_endpoint_exists(self, client, setup_test_env):
        """Test that batch upload endpoint exists and accepts requests."""
        # This test validates the endpoint is properly registered
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        response = client.post(
            "/evidence/upload/batch",
            files={"files": []},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        # Should be 400 for empty files, not 404 (endpoint exists)
        assert response.status_code in [400, 422]
    
    def test_batch_upload_missing_uploader_id(self, client, setup_test_env):
        """Test batch upload rejects missing uploader_id."""
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        files = [("file", ("test.jpg", BytesIO(jpg_content), "image/jpeg"))]
        
        response = client.post(
            "/evidence/upload/batch",
            files=files,
            data={"collection_method": "Test"}
        )
        
        assert response.status_code == 422  # FastAPI validation error
    
    def test_batch_upload_missing_collection_method(self, client, setup_test_env):
        """Test batch upload rejects missing collection_method."""
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        files = [("file", ("test.jpg", BytesIO(jpg_content), "image/jpeg"))]
        
        response = client.post(
            "/evidence/upload/batch",
            files=files,
            data={"uploader_id": "investigator_001"}
        )
        
        assert response.status_code == 422  # FastAPI validation error
    
    def test_batch_upload_no_files(self, client, setup_test_env):
        """Test batch upload rejects empty file list."""
        response = client.post(
            "/evidence/upload/batch",
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Empty batch"
            }
        )
        
        assert response.status_code == 400 or response.status_code == 422


class TestRetrievalEndpoints:
    """Tests for GET /evidence/{id} and GET /evidence/{id}/file endpoints."""
    
    def test_get_evidence_record_success(self, client, setup_test_env):
        """Test successful retrieval of evidence record."""
        # First, upload a file
        jpg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00' + b'\x00' * 100
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Mobile device extraction"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        
        # Now retrieve the evidence record
        retrieval_response = client.get(f"/evidence/{evidence_id}")
        
        assert retrieval_response.status_code == 200
        data = retrieval_response.json()
        
        # Verify response structure
        assert "id" in data
        assert "original_filename" in data
        assert "file_size" in data
        assert "mime_type" in data
        assert "file_extension" in data
        assert "sha256_hash" in data
        assert "uploader_id" in data
        assert "collection_method" in data
        assert "upload_timestamp" in data
        
        # Verify response values match upload
        assert data["id"] == evidence_id
        assert data["original_filename"] == "test.jpg"
        assert data["file_size"] == len(jpg_content)
        assert data["mime_type"] == "image/jpeg"
        assert data["file_extension"] == "jpg"
        assert data["uploader_id"] == "investigator_001"
        assert data["collection_method"] == "Mobile device extraction"
    
    def test_get_evidence_record_not_found(self, client, setup_test_env):
        """Test retrieval returns 404 for non-existent evidence ID."""
        response = client.get("/evidence/nonexistent-id")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "Evidence record not found" in data["detail"]
    
    def test_get_evidence_record_logs_custody_entry(self, client, setup_test_env):
        """Test that evidence record retrieval logs a custody ACCESS entry."""
        # Upload a file
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Retrieve the evidence record
        retrieval_response = client.get(f"/evidence/{evidence_id}")
        assert retrieval_response.status_code == 200
        
        # Check that custody entry was created
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action_type FROM custody_entries WHERE evidence_id = ? AND action_type = 'ACCESS'",
            (evidence_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        # Should have at least one ACCESS entry (from retrieval)
        access_entries = [row for row in rows if row[0] == "ACCESS"]
        assert len(access_entries) > 0
    
    def test_download_evidence_file_success(self, client, setup_test_env):
        """Test successful download of evidence file."""
        # Upload a file
        known_content = b"Test evidence file content for download validation."
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(known_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        mime_type = upload_response.json().get("mime_type", "text/plain")
        
        # Download the file
        download_response = client.get(f"/evidence/{evidence_id}/file")
        
        assert download_response.status_code == 200
        assert download_response.content == known_content
        # Verify Content-Type header
        assert "text/plain" in download_response.headers.get("content-type", "")
    
    def test_download_evidence_file_not_found(self, client, setup_test_env):
        """Test file download returns 404 for non-existent evidence ID."""
        response = client.get("/evidence/nonexistent-id/file")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "Evidence file not found" in data["detail"]
    
    def test_download_evidence_file_correct_content_type(self, client, setup_test_env):
        """Test that downloaded file has correct Content-Type header."""
        # Upload a JPG file
        jpg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 100
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Download the file
        download_response = client.get(f"/evidence/{evidence_id}/file")
        
        assert download_response.status_code == 200
        # Verify Content-Type is image/jpeg
        assert "image/jpeg" in download_response.headers.get("content-type", "")
    
    def test_download_evidence_file_logs_custody_entry(self, client, setup_test_env):
        """Test that evidence file download logs a custody ACCESS entry."""
        # Upload a file
        content = b"Test content"
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Download the file
        download_response = client.get(f"/evidence/{evidence_id}/file")
        assert download_response.status_code == 200
        
        # Check that custody entry was created
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action_type FROM custody_entries WHERE evidence_id = ? AND action_type = 'ACCESS'",
            (evidence_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        # Should have at least one ACCESS entry (from file download)
        access_entries = [row for row in rows if row[0] == "ACCESS"]
        assert len(access_entries) > 0
    
    def test_download_evidence_file_round_trip(self, client, setup_test_env):
        """Test upload-download round trip maintains file integrity."""
        # Create deterministic content
        original_content = b"Forensic evidence file for round-trip testing with specific content."
        
        # Upload the file
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("evidence.txt", BytesIO(original_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test collection"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        original_hash = upload_response.json()["sha256_hash"]
        
        # Download the file
        download_response = client.get(f"/evidence/{evidence_id}/file")
        
        assert download_response.status_code == 200
        downloaded_content = download_response.content
        
        # Verify content matches
        assert downloaded_content == original_content
        
        # Verify hash of downloaded content matches original
        import hashlib
        computed_hash = hashlib.sha256(downloaded_content).hexdigest()
        assert computed_hash == original_hash


class TestCustodyRetrievalEndpoint:
    """Tests for GET /evidence/{id}/custody endpoint."""
    
    def test_get_custody_chain_success(self, client, setup_test_env):
        """Test successful retrieval of custody chain."""
        # Upload a file
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Mobile device extraction"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        
        # Perform some actions to create custody entries
        client.get(f"/evidence/{evidence_id}")  # ACCESS via retrieval
        client.get(f"/evidence/{evidence_id}/file")  # ACCESS via download
        
        # Retrieve custody chain
        custody_response = client.get(f"/evidence/{evidence_id}/custody")
        
        assert custody_response.status_code == 200
        custody_entries = custody_response.json()
        
        # Should have at least UPLOAD + 2 ACCESS entries
        assert len(custody_entries) >= 3
        
        # First entry should be UPLOAD
        assert custody_entries[0]["action_type"] == "UPLOAD"
        assert custody_entries[0]["evidence_id"] == evidence_id
        assert "timestamp" in custody_entries[0]
        assert custody_entries[0]["id"] is not None
    
    def test_get_custody_chain_not_found(self, client, setup_test_env):
        """Test custody retrieval returns 404 for non-existent evidence ID."""
        response = client.get("/evidence/nonexistent-id/custody")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "Evidence record not found" in data["detail"]
    
    def test_get_custody_chain_chronological_order(self, client, setup_test_env):
        """Test that custody entries are returned in chronological order."""
        import time
        
        # Upload a file
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Create multiple ACCESS entries with delays
        time.sleep(0.01)
        client.get(f"/evidence/{evidence_id}")
        time.sleep(0.01)
        client.get(f"/evidence/{evidence_id}/file")
        
        # Retrieve custody chain
        custody_response = client.get(f"/evidence/{evidence_id}/custody")
        
        assert custody_response.status_code == 200
        custody_entries = custody_response.json()
        
        # Verify chronological order
        for i in range(1, len(custody_entries)):
            assert custody_entries[i]["timestamp"] >= custody_entries[i-1]["timestamp"]
    
    def test_get_custody_chain_empty_for_no_actions(self, client, setup_test_env):
        """Test that custody chain returns only UPLOAD entry if no other actions."""
        # Upload a file
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Retrieve custody chain without performing any other actions
        custody_response = client.get(f"/evidence/{evidence_id}/custody")
        
        assert custody_response.status_code == 200
        custody_entries = custody_response.json()
        
        # Should have at least UPLOAD entry
        assert len(custody_entries) >= 1
        assert custody_entries[0]["action_type"] == "UPLOAD"
    
    def test_get_custody_chain_response_structure(self, client, setup_test_env):
        """Test that custody entries have correct response structure."""
        # Upload a file
        jpg_content = b'\xff\xd8\xff\xe0' + b'\x00' * 50
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Perform an action
        client.get(f"/evidence/{evidence_id}")
        
        # Retrieve custody chain
        custody_response = client.get(f"/evidence/{evidence_id}/custody")
        
        assert custody_response.status_code == 200
        custody_entries = custody_response.json()
        
        # Each entry should have required fields
        for entry in custody_entries:
            assert "id" in entry
            assert isinstance(entry["id"], int)
            assert "evidence_id" in entry
            assert entry["evidence_id"] == evidence_id
            assert "action_type" in entry
            assert entry["action_type"] in ["UPLOAD", "ACCESS", "VERIFY"]
            assert "timestamp" in entry
            # notes is optional, can be None or string
            assert "notes" in entry


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
