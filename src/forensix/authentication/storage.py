"""
Storage operations for authentication results.
Handles database persistence and retrieval of authentication analysis results.

Requirements: 1.1, 1.3, 1.4, 8.1-8.4
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict
import json

from ..config import DATABASE_PATH
from .models import AuthenticationResult, Signal

logger = logging.getLogger(__name__)


class AuthenticationStorage:
    """
    Handles database operations for authentication results.
    
    Operations:
    - Insert/update authentication result in database
    - Retrieve authentication result by evidence_id
    - Query results by verdict with pagination
    - Use transactions with rollback on error
    
    Validates: Requirements 1.1, 1.3, 1.4, 8.1-8.4
    """
    
    def __init__(self, db_path: Path = DATABASE_PATH):
        """Initialize storage with database path."""
        self.db_path = db_path
    
    def store_result(self, result: AuthenticationResult) -> bool:
        """
        Store authentication result in database.
        
        Updates existing record if evidence_id exists (due to UNIQUE constraint),
        otherwise inserts new record.
        
        Args:
            result: AuthenticationResult object to store
        
        Returns:
            True if successful, False otherwise
        
        Raises:
            RuntimeError: If database transaction fails
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if result already exists for this evidence
            cursor.execute(
                "SELECT id FROM authentication_results WHERE evidence_id = ?",
                (result.evidence_id,)
            )
            existing = cursor.fetchone()
            
            now = self._get_current_timestamp_utc()
            
            if existing:
                # Update existing result
                cursor.execute(
                    """
                    UPDATE authentication_results
                    SET confidence_score = ?, verdict = ?, signals_detected = ?,
                        explanation = ?, analyzed_at = ?, analyzer_version = ?, updated_at = ?
                    WHERE evidence_id = ?
                    """,
                    (result.confidence_score, result.verdict, result.signals_as_json(),
                     result.explanation, result.analyzed_at, result.analyzer_version,
                     now, result.evidence_id)
                )
                logger.debug(f"Updated authentication result for {result.evidence_id}")
            else:
                # Insert new result
                cursor.execute(
                    """
                    INSERT INTO authentication_results
                    (id, evidence_id, confidence_score, verdict, signals_detected,
                     explanation, analyzed_at, analyzer_version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (result.id, result.evidence_id, result.confidence_score, result.verdict,
                     result.signals_as_json(), result.explanation, result.analyzed_at,
                     result.analyzer_version, now, now)
                )
                logger.debug(f"Inserted authentication result for {result.evidence_id}")
            
            conn.commit()
            conn.close()
            
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Database error storing result for {result.evidence_id}: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
            raise RuntimeError(f"Failed to store authentication result: {e}")
    
    def get_result(self, evidence_id: str) -> Optional[AuthenticationResult]:
        """
        Retrieve authentication result by evidence_id.
        
        Args:
            evidence_id: UUID of the evidence record
        
        Returns:
            AuthenticationResult object if found, None otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT id, evidence_id, confidence_score, verdict, signals_detected,
                       explanation, analyzed_at, analyzer_version, created_at, updated_at
                FROM authentication_results
                WHERE evidence_id = ?
                """,
                (evidence_id,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            # Convert database row to result
            result_dict = dict(row)
            
            # Parse signals_detected from JSON
            signals_json = result_dict['signals_detected']
            signals_data = json.loads(signals_json)
            result_dict['signals_detected'] = [Signal.from_dict(s) for s in signals_data]
            
            return AuthenticationResult.from_dict(result_dict)
            
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving result for {evidence_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing result for {evidence_id}: {e}")
            return None
    
    def get_results_by_verdict(
        self,
        verdict: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[AuthenticationResult]:
        """
        Query authentication results by verdict with pagination.
        
        Args:
            verdict: Verdict filter (AUTHENTIC, SUSPICIOUS, TAMPERED)
            limit: Max number of results to return
            offset: Pagination offset
        
        Returns:
            List of AuthenticationResult objects
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT id, evidence_id, confidence_score, verdict, signals_detected,
                       explanation, analyzed_at, analyzer_version, created_at, updated_at
                FROM authentication_results
                WHERE verdict = ?
                ORDER BY analyzed_at DESC
                LIMIT ? OFFSET ?
                """,
                (verdict, limit, offset)
            )
            
            rows = cursor.fetchall()
            conn.close()
            
            results = []
            for row in rows:
                try:
                    result_dict = dict(row)
                    signals_json = result_dict['signals_detected']
                    signals_data = json.loads(signals_json)
                    result_dict['signals_detected'] = [Signal.from_dict(s) for s in signals_data]
                    results.append(AuthenticationResult.from_dict(result_dict))
                except Exception as e:
                    logger.error(f"Error processing result: {e}")
                    continue
            
            return results
            
        except sqlite3.Error as e:
            logger.error(f"Database error querying results by verdict {verdict}: {e}")
            return []
    
    def get_all_results(self, limit: int = 100, offset: int = 0) -> List[AuthenticationResult]:
        """
        Retrieve all authentication results with pagination.
        
        Args:
            limit: Max number of results to return
            offset: Pagination offset
        
        Returns:
            List of AuthenticationResult objects
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT id, evidence_id, confidence_score, verdict, signals_detected,
                       explanation, analyzed_at, analyzer_version, created_at, updated_at
                FROM authentication_results
                ORDER BY analyzed_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
            
            rows = cursor.fetchall()
            conn.close()
            
            results = []
            for row in rows:
                try:
                    result_dict = dict(row)
                    signals_json = result_dict['signals_detected']
                    signals_data = json.loads(signals_json)
                    result_dict['signals_detected'] = [Signal.from_dict(s) for s in signals_data]
                    results.append(AuthenticationResult.from_dict(result_dict))
                except Exception as e:
                    logger.error(f"Error processing result: {e}")
                    continue
            
            return results
            
        except sqlite3.Error as e:
            logger.error(f"Database error querying all results: {e}")
            return []
    
    def _get_current_timestamp_utc(self) -> str:
        """Get current timestamp in ISO 8601 UTC format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
