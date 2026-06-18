"""Live rail data provider: erail.in (route) + confirmtkt (availability/fare)."""
from app.providers.irctc.provider import IRCTCRailDataProvider

__all__ = ["IRCTCRailDataProvider"]
