"""
Configuration constants for the Upload & Fingerprint module.
Hackathon-optimized settings for rapid development.
"""

from pathlib import Path
from typing import Dict

# File handling constants
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB in bytes
MAX_BATCH_FILES = 100
MAX_BATCH_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB in bytes
MAX_HASH_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB in bytes

# Timeout constants (seconds)
HASH_COMPUTATION_TIMEOUT = 300  # 5 minutes
METADATA_EXTRACTION_TIMEOUT = 30  # 30 seconds
VERIFICATION_TIMEOUT = 300  # 5 minutes

# Authentication Engine constants
AUTHENTICATION_TIMEOUT = 300  # 5 minutes in seconds
MAX_AUTH_FILE_SIZE = 1 * 1024 * 1024 * 1024  # 1 GB in bytes
ANALYZER_VERSION = "1.0.0"

# Allowed file extensions (hackathon-optimized whitelist)
ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'bmp',  # Images
    'mp4', 'mov', 'avi',                   # Videos
    'txt', 'log', 'json', 'csv'           # Text/Data files
}

# Extension-based MIME type mapping (simplified for hackathon)
MIME_TYPE_MAP: Dict[str, str] = {
    # Images
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg', 
    'png': 'image/png',
    'gif': 'image/gif',
    'bmp': 'image/bmp',
    
    # Videos
    'mp4': 'video/mp4',
    'mov': 'video/quicktime',
    'avi': 'video/x-msvideo',
    
    # Text/Data files
    'txt': 'text/plain',
    'log': 'text/plain',
    'json': 'application/json',
    'csv': 'text/csv'
}

# Storage paths
EVIDENCE_STORAGE_DIR = Path("./evidence_storage")
DATABASE_PATH = Path("./forensix.db")

# Hash algorithm
HASH_ALGORITHM = "sha256"
HASH_CHUNK_SIZE = 8192  # 8KB chunks for streaming

# Chain of custody action types
class ActionType:
    UPLOAD = "UPLOAD"
    ACCESS = "ACCESS" 
    VERIFY = "VERIFY"
    AUTHENTICATE = "AUTHENTICATE"

# Timestamp format
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"  # ISO 8601 with millisecond precision

# Database constraints
MAX_FILENAME_LENGTH = 255
MAX_MIME_TYPE_LENGTH = 100
MAX_FILE_EXTENSION_LENGTH = 10
MAX_UPLOADER_ID_LENGTH = 100
MAX_COLLECTION_METHOD_LENGTH = 1000
MAX_METADATA_SIZE = 1024 * 1024  # 1 MB JSON metadata limit

def get_mime_type_from_extension(file_extension: str) -> str:
    """
    Get MIME type from file extension using extension-based lookup.
    
    Args:
        file_extension: File extension (without dot, lowercase)
        
    Returns:
        MIME type string, defaults to 'application/octet-stream' for unknown extensions
    """
    return MIME_TYPE_MAP.get(file_extension.lower(), 'application/octet-stream')

def is_allowed_extension(file_extension: str) -> bool:
    """
    Check if file extension is in allowed list.
    
    Args:
        file_extension: File extension (without dot)
        
    Returns:
        True if extension is allowed, False otherwise
    """
    return file_extension.lower() in ALLOWED_EXTENSIONS

def get_supported_formats_message() -> str:
    """
    Get formatted message listing all supported file formats.
    
    Returns:
        Human-readable string listing supported extensions
    """
    sorted_extensions = sorted(ALLOWED_EXTENSIONS)
    return f"Supported formats: {', '.join(sorted_extensions)}"


def is_supported_for_authentication(mime_type: str) -> bool:
    """
    Check if MIME type is supported for authentication analysis.
    
    Args:
        mime_type: MIME type string (e.g., 'image/jpeg', 'video/mp4')
        
    Returns:
        True if MIME type is image/* or video/*, False otherwise
    """
    return mime_type.startswith('image/') or mime_type.startswith('video/')


def get_analyzer_version() -> str:
    """
    Get the current authentication analyzer version.
    
    Returns:
        Version string in format "X.Y.Z"
    """
    return ANALYZER_VERSION
