#!/usr/bin/env python3
"""
Main entry point for the ForensiX Upload & Fingerprint service.
"""

import uvicorn
from src.forensix.app import app

if __name__ == "__main__":
    uvicorn.run(
        "src.forensix.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )