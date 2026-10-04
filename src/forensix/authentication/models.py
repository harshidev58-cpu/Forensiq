"""
Data models for Authentication Engine module.
Defines Signal and AuthenticationResult structures for authentication analysis.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any
from datetime import datetime, timezone


@dataclass
class Signal:
    """
    Represents a single authentication check result.
    
    Attributes:
        signal_name: Name of the signal (e.g., "EXIF_COMPLETE")
        category: Category of the signal (METADATA, STRUCTURE, ENCODING, TIMESTAMP, etc.)
        severity: Severity level (INFO, WARNING, CRITICAL)
        score: Score 0-100 (0=clean, 100=tampering detected)
        message: Human-readable result message
        details: Optional specific findings (dict)
    
    Validates: Requirements 5.1, 5.2
    """
    signal_name: str
    category: str
    severity: str
    score: int
    message: str
    details: Optional[dict] = None
    
    def __post_init__(self):
        """Validate field values after initialization."""
        # Validate severity
        valid_severities = {"INFO", "WARNING", "CRITICAL"}
        if self.severity not in valid_severities:
            raise ValueError(f"Invalid severity: {self.severity}. Must be one of {valid_severities}")
        
        # Validate score range
        if not isinstance(self.score, int) or not (0 <= self.score <= 100):
            raise ValueError(f"Score must be integer 0-100, got {self.score}")
    
    def to_dict(self) -> dict:
        """Convert signal to dictionary for JSON serialization."""
        return {
            "signal_name": self.signal_name,
            "category": self.category,
            "severity": self.severity,
            "score": self.score,
            "message": self.message,
            "details": self.details
        }
    
    def to_json(self) -> str:
        """Convert signal to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: dict) -> "Signal":
        """Create Signal from dictionary."""
        return cls(
            signal_name=data["signal_name"],
            category=data["category"],
            severity=data["severity"],
            score=data["score"],
            message=data["message"],
            details=data.get("details")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "Signal":
        """Create Signal from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class AuthenticationResult:
    """
    Represents a complete authentication analysis result.
    
    Attributes:
        id: UUID primary key
        evidence_id: Foreign key to evidence_records.id
        confidence_score: Integer 0-100 representing certainty in verdict
        verdict: String enum (AUTHENTIC, SUSPICIOUS, TAMPERED)
        signals_detected: List of Signal objects from analysis
        explanation: Human-readable summary (max 5000 chars)
        analyzed_at: ISO 8601 UTC timestamp when analysis was performed
        analyzer_version: Version of the authentication engine
        created_at: Timestamp of record creation
        updated_at: Timestamp of last update
    
    Validates: Requirements 1.1, 5.1, 5.2
    """
    id: str
    evidence_id: str
    confidence_score: int
    verdict: str
    signals_detected: List[Signal]
    explanation: str
    analyzed_at: str
    analyzer_version: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        """Validate field values after initialization."""
        # Validate confidence_score
        if not isinstance(self.confidence_score, int) or not (0 <= self.confidence_score <= 100):
            raise ValueError(f"Confidence score must be integer 0-100, got {self.confidence_score}")
        
        # Validate verdict
        valid_verdicts = {"AUTHENTIC", "SUSPICIOUS", "TAMPERED"}
        if self.verdict not in valid_verdicts:
            raise ValueError(f"Invalid verdict: {self.verdict}. Must be one of {valid_verdicts}")
        
        # Validate explanation length
        if len(self.explanation) > 5000:
            raise ValueError(f"Explanation exceeds 5000 chars: {len(self.explanation)}")
        
        # Validate signals are Signal objects
        if not all(isinstance(s, Signal) for s in self.signals_detected):
            raise ValueError("All signals_detected items must be Signal objects")
        
        # Note: Signal count validation happens in the analyzer based on file type
        # This allows for flexibility during development
    
    def to_dict(self) -> dict:
        """Convert result to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "evidence_id": self.evidence_id,
            "confidence_score": self.confidence_score,
            "verdict": self.verdict,
            "signals_detected": [s.to_dict() for s in self.signals_detected],
            "explanation": self.explanation,
            "analyzed_at": self.analyzed_at,
            "analyzer_version": self.analyzer_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    def to_json(self) -> str:
        """Convert result to JSON string for database storage."""
        return json.dumps(self.to_dict())
    
    def signals_as_json(self) -> str:
        """Convert signals_detected list to JSON string for database storage."""
        return json.dumps([s.to_dict() for s in self.signals_detected])
    
    @classmethod
    def from_dict(cls, data: dict) -> "AuthenticationResult":
        """Create AuthenticationResult from dictionary."""
        # Parse signals if they are dicts
        signals = data.get("signals_detected", [])
        if signals and isinstance(signals[0], dict):
            signals = [Signal.from_dict(s) for s in signals]
        
        return cls(
            id=data["id"],
            evidence_id=data["evidence_id"],
            confidence_score=data["confidence_score"],
            verdict=data["verdict"],
            signals_detected=signals,
            explanation=data["explanation"],
            analyzed_at=data["analyzed_at"],
            analyzer_version=data["analyzer_version"],
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "AuthenticationResult":
        """Create AuthenticationResult from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
