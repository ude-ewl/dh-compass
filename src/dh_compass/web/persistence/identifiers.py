"""Stable identifier and timestamp helpers for persisted web records."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def new_identifier() -> str:
    """Return an opaque, URL-safe identifier for an application record."""

    return str(uuid4())


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp suitable for persistence/API use."""

    return datetime.now(timezone.utc)


# Short aliases keep repository code readable without changing the opaque ID
# contract exposed to API consumers.
new_id = new_identifier
now_utc = utc_now


__all__ = ["new_identifier", "new_id", "now_utc", "utc_now"]
