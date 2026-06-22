"""Application entry point for uvicorn.

Run with: uvicorn main:app --reload
"""

from src.api.app import app

__all__ = ["app"]
