"""
Input validation module for the Upload & Fingerprint system.
Provides validation functions for file size, extension, and required parameters.
"""

from .config import MAX_FILE_SIZE, is_allowed_extension, get_supported_formats_message


def validate_file_size(file_size: int) -> None:
    """
    Validate file size is within acceptable limits.
    
    Args:
        file_size: File size in bytes
        
    Raises:
        ValueError: If file size is 0 bytes or exceeds maximum limit
        
    Requirements: 1.5, 1.6
    """
    if file_size <= 0:
        raise ValueError("File size must be greater than 0 bytes")
    
    if file_size > MAX_FILE_SIZE:
        raise ValueError("File size exceeds maximum limit of 500 MB")


def validate_file_extension(filename: str) -> None:
    """
    Validate file extension against allowed extensions list.
    
    Args:
        filename: Original filename to extract extension from
        
    Raises:
        ValueError: If file extension is not in allowed list
        
    Requirements: 1.7, 1.8
    """
    if not filename or '.' not in filename:
        raise ValueError(f"Invalid filename format. {get_supported_formats_message()}")
    
    # Extract extension (everything after the last dot, lowercase)
    file_extension = filename.rsplit('.', 1)[-1].lower()
    
    if not is_allowed_extension(file_extension):
        raise ValueError(f"Unsupported file format. {get_supported_formats_message()}")


def validate_required_params(uploader_id: str, collection_method: str) -> None:
    """
    Validate that required parameters are provided and non-empty.
    
    Args:
        uploader_id: Identifier for the investigator who uploaded the file
        collection_method: Description of how the evidence was collected
        
    Raises:
        ValueError: If either parameter is missing or empty
        
    Requirements: 1.2, 1.3, 1.8
    """
    if not uploader_id or not uploader_id.strip():
        raise ValueError("Uploader_ID and Collection_Method are required")
    
    if not collection_method or not collection_method.strip():
        raise ValueError("Uploader_ID and Collection_Method are required")