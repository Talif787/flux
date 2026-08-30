from __future__ import annotations

import hashlib


def fingerprint(tenant_id: str, method: str, path: str, body: bytes) -> str:
    """Stable hash identifying a request for idempotency-key reuse checks."""
    digest = hashlib.sha256()
    for part in (tenant_id, method, path):
        digest.update(part.encode())
        digest.update(b"\x00")
    digest.update(body)
    return digest.hexdigest()
