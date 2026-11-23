"""Vercel entrypoint.

Vercel's Python runtime looks for a FastAPI instance named `app` in supported
entrypoint files (app.py, index.py, server.py, main.py, asgi.py, wsgi.py).
"""

from voice_app import app  # noqa: F401
