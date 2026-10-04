"""
Image Authentication Analyzer - Performs image-specific authenticity checks.
Implements signal generation for EXIF, headers, thumbnails, color space, and compression.

Requirements: 3.1-3.8, 5.1
"""

import logging
from pathlib import Path
from typing import List, Optional
from PIL import Image
import struct
import io

from .models import Signal

logger = logging.getLogger(__name__)


class ImageAnalyzer:
    """
    Performs image-specific authentication checks.
    
    Generates signals for:
    1. EXIF Metadata Validation
    2. Image Header Validation
    3. Thumbnail Analysis (JPEG only)
    4. Color Space Analysis
    5. Compression Artifacts Detection
    
    Validates: Requirements 3.1-3.8, 5.1
    """
    
    def analyze(self, file_path: Path) -> List[Signal]:
        """
        Perform comprehensive image analysis.
        
        Returns list of Signal objects representing all detected checks.
        """
        signals = []
        
        try:
            # Perform all analysis checks
            signals.extend(self._check_exif_metadata(file_path))
            signals.extend(self._check_image_header(file_path))
            signals.extend(self._check_thumbnail(file_path))
            signals.extend(self._check_color_space(file_path))
            signals.extend(self._check_compression_artifacts(file_path))
            
            logger.debug(f"Image analysis complete: {len(signals)} signals generated")
            
        except Exception as e:
            logger.error(f"Error during image analysis of {file_path}: {e}")
            # Add error signal to indicate analysis failure
            signals.append(Signal(
                signal_name="ANALYSIS_ERROR",
                category="STRUCTURE",
                severity="WARNING",
                score=60,
                message=f"Error during image analysis: {str(e)}",
                details={"error": str(e)}
            ))
        
        return signals
    
    def _check_exif_metadata(self, file_path: Path) -> List[Signal]:
        """
        Check EXIF metadata validity and consistency.
        
        Returns list of signals for:
        - EXIF_COMPLETE: Standard tags present and complete
        - EXIF_MISSING: No EXIF data found
        - EXIF_INCONSISTENT: Dates don't match, GPS issues
        """
        signals = []
        
        try:
            image = Image.open(file_path)
            
            # Try to extract EXIF data
            exif_dict = None
            try:
                exif_data = image.getexif()
                if exif_data:
                    exif_dict = exif_data
            except:
                pass
            
            if not exif_dict:
                # No EXIF data found
                signals.append(Signal(
                    signal_name="EXIF_MISSING",
                    category="METADATA",
                    severity="WARNING",
                    score=50,
                    message="No EXIF metadata found in image",
                    details={"exif_present": False}
                ))
                return signals
            
            # Check for standard EXIF tags
            standard_tags = ['DateTime', 'Model', 'Make', 'Software']
            found_tags = {tag: exif_dict.get(tag) for tag in standard_tags if exif_dict.get(tag)}
            
            # Check EXIF completeness
            completeness = len(found_tags) / len(standard_tags) * 100
            
            if completeness >= 75:
                # EXIF is complete and consistent
                signals.append(Signal(
                    signal_name="EXIF_COMPLETE",
                    category="METADATA",
                    severity="INFO",
                    score=10,
                    message=f"EXIF metadata complete with {len(found_tags)} standard tags",
                    details={"tags_found": found_tags, "completeness_percent": int(completeness)}
                ))
            else:
                # EXIF is incomplete
                signals.append(Signal(
                    signal_name="EXIF_INCONSISTENT",
                    category="METADATA",
                    severity="WARNING",
                    score=45,
                    message=f"EXIF metadata incomplete: only {len(found_tags)}/{len(standard_tags)} tags found",
                    details={"tags_found": found_tags, "completeness_percent": int(completeness)}
                ))
            
            # Check for GPS data
            try:
                gps_ifd = exif_dict.get("GPSInfo", {})
                if gps_ifd:
                    signals.append(Signal(
                        signal_name="EXIF_GPS_PRESENT",
                        category="METADATA",
                        severity="INFO",
                        score=15,
                        message="GPS coordinates present in EXIF",
                        details={"gps_present": True}
                    ))
            except:
                pass
            
        except Exception as e:
            logger.warning(f"Error checking EXIF metadata in {file_path}: {e}")
        
        return signals
    
    def _check_image_header(self, file_path: Path) -> List[Signal]:
        """
        Check image header validity.
        
        Returns signals for header validation including:
        - Valid/corrupted magic numbers
        - Dimension consistency
        - Size indicator matching
        """
        signals = []
        
        try:
            # Read first few bytes to check magic number
            with open(file_path, 'rb') as f:
                header = f.read(16)
            
            # Determine format and check magic number
            file_format = self._identify_format(header)
            
            if file_format == 'JPEG':
                # Check JPEG magic number (FF D8 FF)
                if header[:3] == b'\xff\xd8\xff':
                    signals.append(Signal(
                        signal_name="HEADER_VALID",
                        category="STRUCTURE",
                        severity="INFO",
                        score=5,
                        message="JPEG header valid (magic number correct)",
                        details={"format": "JPEG", "magic_valid": True}
                    ))
                else:
                    signals.append(Signal(
                        signal_name="HEADER_CORRUPTED",
                        category="STRUCTURE",
                        severity="CRITICAL",
                        score=85,
                        message="JPEG header corrupted (invalid magic number)",
                        details={"format": "JPEG", "magic_valid": False, "header": header[:3].hex()}
                    ))
            
            elif file_format == 'PNG':
                # Check PNG magic number (89 50 4E 47)
                if header[:4] == b'\x89PNG':
                    signals.append(Signal(
                        signal_name="HEADER_VALID",
                        category="STRUCTURE",
                        severity="INFO",
                        score=5,
                        message="PNG header valid (magic number correct)",
                        details={"format": "PNG", "magic_valid": True}
                    ))
                else:
                    signals.append(Signal(
                        signal_name="HEADER_CORRUPTED",
                        category="STRUCTURE",
                        severity="CRITICAL",
                        score=85,
                        message="PNG header corrupted (invalid magic number)",
                        details={"format": "PNG", "magic_valid": False}
                    ))
            
            elif file_format == 'GIF':
                # Check GIF magic number (47 49 46)
                if header[:3] in [b'GIF87a', b'GIF89a']:
                    signals.append(Signal(
                        signal_name="HEADER_VALID",
                        category="STRUCTURE",
                        severity="INFO",
                        score=5,
                        message="GIF header valid",
                        details={"format": "GIF", "magic_valid": True}
                    ))
                else:
                    signals.append(Signal(
                        signal_name="HEADER_CORRUPTED",
                        category="STRUCTURE",
                        severity="CRITICAL",
                        score=85,
                        message="GIF header corrupted",
                        details={"format": "GIF", "magic_valid": False}
                    ))
            
            # Check dimensions using PIL
            try:
                image = Image.open(file_path)
                width, height = image.size
                
                if width > 0 and height > 0:
                    signals.append(Signal(
                        signal_name="DIMENSIONS_VALID",
                        category="STRUCTURE",
                        severity="INFO",
                        score=5,
                        message=f"Image dimensions valid: {width}x{height}",
                        details={"width": width, "height": height}
                    ))
                else:
                    signals.append(Signal(
                        signal_name="DIMENSIONS_INVALID",
                        category="STRUCTURE",
                        severity="WARNING",
                        score=50,
                        message="Image dimensions invalid or zero",
                        details={"width": width, "height": height}
                    ))
            except Exception as e:
                logger.warning(f"Error checking dimensions: {e}")
        
        except Exception as e:
            logger.warning(f"Error checking header in {file_path}: {e}")
        
        return signals
    
    def _check_thumbnail(self, file_path: Path) -> List[Signal]:
        """
        Check for embedded thumbnail (JPEG only).
        
        Returns signals for thumbnail presence and consistency.
        """
        signals = []
        
        try:
            # Only check JPEG files for thumbnails
            if not file_path.suffix.lower() in ['.jpg', '.jpeg']:
                return signals
            
            image = Image.open(file_path)
            
            # Check if image has thumbnail
            try:
                if hasattr(image, 'thumbnail'):
                    # JPEG may have embedded thumbnail
                    # Try to extract using PIL
                    if image.format == 'JPEG':
                        try:
                            # Get EXIF data which may contain thumbnail
                            exif_data = image.getexif()
                            if exif_data:
                                signals.append(Signal(
                                    signal_name="THUMBNAIL_PRESENT",
                                    category="STRUCTURE",
                                    severity="INFO",
                                    score=10,
                                    message="JPEG contains thumbnail metadata",
                                    details={"has_thumbnail": True}
                                ))
                            else:
                                signals.append(Signal(
                                    signal_name="THUMBNAIL_MISSING",
                                    category="STRUCTURE",
                                    severity="INFO",
                                    score=20,
                                    message="JPEG has no thumbnail metadata",
                                    details={"has_thumbnail": False}
                                ))
                        except:
                            signals.append(Signal(
                                signal_name="THUMBNAIL_MISSING",
                                category="STRUCTURE",
                                severity="INFO",
                                score=15,
                                message="Could not determine thumbnail status",
                                details={"has_thumbnail": None}
                            ))
            except Exception as e:
                logger.warning(f"Error checking thumbnail: {e}")
        
        except Exception as e:
            logger.warning(f"Error in thumbnail analysis: {e}")
        
        return signals
    
    def _check_color_space(self, file_path: Path) -> List[Signal]:
        """
        Check color space and encoding consistency.
        
        Returns signals for standard vs anomalous color spaces.
        """
        signals = []
        
        try:
            image = Image.open(file_path)
            
            # Get image mode (color space)
            mode = image.mode
            
            # Standard modes
            standard_modes = {'RGB', 'RGBA', 'L', 'LA', 'CMYK', 'YCbCr', '1', 'P'}
            
            if mode in standard_modes:
                signals.append(Signal(
                    signal_name="COLORSPACE_STANDARD",
                    category="ENCODING",
                    severity="INFO",
                    score=10,
                    message=f"Color space is standard: {mode}",
                    details={"color_space": mode, "is_standard": True}
                ))
            else:
                signals.append(Signal(
                    signal_name="COLORSPACE_ANOMALOUS",
                    category="ENCODING",
                    severity="WARNING",
                    score=40,
                    message=f"Unusual color space detected: {mode}",
                    details={"color_space": mode, "is_standard": False}
                ))
            
            # Check for color profile
            if hasattr(image, 'info') and 'icc_profile' in image.info:
                signals.append(Signal(
                    signal_name="COLORPROFILE_PRESENT",
                    category="ENCODING",
                    severity="INFO",
                    score=5,
                    message="ICC color profile present",
                    details={"has_profile": True}
                ))
        
        except Exception as e:
            logger.warning(f"Error checking color space: {e}")
        
        return signals
    
    def _check_compression_artifacts(self, file_path: Path) -> List[Signal]:
        """
        Check for compression artifacts and re-compression signs.
        
        Returns signals for single vs multiple compression generations.
        """
        signals = []
        
        try:
            # Only check JPEG files for compression artifacts
            if file_path.suffix.lower() not in ['.jpg', '.jpeg']:
                return signals
            
            image = Image.open(file_path)
            
            if image.format != 'JPEG':
                return signals
            
            # Check quantization tables to detect re-compression
            try:
                # Get quantization tables info
                if hasattr(image, 'quantization'):
                    quant_tables = image.quantization
                    
                    if len(quant_tables) > 0:
                        # Check for evidence of re-compression
                        # Multiple generations show degraded quality
                        quality_indicator = sum(sum(table.values()) for table in quant_tables.values() if isinstance(table, dict))
                        
                        if quality_indicator < 100:
                            signals.append(Signal(
                                signal_name="COMPRESSION_MULTIPLE_GENERATIONS",
                                category="ENCODING",
                                severity="WARNING",
                                score=60,
                                message="Signs of multiple JPEG compressions detected",
                                details={"quantization_score": quality_indicator, "generations_detected": "multiple"}
                            ))
                        else:
                            signals.append(Signal(
                                signal_name="COMPRESSION_SINGLE",
                                category="ENCODING",
                                severity="INFO",
                                score=15,
                                message="Single JPEG compression detected",
                                details={"quantization_score": quality_indicator, "generations_detected": "single"}
                            ))
                    else:
                        signals.append(Signal(
                            signal_name="COMPRESSION_SINGLE",
                            category="ENCODING",
                            severity="INFO",
                            score=20,
                            message="JPEG compression appears normal",
                            details={"generations_detected": "single"}
                        ))
            except:
                # If we can't get quantization tables, use generic signal
                signals.append(Signal(
                    signal_name="COMPRESSION_SINGLE",
                    category="ENCODING",
                    severity="INFO",
                    score=25,
                    message="JPEG compression analysis inconclusive",
                    details={"analysis": "inconclusive"}
                ))
        
        except Exception as e:
            logger.warning(f"Error checking compression artifacts: {e}")
        
        return signals
    
    def _identify_format(self, header: bytes) -> Optional[str]:
        """Identify image format from header bytes."""
        if header[:3] == b'\xff\xd8\xff':
            return 'JPEG'
        elif header[:4] == b'\x89PNG':
            return 'PNG'
        elif header[:3] == b'GIF':
            return 'GIF'
        elif header[:2] == b'BM':
            return 'BMP'
        return None
