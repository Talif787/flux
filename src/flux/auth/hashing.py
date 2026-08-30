from __future__ import annotations

import hashlib
import hmac
import secrets

API_KEY_PREFIX = "flux_"
PREFIX_DISPLAY_LEN = 12


def generate_api_key() -> str:
    """Generate a new high-entropy API key with a recognisable prefix."""
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str, pepper: str) -> str:
    """Keyed (HMAC-SHA256) hash of a high-entropy API key.

    API keys carry sufficient entropy that a fast keyed hash is appropriate;
    slow password hashes (argon2) are unnecessary and would tax the hot path.
    """
    return hmac.new(pepper.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def key_prefix(raw_key: str) -> str:
    """The non-secret display prefix stored to identify a key in listings."""
    return raw_key[:PREFIX_DISPLAY_LEN]
