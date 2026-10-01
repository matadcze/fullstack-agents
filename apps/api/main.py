"""Application entry point for uvicorn.

Run with: uvicorn main:app --reload --no-proxy-headers
"""

from src.api.app import app

__all__ = ["app"]
