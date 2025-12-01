"""
Placeholder Telegram bot interface.
Wire commands to start/stop strategies or check status.
"""
from __future__ import annotations

def start_bot(token: str, allow_users: list[str], engine) -> None:
    """
    Implement your bot wiring here. The `engine` can expose methods to query
    positions, PnL, or pause/start strategies.
    """
    raise NotImplementedError("Implement Telegram bot commands here.")
