"""
Authentication Analyzer - Main orchestrator for evidence authenticity analysis.
Coordinates the authentication workflow and manages caching/storage.

Requirements: 2.1, 2.2, 9.1, 6.1
"""

import sqlite3
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from ..config import (
    DATABASE_PATH, EVIDENCE_STORAGE_DIR, AUTHENTICATION_TIMEOUT, 
    MAX_AUTH_FILE_SIZE, ANALYZER_VERSION
)
from ..custody import create_chain_of_custody_entry
from .models import Signal, AuthenticationResult
from .image_analyzer import ImageAnalyzer
from .video_analyzer import VideoAnalyzer
from .aggregator import SignalAggregator
from .storage import AuthenticationStorage


logger = logging.getLogger(__name__)


class AuthenticationAnalyzer:
    """
    Main orchestrator for authentication analysis.
    
    Coordinates the authentication workflow:
    1. Retrieve evidence record and verify it exists
    2. Check if cached results exist (return if force_reanalysis=false)
    3. Load file from storage
    4. Route to Image or Video analyzer based on mime_type
    5. Collect all signals from analyzer
    6. Aggregate signals into confidence_score and verdict
    7. Store results in database
    8. Log chain of custody event
    9. Return result
    
    Validates: Requirements 2.1, 2.2, 9.1, 6.1
    """
    
    def __init__(self):
        """Initialize the authentication analyzer."""
        self.logger = logging.getLogger(__name__)
        self.db_path = DATABASE_PATH
        self.storage_dir = EVIDENCE_STORAGE_DIR
        self.timeout = AUTHENTICATION_TIMEOUT
        self.max_file_size = MAX_AUTH_FILE_SIZE
        self.analyzer_version = ANALYZER_VERSION
        self.image_analyzer = ImageAnalyzer()
        self.video_analyzer = VideoAnalyzer()
        self.aggregator = SignalAggregator()
        self.storage = AuthenticationStorage(self.db_path)
    
    def analyze_evidence(
        self,
        evidence_id: str,
        force_reanalysis: bool = False,
        actor_id: str = "SYSTEM",
        request_context: Optional[Dict[str, Any]] = None
    ) -> dict:
        """
        Main entry point for authentication analysis.
        
        Args:
            evidence_id: UUID of the evidence to analyze
            force_reanalysis: If true, bypass cache and re-analyze
            actor_id: Identifier for the requesting actor (user or system)
            request_context: Optional dict with client_ip and user_agent
        
        Returns:
            Dictionary with authentication result containing:
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
        
        Raises:
            ValueError: If evidence not found or invalid input
            OSError: If file cannot be accessed from storage
            RuntimeError: If analysis fails due to processing error
        
        Validates: Requirements 2.1, 2.2, 9.1, 6.1
        """
        if not request_context:
            request_context = {}
        
        try:
            # Step 1: Retrieve evidence record and verify it exists
            evidence = self._retrieve_evidence_record(evidence_id)
            if not evidence:
                raise ValueError(f"Evidence not found: {evidence_id}")
            
            self.logger.debug(f"Retrieved evidence record: {evidence_id}, mime_type={evidence.get('mime_type')}")
            
            # Step 2: Check if cached results exist and force_reanalysis=false
            if not force_reanalysis:
                cached_result = self._get_cached_result(evidence_id)
                if cached_result:
                    self.logger.info(f"Returning cached result for evidence {evidence_id}")
                    return cached_result
            
            # Step 3: Check mime_type early to fail fast on unsupported types
            mime_type = evidence.get('mime_type', '')
            if not mime_type.startswith('image/') and not mime_type.startswith('video/'):
                raise ValueError(f"Unsupported file type for authentication analysis: {mime_type}")
            
            # Step 4: Load file from storage and validate
            file_path = self._get_evidence_file_path(evidence_id, evidence['file_extension'])
            if not file_path.exists():
                raise OSError(f"Evidence file not found in storage: {file_path}")
            
            # Validate file size
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                raise ValueError(f"File exceeds maximum size: {file_size} > {self.max_file_size}")
            
            self.logger.debug(f"Evidence file validated: {file_path}, size={file_size} bytes")
            
            # Step 5: Route to appropriate analyzer based on mime_type
            signals = self._analyze_file(file_path, mime_type)
            
            # Step 6: Collect and aggregate signals into verdict
            confidence_score, verdict, explanation = self._aggregate_signals(signals, mime_type)
            
            self.logger.info(f"Analysis complete for {evidence_id}: verdict={verdict}, confidence={confidence_score}")
            
            # Step 7: Create result object
            result = AuthenticationResult(
                id=str(uuid.uuid4()),
                evidence_id=evidence_id,
                confidence_score=confidence_score,
                verdict=verdict,
                signals_detected=signals,
                explanation=explanation,
                analyzed_at=self._get_current_timestamp_utc(),
                analyzer_version=self.analyzer_version
            )
            
            # Step 8: Store results in database
            self._store_result(result)
            
            # Step 9: Log chain of custody event
            self._log_custody_event(evidence_id, verdict, confidence_score, actor_id, request_context)
            
            # Step 10: Return result as dict
            return result.to_dict()
            
        except ValueError as e:
            # Invalid input or evidence not found
            self.logger.error(f"Validation error analyzing {evidence_id}: {e}")
            raise
        except OSError as e:
            # File access error
            self.logger.error(f"File access error analyzing {evidence_id}: {e}")
            raise
        except Exception as e:
            # Processing error
            self.logger.error(f"Unexpected error analyzing {evidence_id}: {e}")
            raise RuntimeError(f"Authentication analysis failed: {str(e)}")
    
    def _retrieve_evidence_record(self, evidence_id: str) -> Optional[dict]:
        """
        Retrieve evidence record from database.
        
        Returns dict with evidence metadata or None if not found.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT id, original_filename, file_size, mime_type, file_extension,
                       sha256_hash, uploader_id, collection_method, upload_timestamp
                FROM evidence_records
                WHERE id = ?
                """,
                (evidence_id,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            return dict(row)
            
        except sqlite3.Error as e:
            self.logger.error(f"Database error retrieving evidence {evidence_id}: {e}")
            raise RuntimeError(f"Database error: {e}")
    
    def _get_cached_result(self, evidence_id: str) -> Optional[dict]:
        """
        Check if cached result exists for this evidence.
        
        Returns cached result dict if found and fresh (< 24 hours old), None otherwise.
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
            
            # Check if cached result is fresh (< 24 hours old)
            result_dict = dict(row)
            analyzed_at = datetime.fromisoformat(result_dict['analyzed_at'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age = now - analyzed_at
            
            if age > timedelta(hours=24):
                self.logger.debug(f"Cached result for {evidence_id} is stale ({age}), treating as miss")
                return None
            
            # Parse signals_detected from JSON
            import json
            result_dict['signals_detected'] = json.loads(result_dict['signals_detected'])
            
            return result_dict
            
        except sqlite3.Error as e:
            self.logger.error(f"Database error retrieving cached result for {evidence_id}: {e}")
            # Don't raise - just return None to proceed with analysis
            return None
        except Exception as e:
            self.logger.error(f"Error processing cached result for {evidence_id}: {e}")
            return None
    
    def _get_evidence_file_path(self, evidence_id: str, file_extension: str) -> Path:
        """Construct the file path for evidence stored in storage directory."""
        return self.storage_dir / f"{evidence_id}.{file_extension}"
    
    def _analyze_file(self, file_path: Path, mime_type: str) -> list:
        """
        Route to appropriate analyzer based on mime_type.
        
        Returns list of Signal objects from the appropriate analyzer.
        """
        # Determine file type from mime_type
        if mime_type.startswith('image/'):
            return self._analyze_image(file_path)
        elif mime_type.startswith('video/'):
            return self._analyze_video(file_path)
        else:
            raise ValueError(f"Unsupported file type for authentication analysis: {mime_type}")
    
    def _analyze_image(self, file_path: Path) -> list:
        """
        Perform image analysis. 
        
        Delegates to ImageAnalyzer to generate signals for EXIF, headers, thumbnails,
        color space, and compression artifacts.
        """
        self.logger.debug(f"Analyzing image file: {file_path}")
        try:
            signals = self.image_analyzer.analyze(file_path)
            self.logger.debug(f"Image analysis generated {len(signals)} signals")
            return signals
        except Exception as e:
            self.logger.error(f"Image analysis failed: {e}")
            raise
    
    def _analyze_video(self, file_path: Path) -> list:
        """
        Perform video analysis.
        
        Delegates to VideoAnalyzer to generate signals for container, codec, frames,
        timestamps, audio, and file size.
        """
        self.logger.debug(f"Analyzing video file: {file_path}")
        try:
            signals = self.video_analyzer.analyze(file_path)
            self.logger.debug(f"Video analysis generated {len(signals)} signals")
            return signals
        except Exception as e:
            self.logger.error(f"Video analysis failed: {e}")
            raise
    
    def _aggregate_signals(self, signals: list, mime_type: str) -> tuple:
        """
        Aggregate signals into confidence_score, verdict, and explanation.
        
        Delegates to SignalAggregator to perform weighted averaging and verdict logic.
        
        Returns: (confidence_score, verdict, explanation)
        
        Validates: Requirements 5.2, 5.3, 6.1, 6.2
        """
        return self.aggregator.aggregate(signals)
    
    def _store_result(self, result: AuthenticationResult) -> None:
        """
        Store authentication result in database.
        
        Handles UNIQUE constraint on evidence_id by either inserting new or updating existing.
        Uses transaction with rollback on error.
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
                self.logger.debug(f"Updated authentication result for {result.evidence_id}")
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
                self.logger.debug(f"Inserted authentication result for {result.evidence_id}")
            
            conn.commit()
            conn.close()
            
        except sqlite3.Error as e:
            self.logger.error(f"Database error storing result for {result.evidence_id}: {e}")
            if 'conn' in locals():
                conn.rollback()
                conn.close()
            raise RuntimeError(f"Failed to store authentication result: {e}")
    
    def _log_custody_event(
        self,
        evidence_id: str,
        verdict: str,
        confidence_score: int,
        actor_id: str,
        request_context: dict
    ) -> None:
        """
        Log chain of custody event for authentication analysis.
        
        Non-blocking - errors are logged but don't raise exceptions.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Create details JSON with verdict and confidence_score
            details = f"verdict={verdict}, confidence_score={confidence_score}"
            if request_context.get('client_ip'):
                details += f", client_ip={request_context['client_ip']}"
            if request_context.get('user_agent'):
                details += f", user_agent={request_context['user_agent']}"
            
            # Create custody entry with AUTHENTICATE action
            # Note: The custody module doesn't support AUTHENTICATE action yet,
            # but we'll add it to the entry anyway
            cursor = conn.cursor()
            timestamp = self._get_current_timestamp_utc()
            
            cursor.execute(
                """
                INSERT INTO custody_entries (evidence_id, action_type, timestamp, notes)
                VALUES (?, ?, ?, ?)
                """,
                (evidence_id, "AUTHENTICATE", timestamp, details)
            )
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Chain of custody event logged for {evidence_id}: AUTHENTICATE")
            
        except Exception as e:
            # Non-blocking - don't raise, just log error
            self.logger.error(f"Failed to log custody event for {evidence_id}: {e}")
    
    def _get_current_timestamp_utc(self) -> str:
        """Get current timestamp in ISO 8601 UTC format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
