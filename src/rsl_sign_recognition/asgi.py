"""ASGI entrypoint for the clean runtime shell."""

from .api.factory import create_app

app = create_app()
