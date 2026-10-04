"""
Chain of custody logging module for ForensiX.
Provides non-blocking audit trail functionality for evidence handling.
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

from .config import ActionType, TIMESTAMP_FORMAT

# Configure logger
logger = logging.getLogger(__name__)


def create_chain_of_custody_entry(
    conn: sqlite3.Connection, 
    evidence_id: str, 
    action_type: str, 
    notes: Optional[str] = None
) -> None:
    """
    Create a chain of custody entry for evidence handling actions.
    
    This function provides non-blocking error handling - custody logging failures
    are logged but never raise exceptions to avoid blocking primary operations.
    
    Args:
        conn: SQLite database connection
        evidence_id: UUID of the evidence record
        action_type: Type of action (UPLOAD, ACCESS, VERIFY)
        notes: Optional contextual notes about the action
        
    Requirements: 11.1, 11.2, 11.3, 11.4, 11.8
    """
    try:
        # Capture timestamp with millisecond precision in UTC
        timestamp = datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)
        
        # Validate action_type
        valid_actions = {ActionType.UPLOAD, ActionType.ACCESS, ActionType.VERIFY}
        if action_type not in valid_actions:
            logger.warning(f"Invalid action_type '{action_type}' for evidence {evidence_id}. Valid actions: {valid_actions}")
            # Continue with the provided action_type anyway for flexibility
        
        # Insert custody entry
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO custody_entries (evidence_id, action_type, timestamp, notes)
            VALUES (?, ?, ?, ?)
            """,
            (evidence_id, action_type, timestamp, notes)
        )
        
        # Commit the transaction
        conn.commit()
        
        logger.info(f"Chain of custody entry created: evidence_id={evidence_id}, action={action_type}, timestamp={timestamp}")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to create chain of custody entry for evidence {evidence_id}: {e}")
        # Non-blocking: catch all exceptions, log errors, but never raise
        # This ensures custody failures don't block primary operations (upload, access, verification)
        
    except Exception as e:
        logger.error(f"Unexpected error creating chain of custody entry for evidence {evidence_id}: {e}")
        # Non-blocking: catch all exceptions, log errors, but never raise


def get_chain_of_custody_entries(conn: sqlite3.Connection, evidence_id: str) -> list:
    """
    Retrieve all chain of custody entries for a specific evidence record.
    
    Args:
        conn: SQLite database connection
        evidence_id: UUID of the evidence record
        
    Returns:
        List of custody entries sorted by timestamp in ascending order
        
    Raises:
        sqlite3.Error: For database query errors (not caught - let caller handle)
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, evidence_id, action_type, timestamp, notes
        FROM custody_entries
        WHERE evidence_id = ?
        ORDER BY timestamp ASC
        """,
        (evidence_id,)
    )
    
    rows = cursor.fetchall()
    
    # Convert to list of dictionaries for easier handling
    entries = []
    for row in rows:
        entry = {
            'id': row[0],
            'evidence_id': row[1],
            'action_type': row[2],
            'timestamp': row[3],
            'notes': row[4]
        }
        entries.append(entry)
    
    return entries


def verify_custody_chain(conn: sqlite3.Connection, evidence_id: str) -> dict:
    """
    Verify the integrity of the chain of custody for an evidence record.
    
    Args:
        conn: SQLite database connection
        evidence_id: UUID of the evidence record
        
    Returns:
        Dictionary containing chain verification results:
        - valid: bool - whether chain is valid
        - entries_count: int - number of custody entries
        - first_action: str - first logged action (should be UPLOAD)
        - timeline_valid: bool - whether timestamps are in chronological order
    """
    try:
        entries = get_chain_of_custody_entries(conn, evidence_id)
        
        if not entries:
            return {
                'valid': False,
                'entries_count': 0,
                'first_action': None,
                'timeline_valid': False,
                'error': 'No custody entries found'
            }
        
        # Check if first action is UPLOAD
        first_action_valid = entries[0]['action_type'] == ActionType.UPLOAD
        
        # Check if timeline is chronologically valid
        timeline_valid = True
        for i in range(1, len(entries)):
            if entries[i]['timestamp'] < entries[i-1]['timestamp']:
                timeline_valid = False
                break
        
        return {
            'valid': first_action_valid and timeline_valid,
            'entries_count': len(entries),
            'first_action': entries[0]['action_type'],
            'timeline_valid': timeline_valid,
            'entries': entries
        }
        
    except Exception as e:
        logger.error(f"Error verifying custody chain for evidence {evidence_id}: {e}")
        return {
            'valid': False,
            'entries_count': 0,
            'first_action': None,
            'timeline_valid': False,
            'error': str(e)
        }