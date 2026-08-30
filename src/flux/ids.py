from __future__ import annotations

import uuid


def new_id() -> str:
    """Generate an opaque, URL-safe, collision-resistant identifier."""
    return uuid.uuid4().hex
