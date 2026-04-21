"""Minimal FastAPI runtime shell for the clean RSL runtime contour."""

from .api.factory import create_app

__all__ = ["create_app"]
