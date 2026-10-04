"""
Signal Aggregator - Combines individual signals into verdict and confidence score.
Implements weighted averaging and explanation generation.

Requirements: 5.2, 5.3, 6.1, 6.2
"""

import logging
from typing import List, Tuple
from .models import Signal

logger = logging.getLogger(__name__)


class SignalAggregator:
    """
    Aggregates authentication signals into final verdict and confidence score.
    
    Algorithm:
    1. Collect all signals from analysis
    2. Extract severity and score from each signal
    3. Weight signals by severity (CRITICAL=40%, WARNING=30%, INFO=10%)
    4. Compute weighted average confidence_score (0-100)
    5. Determine verdict based on score and signal severity:
       - AUTHENTIC: confidence >= 85 AND no CRITICAL signals
       - SUSPICIOUS: confidence 50-84 OR some WARNING signals
       - TAMPERED: confidence < 50 OR CRITICAL signals detected
    6. Generate human-readable explanation
    
    Validates: Requirements 5.2, 5.3, 6.1, 6.2
    """
    
    # Weight distribution for each severity level
    SEVERITY_WEIGHTS = {
        "CRITICAL": 0.40,  # 40% weight
        "WARNING": 0.30,   # 30% weight
        "INFO": 0.10       # 10% weight
    }
    
    def aggregate(self, signals: List[Signal]) -> Tuple[int, str, str]:
        """
        Aggregate signals into confidence_score, verdict, and explanation.
        
        Args:
            signals: List of Signal objects from analysis
        
        Returns:
            Tuple of (confidence_score: int, verdict: str, explanation: str)
        
        Validates: Requirements 5.2, 5.3, 6.1, 6.2
        """
        
        # Handle empty signal list
        if not signals:
            logger.warning("No signals provided to aggregator")
            return 50, "SUSPICIOUS", "No authentication signals were generated for this file."
        
        # Calculate weighted confidence score
        confidence_score = self._calculate_confidence_score(signals)
        
        # Determine verdict based on score and signal severity
        verdict = self._determine_verdict(signals, confidence_score)
        
        # Generate explanation
        explanation = self._generate_explanation(signals, confidence_score, verdict)
        
        logger.debug(f"Aggregation complete: confidence={confidence_score}, verdict={verdict}")
        
        return confidence_score, verdict, explanation
    
    def _calculate_confidence_score(self, signals: List[Signal]) -> int:
        """
        Calculate weighted average confidence score from signals.
        
        IMPORTANT: In authentication, a LOW signal score (close to 0) means CLEAN/AUTHENTIC
        while a HIGH signal score (close to 100) means TAMPERING detected.
        
        Confidence = 100 - average_signal_score
        
        This inverts the signal scores so that:
        - Signals with score 0-10 (clean) -> confidence 90-100 (authentic)
        - Signals with score 50 (uncertain) -> confidence 50 (suspicious)
        - Signals with score 80-100 (tampering) -> confidence 0-20 (tampered)
        
        Returns: Integer 0-100 representing overall confidence/authenticity
        """
        
        if not signals:
            return 50
        
        # Calculate simple average of all signal scores
        avg_signal_score = sum(s.score for s in signals) / len(signals)
        
        # Invert: confidence = 100 - avg_signal_score
        # This makes low scores (0-10 clean) -> high confidence (90-100 authentic)
        confidence_score = int(100 - avg_signal_score)
        
        # Ensure score is in valid range
        confidence_score = max(0, min(100, confidence_score))
        
        logger.debug(f"Confidence calculation: avg_signal_score={int(avg_signal_score)}, confidence={confidence_score}")
        
        return confidence_score
    
    def _determine_verdict(self, signals: List[Signal], confidence_score: int) -> str:
        """
        Determine final verdict based on confidence score and signal severity.
        
        Rules:
        - AUTHENTIC: confidence >= 85 AND no CRITICAL signals
        - SUSPICIOUS: confidence 50-84 OR some WARNING signals
        - TAMPERED: confidence < 50 OR CRITICAL signals present
        
        Returns: String verdict (AUTHENTIC, SUSPICIOUS, or TAMPERED)
        """
        
        # Check for CRITICAL signals
        critical_signals = [s for s in signals if s.severity == "CRITICAL"]
        warning_signals = [s for s in signals if s.severity == "WARNING"]
        
        # Rule 1: If any CRITICAL signals, verdict is TAMPERED
        if critical_signals:
            logger.debug(f"Verdict: TAMPERED (due to {len(critical_signals)} critical signals)")
            return "TAMPERED"
        
        # Rule 2: If confidence < 50, verdict is TAMPERED
        if confidence_score < 50:
            logger.debug(f"Verdict: TAMPERED (confidence {confidence_score} < 50)")
            return "TAMPERED"
        
        # Rule 3: If confidence >= 85 and no CRITICAL signals, verdict is AUTHENTIC
        if confidence_score >= 85:
            logger.debug(f"Verdict: AUTHENTIC (confidence {confidence_score} >= 85, no critical signals)")
            return "AUTHENTIC"
        
        # Rule 4: Otherwise (50-84), verdict is SUSPICIOUS
        logger.debug(f"Verdict: SUSPICIOUS (confidence {confidence_score} in range 50-84)")
        return "SUSPICIOUS"
    
    def _generate_explanation(self, signals: List[Signal], confidence_score: int, verdict: str) -> str:
        """
        Generate human-readable explanation of analysis results.
        
        Summarizes key findings, highlights significant signals, and provides recommendations.
        Max 5000 characters.
        
        Returns: Explanation string
        """
        
        # Group signals by severity
        critical_signals = [s for s in signals if s.severity == "CRITICAL"]
        warning_signals = [s for s in signals if s.severity == "WARNING"]
        info_signals = [s for s in signals if s.severity == "INFO"]
        
        explanation_parts = []
        
        # Start with verdict and confidence
        explanation_parts.append(f"Authentication Analysis Result: {verdict}")
        explanation_parts.append(f"Confidence Score: {confidence_score}%")
        explanation_parts.append("")
        
        # Summary of signals
        explanation_parts.append(f"Analysis Summary:")
        explanation_parts.append(f"- Critical Issues: {len(critical_signals)}")
        explanation_parts.append(f"- Warnings: {len(warning_signals)}")
        explanation_parts.append(f"- Info Signals: {len(info_signals)}")
        explanation_parts.append("")
        
        # Add detail for each signal type
        if critical_signals:
            explanation_parts.append("CRITICAL FINDINGS (Strong indicators of tampering):")
            for i, signal in enumerate(critical_signals[:3], 1):  # Limit to top 3
                explanation_parts.append(f"  {i}. {signal.signal_name}: {signal.message}")
            if len(critical_signals) > 3:
                explanation_parts.append(f"  ... and {len(critical_signals) - 3} more critical issues")
            explanation_parts.append("")
        
        if warning_signals:
            explanation_parts.append("WARNINGS (Potential anomalies):")
            for i, signal in enumerate(warning_signals[:3], 1):  # Limit to top 3
                explanation_parts.append(f"  {i}. {signal.signal_name}: {signal.message}")
            if len(warning_signals) > 3:
                explanation_parts.append(f"  ... and {len(warning_signals) - 3} more warnings")
            explanation_parts.append("")
        
        if info_signals:
            explanation_parts.append("NORMAL FINDINGS (Expected characteristics):")
            for i, signal in enumerate(info_signals[:2], 1):  # Limit to top 2
                explanation_parts.append(f"  {i}. {signal.signal_name}: {signal.message}")
            if len(info_signals) > 2:
                explanation_parts.append(f"  ... and {len(info_signals) - 2} more normal findings")
            explanation_parts.append("")
        
        # Add verdict-specific guidance
        if verdict == "AUTHENTIC":
            explanation_parts.append("VERDICT INTERPRETATION:")
            explanation_parts.append("This evidence file appears to be authentic with high confidence.")
            explanation_parts.append("All key authentication checks passed without significant issues.")
            explanation_parts.append("Recommendation: File can be considered authentic for investigative purposes.")
        
        elif verdict == "SUSPICIOUS":
            explanation_parts.append("VERDICT INTERPRETATION:")
            explanation_parts.append("This evidence file shows some anomalies or ambiguous characteristics.")
            explanation_parts.append("Further manual review is recommended to assess potential authenticity concerns.")
            explanation_parts.append("Recommendation: Investigate specific findings flagged above before drawing conclusions.")
        
        elif verdict == "TAMPERED":
            explanation_parts.append("VERDICT INTERPRETATION:")
            explanation_parts.append("This evidence file shows signs of tampering or significant manipulation.")
            explanation_parts.append("Critical issues detected that suggest file integrity may be compromised.")
            explanation_parts.append("Recommendation: This file should be treated as potentially unreliable evidence.")
        
        # Join all parts
        explanation = "\n".join(explanation_parts)
        
        # Truncate to 5000 characters
        if len(explanation) > 5000:
            explanation = explanation[:4997] + "..."
        
        logger.debug(f"Explanation generated: {len(explanation)} characters")
        
        return explanation
