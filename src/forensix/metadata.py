"""
Metadata extraction functions for the Upload & Fingerprint module.

This module provides functions to extract file system metadata and embedded metadata
from evidence files (images and videos).
"""

from pathlib import Path
from typing import Dict, Any
from fastapi import UploadFile
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import ffmpeg
from .config import get_mime_type_from_extension


def extract_file_metadata(file: UploadFile, file_path: str) -> dict:
    """
    Extract file system metadata from an uploaded file.
    
    Captures:
    - Original filename
    - File size in bytes
    - MIME type (using get_mime_type_from_extension from config)
    - File extension (lowercase, without dot)
    
    Args:
        file: The uploaded file object (FastAPI UploadFile)
        file_path: Path to the stored file on disk
        
    Returns:
        Dictionary containing:
        - original_filename: str - Original name of the uploaded file
        - file_size: int - Size in bytes
        - mime_type: str - MIME type of the file
        - file_extension: str - File extension (lowercase, without dot)
        
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
    """
    # Extract original filename from the uploaded file
    original_filename = file.filename if file.filename else "unknown"
    
    # Get file size from the stored file
    path_obj = Path(file_path)
    file_size = path_obj.stat().st_size if path_obj.exists() else 0
    
    # Extract file extension (lowercase, without the dot)
    file_extension = Path(original_filename).suffix.lower().lstrip('.')
    if not file_extension:
        file_extension = ""
    
    # Get MIME type from extension using config function
    mime_type = get_mime_type_from_extension(file_extension)
    
    return {
        "original_filename": original_filename,
        "file_size": file_size,
        "mime_type": mime_type,
        "file_extension": file_extension
    }


def extract_exif_metadata(file_path: str) -> dict:
    """
    Extract EXIF metadata from image files (jpg, jpeg, png).
    
    Extracts:
    - GPS coordinates (latitude, longitude)
    - Camera information (make, model)
    - DateTimeOriginal timestamp
    
    Args:
        file_path: Path to the image file on disk
        
    Returns:
        Dictionary containing extracted EXIF data:
        - gps_latitude: float or None
        - gps_longitude: float or None
        - camera_make: str or None
        - camera_model: str or None
        - datetime_original: str or None
        
        Returns empty dict {} on any extraction failure (graceful degradation).
        Only processes image extensions: jpg, jpeg, png
        
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
    """
    try:
        # Check if file extension is supported (jpg, jpeg, png)
        path_obj = Path(file_path)
        file_extension = path_obj.suffix.lower().lstrip('.')
        
        if file_extension not in {'jpg', 'jpeg', 'png'}:
            return {}
        
        # Open the image and extract EXIF data
        with Image.open(file_path) as img:
            exif_data = img._getexif()
            
            # If no EXIF data exists, return empty dict
            if exif_data is None:
                return {}
            
            # Initialize result dictionary
            result = {
                "gps_latitude": None,
                "gps_longitude": None,
                "camera_make": None,
                "camera_model": None,
                "datetime_original": None
            }
            
            # Extract camera make and model
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, tag_id)
                
                if tag_name == "Make":
                    result["camera_make"] = str(value).strip()
                elif tag_name == "Model":
                    result["camera_model"] = str(value).strip()
                elif tag_name == "DateTimeOriginal":
                    result["datetime_original"] = str(value).strip()
                elif tag_name == "GPSInfo":
                    # Extract GPS coordinates
                    gps_info = {}
                    for gps_tag_id in value:
                        gps_tag_name = GPSTAGS.get(gps_tag_id, gps_tag_id)
                        gps_info[gps_tag_name] = value[gps_tag_id]
                    
                    # Convert GPS coordinates to decimal degrees
                    if "GPSLatitude" in gps_info and "GPSLatitudeRef" in gps_info:
                        lat = _convert_to_degrees(gps_info["GPSLatitude"])
                        if lat is not None:
                            if gps_info["GPSLatitudeRef"] == "S":
                                lat = -lat
                            result["gps_latitude"] = lat
                    
                    if "GPSLongitude" in gps_info and "GPSLongitudeRef" in gps_info:
                        lon = _convert_to_degrees(gps_info["GPSLongitude"])
                        if lon is not None:
                            if gps_info["GPSLongitudeRef"] == "W":
                                lon = -lon
                            result["gps_longitude"] = lon
            
            return result
            
    except Exception:
        # Graceful degradation: return empty dict on any failure
        return {}


def _convert_to_degrees(value) -> float | None:
    """
    Helper function to convert GPS coordinates from degrees/minutes/seconds to decimal degrees.
    
    Args:
        value: GPS coordinate value in the format (degrees, minutes, seconds)
        
    Returns:
        Decimal degrees as float, or None if conversion fails
    """
    try:
        d, m, s = value
        # Convert tuples to floats
        d = float(d[0]) / float(d[1]) if isinstance(d, tuple) else float(d)
        m = float(m[0]) / float(m[1]) if isinstance(m, tuple) else float(m)
        s = float(s[0]) / float(s[1]) if isinstance(s, tuple) else float(s)
        
        return d + (m / 60.0) + (s / 3600.0)
    except (ValueError, TypeError, ZeroDivisionError, IndexError):
        return None


def extract_video_metadata(file_path: str) -> dict:
    """
    Extract metadata from video files (mp4, mov, avi).
    
    Extracts:
    - Duration in seconds
    - Resolution (width and height in pixels)
    - Codec information
    - Creation timestamp (if available)
    
    Args:
        file_path: Path to the video file on disk
        
    Returns:
        Dictionary containing extracted video metadata:
        - duration: float or None - Duration in seconds
        - width: int or None - Video width in pixels
        - height: int or None - Video height in pixels
        - codec: str or None - Codec name
        - creation_timestamp: str or None - Creation timestamp
        
        Returns empty dict {} on any extraction failure (graceful degradation).
        Only processes video extensions: mp4, mov, avi
        
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
    """
    try:
        # Check if file extension is supported (mp4, mov, avi)
        path_obj = Path(file_path)
        file_extension = path_obj.suffix.lower().lstrip('.')
        
        if file_extension not in {'mp4', 'mov', 'avi'}:
            return {}
        
        # Use ffmpeg.probe to extract video metadata
        probe = ffmpeg.probe(file_path)
        
        # Initialize result dictionary
        result = {
            "duration": None,
            "width": None,
            "height": None,
            "codec": None,
            "creation_timestamp": None
        }
        
        # Extract format-level duration
        if 'format' in probe and 'duration' in probe['format']:
            try:
                result["duration"] = float(probe['format']['duration'])
            except (ValueError, TypeError):
                pass
        
        # Extract creation timestamp from format tags if available
        if 'format' in probe and 'tags' in probe['format']:
            tags = probe['format']['tags']
            # Try different possible tag names for creation time
            for tag_name in ['creation_time', 'date', 'DATE']:
                if tag_name in tags:
                    result["creation_timestamp"] = str(tags[tag_name]).strip()
                    break
        
        # Find the first video stream and extract its metadata
        video_streams = [stream for stream in probe.get('streams', []) 
                        if stream.get('codec_type') == 'video']
        
        if video_streams:
            video_stream = video_streams[0]
            
            # Extract codec
            if 'codec_name' in video_stream:
                result["codec"] = str(video_stream['codec_name']).strip()
            
            # Extract resolution
            if 'width' in video_stream:
                try:
                    result["width"] = int(video_stream['width'])
                except (ValueError, TypeError):
                    pass
            
            if 'height' in video_stream:
                try:
                    result["height"] = int(video_stream['height'])
                except (ValueError, TypeError):
                    pass
            
            # If duration wasn't at format level, try stream level
            if result["duration"] is None and 'duration' in video_stream:
                try:
                    result["duration"] = float(video_stream['duration'])
                except (ValueError, TypeError):
                    pass
            
            # Try to get creation timestamp from stream tags if not found at format level
            if result["creation_timestamp"] is None and 'tags' in video_stream:
                stream_tags = video_stream['tags']
                for tag_name in ['creation_time', 'date', 'DATE']:
                    if tag_name in stream_tags:
                        result["creation_timestamp"] = str(stream_tags[tag_name]).strip()
                        break
        
        return result
        
    except Exception:
        # Graceful degradation: return empty dict on any failure
        return {}
