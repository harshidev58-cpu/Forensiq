"""
Unit tests for chain of custody logging module.
"""

import unittest
import sqlite3
import tempfile
import os
from datetime import datetime, timezone
import logging

from src.forensix.custody import (
    create_chain_of_custody_entry,
    get_chain_of_custody_entries,
    verify_custody_chain
)
from src.forensix.config import ActionType


class TestChainOfCustody(unittest.TestCase):
    """Test cases for chain of custody logging functionality."""
    
    def setUp(self):
        """Set up test database for each test."""
        # Create temporary database for testing
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.conn = sqlite3.connect(self.db_path)
        
        # Create custody_entries table
        self.conn.execute('''
            CREATE TABLE custody_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
        
        # Set up logging to capture log messages for testing
        self.log_capture = []
        self.log_handler = logging.Handler()
        self.log_handler.emit = lambda record: self.log_capture.append(record)
        
        logger = logging.getLogger('src.forensix.custody')
        logger.addHandler(self.log_handler)
        logger.setLevel(logging.DEBUG)
    
    def tearDown(self):
        """Clean up test database after each test."""
        self.conn.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)
        
        # Remove log handler
        logger = logging.getLogger('src.forensix.custody')
        logger.removeHandler(self.log_handler)
    
    def test_successful_entry_creation_upload(self):
        """Test successful creation of UPLOAD custody entry."""
        evidence_id = "test-uuid-123"
        action_type = ActionType.UPLOAD
        notes = "Uploaded by investigator_001"
        
        # Should not raise any exceptions
        create_chain_of_custody_entry(self.conn, evidence_id, action_type, notes)
        
        # Verify entry was created
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM custody_entries WHERE evidence_id = ?", (evidence_id,))
        rows = cursor.fetchall()
        
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row[1], evidence_id)  # evidence_id
        self.assertEqual(row[2], action_type)  # action_type
        self.assertEqual(row[4], notes)        # notes
        
        # Verify timestamp format (ISO 8601 with timezone)
        timestamp = row[3]
        self.assertTrue(timestamp.endswith('Z'))
        # Should be parseable as ISO format
        datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    
    def test_successful_entry_creation_access(self):
        """Test successful creation of ACCESS custody entry."""
        evidence_id = "test-uuid-456"
        action_type = ActionType.ACCESS
        
        create_chain_of_custody_entry(self.conn, evidence_id, action_type)
        
        # Verify entry was created without notes
        cursor = self.conn.cursor()
        cursor.execute("SELECT action_type, notes FROM custody_entries WHERE evidence_id = ?", (evidence_id,))
        row = cursor.fetchone()
        
        self.assertEqual(row[0], ActionType.ACCESS)
        self.assertIsNone(row[1])  # notes should be None
    
    def test_successful_entry_creation_verify(self):
        """Test successful creation of VERIFY custody entry."""
        evidence_id = "test-uuid-789"
        action_type = ActionType.VERIFY
        notes = "Result: PASS"
        
        create_chain_of_custody_entry(self.conn, evidence_id, action_type, notes)
        
        # Verify entry was created
        cursor = self.conn.cursor()
        cursor.execute("SELECT action_type, notes FROM custody_entries WHERE evidence_id = ?", (evidence_id,))
        row = cursor.fetchone()
        
        self.assertEqual(row[0], ActionType.VERIFY)
        self.assertEqual(row[1], "Result: PASS")
    
    def test_non_blocking_database_error(self):
        """Test that database errors don't raise exceptions (non-blocking behavior)."""
        # Close connection to simulate database error
        self.conn.close()
        
        evidence_id = "test-uuid-error"
        action_type = ActionType.UPLOAD
        
        # Should NOT raise an exception despite database error
        try:
            create_chain_of_custody_entry(self.conn, evidence_id, action_type)
            # If we get here, the function properly caught the exception
        except Exception as e:
            self.fail(f"create_chain_of_custody_entry raised an exception: {e}")
        
        # Should have logged the error
        error_logs = [record for record in self.log_capture if record.levelname == 'ERROR']
        self.assertGreater(len(error_logs), 0)
    
    def test_invalid_action_type_handling(self):
        """Test handling of invalid action types."""
        evidence_id = "test-uuid-invalid"
        invalid_action_type = "INVALID_ACTION"
        
        # Should not raise exception, but should log warning
        create_chain_of_custody_entry(self.conn, evidence_id, invalid_action_type)
        
        # Should still create the entry (for flexibility)
        cursor = self.conn.cursor()
        cursor.execute("SELECT action_type FROM custody_entries WHERE evidence_id = ?", (evidence_id,))
        row = cursor.fetchone()
        
        self.assertEqual(row[0], invalid_action_type)
        
        # Should have logged a warning
        warning_logs = [record for record in self.log_capture if record.levelname == 'WARNING']
        self.assertGreater(len(warning_logs), 0)
    
    def test_get_custody_entries_chronological_order(self):
        """Test retrieving custody entries in chronological order."""
        evidence_id = "test-uuid-timeline"
        
        # Create multiple entries with small delays to ensure different timestamps
        import time
        
        create_chain_of_custody_entry(self.conn, evidence_id, ActionType.UPLOAD, "First")
        time.sleep(0.01)  # Small delay to ensure different timestamps
        create_chain_of_custody_entry(self.conn, evidence_id, ActionType.ACCESS, "Second")
        time.sleep(0.01)
        create_chain_of_custody_entry(self.conn, evidence_id, ActionType.VERIFY, "Third")
        
        # Retrieve entries
        entries = get_chain_of_custody_entries(self.conn, evidence_id)
        
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]['action_type'], ActionType.UPLOAD)
        self.assertEqual(entries[1]['action_type'], ActionType.ACCESS)
        self.assertEqual(entries[2]['action_type'], ActionType.VERIFY)
        
        # Verify chronological order
        self.assertLessEqual(entries[0]['timestamp'], entries[1]['timestamp'])
        self.assertLessEqual(entries[1]['timestamp'], entries[2]['timestamp'])
    
    def test_verify_custody_chain_valid(self):
        """Test custody chain verification for valid chain."""
        evidence_id = "test-uuid-valid-chain"
        
        # Create valid chain: UPLOAD -> ACCESS -> VERIFY
        create_chain_of_custody_entry(self.conn, evidence_id, ActionType.UPLOAD)
        create_chain_of_custody_entry(self.conn, evidence_id, ActionType.ACCESS)
        create_chain_of_custody_entry(self.conn, evidence_id, ActionType.VERIFY)
        
        result = verify_custody_chain(self.conn, evidence_id)
        
        self.assertTrue(result['valid'])
        self.assertEqual(result['entries_count'], 3)
        self.assertEqual(result['first_action'], ActionType.UPLOAD)
        self.assertTrue(result['timeline_valid'])
    
    def test_verify_custody_chain_invalid_first_action(self):
        """Test custody chain verification for invalid first action."""
        evidence_id = "test-uuid-invalid-chain"
        
        # Create invalid chain: starts with ACCESS instead of UPLOAD
        create_chain_of_custody_entry(self.conn, evidence_id, ActionType.ACCESS)
        
        result = verify_custody_chain(self.conn, evidence_id)
        
        self.assertFalse(result['valid'])
        self.assertEqual(result['entries_count'], 1)
        self.assertEqual(result['first_action'], ActionType.ACCESS)
    
    def test_verify_custody_chain_no_entries(self):
        """Test custody chain verification when no entries exist."""
        evidence_id = "test-uuid-no-entries"
        
        result = verify_custody_chain(self.conn, evidence_id)
        
        self.assertFalse(result['valid'])
        self.assertEqual(result['entries_count'], 0)
        self.assertIsNone(result['first_action'])
        self.assertFalse(result['timeline_valid'])
        self.assertIn('error', result)


if __name__ == '__main__':
    unittest.main()