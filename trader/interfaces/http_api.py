"""
Placeholder HTTP API interface.
"""
from __future__ import annotations


def create_app(engine=None):
    """
    Return a configured web app (FastAPI/Flask/etc) that proxies to the engine.
    """
    raise NotImplementedError("Implement HTTP API here.")
