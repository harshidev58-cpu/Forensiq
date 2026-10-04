"""
Pydantic schemas for API request/response validation.
Used for authentication endpoints.

Requirements: 2.1-2.10, 8.1-8.4
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class SignalSchema(BaseModel):
    """Schema for a signal in the response."""
    signal_name: str = Field(..., description="Name of the signal (e.g., EXIF_COMPLETE)")
    category: str = Field(..., description="Category (METADATA, STRUCTURE, ENCODING, TIMESTAMP)")
    severity: str = Field(..., description="Severity level (INFO, WARNING, CRITICAL)")
    score: int = Field(..., ge=0, le=100, description="Score 0-100 (0=clean, 100=tampering)")
    message: str = Field(..., description="Human-readable message")
    details: Optional[dict] = Field(None, description="Optional specific findings")


class AuthenticationResultResponse(BaseModel):
    """Response model for authentication analysis result."""
    id: str = Field(..., description="Unique identifier (UUID) for the result")
    evidence_id: str = Field(..., description="Evidence record ID being analyzed")
    confidence_score: int = Field(..., ge=0, le=100, description="Confidence score 0-100")
    verdict: str = Field(..., description="AUTHENTIC, SUSPICIOUS, or TAMPERED")
    signals_detected: List[SignalSchema] = Field(..., description="Array of signals from analysis")
    explanation: str = Field(..., description="Human-readable explanation (max 5000 chars)")
    analyzed_at: str = Field(..., description="ISO 8601 UTC timestamp of analysis")
    analyzer_version: str = Field(..., description="Version of authentication engine")


class AuthenticationErrorResponse(BaseModel):
    """Error response for authentication endpoint failures."""
    status_code: int = Field(..., description="HTTP status code")
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Detailed error message")
    evidence_id: Optional[str] = Field(None, description="Evidence ID if applicable")
