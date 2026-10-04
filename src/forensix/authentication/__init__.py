"""
Authentication Engine module for ForensiX.
Provides intelligent authenticity verification for digital evidence.
"""

from .analyzer import AuthenticationAnalyzer
from .models import Signal, AuthenticationResult

__all__ = ['AuthenticationAnalyzer', 'Signal', 'AuthenticationResult']
