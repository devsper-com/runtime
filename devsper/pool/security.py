from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import jwt


@dataclass
class AuditHook:
    append: callable  # append(dict) -> None


def verify_worker_jwt(
    token: str,
    *,
    org_id: str,
    public_key_pem: str,
    leeway_seconds: int = 30,
) -> dict[str, Any]:
    """
    Workers present a short-lived JWT when registering/heartbeating.
    This verifies signature + org scope + expiry.
    """
    claims = jwt.decode(
        token,
        public_key_pem,
        algorithms=["ES256"],
        options={"require": ["exp", "iat"]},
        leeway=leeway_seconds,
    )
    tok_org = str(claims.get("org_id") or "")
    if tok_org != org_id:
        raise ValueError("org_mismatch")
    return claims


def now_s() -> int:
    return int(time.time())

