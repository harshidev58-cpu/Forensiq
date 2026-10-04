"""
Tests for evidence integrity verification functionality.
Tests the verify_evidence_integrity function and POST /evidence/{id}/verify endpoint.
"""

import hashlib
import sqlite3
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.forensix.app import app, get_db_connection
from src.forensix.config import DATABASE_PATH, EVIDENCE_STORAGE_DIR
from src.forensix.verification import (
    verify_evidence_integrity,
    EvidenceNotFoundError,
    EvidenceFileNotFoundError
)
from src.forensix.hashing import HashComputationError, HashTimeoutError


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
    for file_path in EVIDENCE_STORAGE_DIR.glob("*.txt"):
        try:
            file_path.unlink()
        except Exception:
            pass
    for file_path in EVIDENCE_STORAGE_DIR.glob("*.mp4"):
        try:
            file_path.unlink()
        except Exception:
            pass


class TestVerifyEvidenceIntegrityFunction:
    """Tests for verify_evidence_integrity() function."""
    
    def test_verify_unmodified_file_passes(self, setup_test_env):
        """Test that verification returns PASS for unmodified files."""
        # Create test content and file
        test_content = b"Evidence content that should not change."
        
        # Upload via API to create evidence record
        client = TestClient(app)
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        original_hash = upload_response.json()["sha256_hash"]
        
        # Verify integrity
        conn = get_db_connection()
        result = verify_evidence_integrity(conn, evidence_id)
        conn.close()
        
        # Should return PASS
        assert result["status"] == "PASS"
        assert result["original_hash"] == original_hash
        assert result["computed_hash"] == original_hash
        assert "verification_timestamp" in result
    
    def test_verify_modified_file_fails(self, setup_test_env):
        """Test that verification returns FAIL for modified files."""
        # Create and upload test file
        original_content = b"Original evidence content"
        
        client = TestClient(app)
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(original_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        original_hash = upload_response.json()["sha256_hash"]
        
        # Modify the stored file
        file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.txt"
        modified_content = b"Modified evidence content - tampering detected!"
        file_path.write_bytes(modified_content)
        
        # Verify integrity
        conn = get_db_connection()
        result = verify_evidence_integrity(conn, evidence_id)
        conn.close()
        
        # Should return FAIL
        assert result["status"] == "FAIL"
        assert result["original_hash"] == original_hash
        assert result["computed_hash"] != original_hash
        assert "verification_timestamp" in result
    
    def test_verify_nonexistent_evidence_raises_error(self, setup_test_env):
        """Test that verification raises EvidenceNotFoundError for missing records."""
        conn = get_db_connection()
        
        with pytest.raises(EvidenceNotFoundError):
            verify_evidence_integrity(conn, "nonexistent-id-12345")
        
        conn.close()
    
    def test_verify_missing_file_raises_error(self, setup_test_env):
        """Test that verification raises EvidenceFileNotFoundError when file is missing."""
        # Create and upload test file
        test_content = b"Test content"
        
        client = TestClient(app)
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        
        # Delete the file from storage
        file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.txt"
        file_path.unlink()
        
        # Verify integrity should raise error
        conn = get_db_connection()
        
        with pytest.raises(EvidenceFileNotFoundError):
            verify_evidence_integrity(conn, evidence_id)
        
        conn.close()
    
    def test_verify_logs_custody_entry_on_pass(self, setup_test_env):
        """Test that verification logs VERIFY custody entry with PASS result."""
        # Create and upload test file
        test_content = b"Test content for custody logging"
        
        client = TestClient(app)
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Perform verification
        conn = get_db_connection()
        result = verify_evidence_integrity(conn, evidence_id)
        
        # Check that custody entry was created
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action_type, notes FROM custody_entries WHERE evidence_id = ? AND action_type = 'VERIFY' ORDER BY timestamp DESC LIMIT 1",
            (evidence_id,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == "VERIFY"
        assert "Result: PASS" in row[1]
    
    def test_verify_logs_custody_entry_on_fail(self, setup_test_env):
        """Test that verification logs VERIFY custody entry with FAIL result."""
        # Create and upload test file
        original_content = b"Original content"
        
        client = TestClient(app)
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(original_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Modify the file
        file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.txt"
        file_path.write_bytes(b"Modified content")
        
        # Perform verification
        conn = get_db_connection()
        result = verify_evidence_integrity(conn, evidence_id)
        
        # Check that custody entry was created with FAIL result
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action_type, notes FROM custody_entries WHERE evidence_id = ? AND action_type = 'VERIFY' ORDER BY timestamp DESC LIMIT 1",
            (evidence_id,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == "VERIFY"
        assert "Result: FAIL" in row[1]
    
    def test_verify_returns_valid_timestamp(self, setup_test_env):
        """Test that verification returns valid ISO 8601 timestamp."""
        # Create and upload test file
        test_content = b"Test content"
        
        client = TestClient(app)
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Perform verification
        conn = get_db_connection()
        result = verify_evidence_integrity(conn, evidence_id)
        conn.close()
        
        # Verify timestamp format
        timestamp = result["verification_timestamp"]
        assert "T" in timestamp  # Date/time separator
        assert (timestamp.endswith("Z") or timestamp.endswith("+00:00"))  # UTC timezone
    
    def test_verify_hash_case_insensitive(self, setup_test_env):
        """Test that hash comparison is case-insensitive."""
        # Create and upload test file
        test_content = b"Test content"
        
        client = TestClient(app)
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Manually uppercase the hash in the database to test case-insensitivity
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sha256_hash FROM evidence_records WHERE id = ?",
            (evidence_id,)
        )
        original_hash = cursor.fetchone()[0]
        
        # Update to uppercase
        uppercase_hash = original_hash.upper()
        cursor.execute(
            "UPDATE evidence_records SET sha256_hash = ? WHERE id = ?",
            (uppercase_hash, evidence_id)
        )
        conn.commit()
        
        # Verify should still pass (case-insensitive comparison)
        result = verify_evidence_integrity(conn, evidence_id)
        conn.close()
        
        assert result["status"] == "PASS"


class TestVerifyEvidenceEndpoint:
    """Tests for POST /evidence/{id}/verify endpoint."""
    
    def test_verify_endpoint_success_pass(self, client, setup_test_env):
        """Test successful verification endpoint returning PASS."""
        # Upload a file
        test_content = b"Test evidence content for verification"
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        original_hash = upload_response.json()["sha256_hash"]
        
        # Verify integrity via endpoint
        verify_response = client.post(f"/evidence/{evidence_id}/verify")
        
        assert verify_response.status_code == 200
        result = verify_response.json()
        
        # Verify response structure
        assert "status" in result
        assert "original_hash" in result
        assert "computed_hash" in result
        assert "verification_timestamp" in result
        
        # Verify values
        assert result["status"] == "PASS"
        assert result["original_hash"] == original_hash
        assert result["computed_hash"] == original_hash
    
    def test_verify_endpoint_success_fail(self, client, setup_test_env):
        """Test successful verification endpoint returning FAIL for modified file."""
        # Upload a file
        original_content = b"Original evidence"
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(original_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        original_hash = upload_response.json()["sha256_hash"]
        
        # Modify the file
        file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.txt"
        file_path.write_bytes(b"Modified evidence - tampering detected")
        
        # Verify integrity via endpoint
        verify_response = client.post(f"/evidence/{evidence_id}/verify")
        
        assert verify_response.status_code == 200
        result = verify_response.json()
        
        # Verify FAIL status
        assert result["status"] == "FAIL"
        assert result["original_hash"] == original_hash
        assert result["computed_hash"] != original_hash
    
    def test_verify_endpoint_evidence_not_found(self, client, setup_test_env):
        """Test verify endpoint returns 404 for non-existent evidence."""
        verify_response = client.post("/evidence/nonexistent-id/verify")
        
        assert verify_response.status_code == 404
        data = verify_response.json()
        assert "detail" in data
        assert "Evidence record not found" in data["detail"]
    
    def test_verify_endpoint_file_missing(self, client, setup_test_env):
        """Test verify endpoint returns 500 if file is missing from storage."""
        # Upload a file
        test_content = b"Test content"
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Direct upload"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Delete the file
        file_path = EVIDENCE_STORAGE_DIR / f"{evidence_id}.txt"
        file_path.unlink()
        
        # Verify should return 500
        verify_response = client.post(f"/evidence/{evidence_id}/verify")
        
        assert verify_response.status_code == 500
        data = verify_response.json()
        assert "detail" in data
        assert "missing from storage" in data["detail"]
    
    def test_verify_endpoint_response_structure(self, client, setup_test_env):
        """Test that verify endpoint response has correct structure."""
        # Upload a file
        test_content = b"Verification test content"
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Verify
        verify_response = client.post(f"/evidence/{evidence_id}/verify")
        
        assert verify_response.status_code == 200
        result = verify_response.json()
        
        # Check all required fields are present
        assert "status" in result
        assert result["status"] in ["PASS", "FAIL"]
        
        assert "original_hash" in result
        assert len(result["original_hash"]) == 64
        assert all(c in "0123456789abcdef" for c in result["original_hash"])
        
        assert "computed_hash" in result
        assert len(result["computed_hash"]) == 64
        assert all(c in "0123456789abcdef" for c in result["computed_hash"])
        
        assert "verification_timestamp" in result
        assert "T" in result["verification_timestamp"]
    
    def test_verify_endpoint_logs_custody_entry(self, client, setup_test_env):
        """Test that verify endpoint logs VERIFY custody entry."""
        # Upload a file
        test_content = b"Custody logging test"
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Verify
        verify_response = client.post(f"/evidence/{evidence_id}/verify")
        
        assert verify_response.status_code == 200
        
        # Check that custody entry was created
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action_type FROM custody_entries WHERE evidence_id = ? AND action_type = 'VERIFY'",
            (evidence_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        # Should have at least one VERIFY entry
        verify_entries = [row for row in rows if row[0] == "VERIFY"]
        assert len(verify_entries) > 0
    
    def test_verify_endpoint_idempotence(self, client, setup_test_env):
        """Test that multiple verifications of same file return same result."""
        # Upload a file
        test_content = b"Idempotence test content"
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Perform verification multiple times
        result1 = client.post(f"/evidence/{evidence_id}/verify").json()
        result2 = client.post(f"/evidence/{evidence_id}/verify").json()
        result3 = client.post(f"/evidence/{evidence_id}/verify").json()
        
        # All should return PASS
        assert result1["status"] == "PASS"
        assert result2["status"] == "PASS"
        assert result3["status"] == "PASS"
        
        # Hashes should be identical
        assert result1["original_hash"] == result2["original_hash"] == result3["original_hash"]
        assert result1["computed_hash"] == result2["computed_hash"] == result3["computed_hash"]
    
    def test_verify_endpoint_with_image_file(self, client, setup_test_env):
        """Test verification with image file."""
        # Create a minimal valid JPG content
        jpg_content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00' + b'\x00' * 100 + b'\xff\xd9'
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("image.jpg", BytesIO(jpg_content), "image/jpeg")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Camera extraction"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        
        # Verify
        verify_response = client.post(f"/evidence/{evidence_id}/verify")
        
        assert verify_response.status_code == 200
        result = verify_response.json()
        assert result["status"] == "PASS"
    
    def test_verify_endpoint_integrity_timeline(self, client, setup_test_env):
        """Test that verification appears in custody timeline."""
        import time
        
        # Upload a file
        test_content = b"Timeline test"
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("test.txt", BytesIO(test_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Test"
            }
        )
        
        evidence_id = upload_response.json()["id"]
        
        # Wait a bit
        time.sleep(0.01)
        
        # Retrieve evidence (creates ACCESS entry)
        client.get(f"/evidence/{evidence_id}")
        
        time.sleep(0.01)
        
        # Verify integrity (creates VERIFY entry)
        verify_response = client.post(f"/evidence/{evidence_id}/verify")
        
        assert verify_response.status_code == 200
        
        # Retrieve custody chain
        custody_response = client.get(f"/evidence/{evidence_id}/custody")
        
        assert custody_response.status_code == 200
        entries = custody_response.json()
        
        # Should have UPLOAD, ACCESS, VERIFY entries in order
        action_types = [e["action_type"] for e in entries]
        assert "UPLOAD" in action_types
        assert "ACCESS" in action_types
        assert "VERIFY" in action_types
        
        # Verify should be last or near last
        last_verify_idx = max(i for i, a in enumerate(action_types) if a == "VERIFY")
        assert last_verify_idx > 0


class TestVerificationWithLargeFiles:
    """Tests for verification with larger files."""
    
    def test_verify_endpoint_with_larger_file(self, client, setup_test_env):
        """Test verification with a reasonably large file."""
        # Create a 5MB file
        large_content = b"x" * (5 * 1024 * 1024)
        
        upload_response = client.post(
            "/evidence/upload",
            files={"file": ("large.txt", BytesIO(large_content), "text/plain")},
            data={
                "uploader_id": "investigator_001",
                "collection_method": "Large file test"
            }
        )
        
        assert upload_response.status_code == 201
        evidence_id = upload_response.json()["id"]
        
        # Verify should complete successfully
        verify_response = client.post(f"/evidence/{evidence_id}/verify")
        
        assert verify_response.status_code == 200
        result = verify_response.json()
        assert result["status"] == "PASS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
