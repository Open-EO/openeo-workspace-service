"""
openeo_workspace_service/auth.py
----------------------------------
FastAPI dependency that validates the ``Authorization: Bearer …`` header.

When ``OPENEO_WS_OIDC_DISCOVERY_URL`` is set the token is verified against the
OIDC provider's JWKS.  When it is empty (default / dev mode) the token is
treated as an opaque *user identifier* – useful for testing without a real IdP.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from openeo_workspace_service.config import settings

logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def _get_oidc_config() -> dict | None:
    if not settings.oidc_discovery_url:
        return None
    resp = httpx.get(settings.oidc_discovery_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _verify_token(token: str) -> str:
    """Return the *sub* claim (user id) or raise 401."""
    oidc_config = _get_oidc_config()
    if oidc_config is None:
        # Dev mode – treat the raw token string as the user id.
        logger.debug("OIDC disabled: using token as user id")
        return token

    from jose import JWTError, jwk, jwt  # type: ignore[import]

    try:
        jwks_uri = oidc_config["jwks_uri"]
        jwks_resp = httpx.get(jwks_uri, timeout=10)
        jwks_resp.raise_for_status()
        keys = jwks_resp.json()["keys"]
        unverified_header = jwt.get_unverified_header(token)
        key = next(
            (k for k in keys if k.get("kid") == unverified_header.get("kid")),
            keys[0] if keys else None,
        )
        if key is None:
            raise ValueError("No matching JWK found")
        public_key = jwk.construct(key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[unverified_header.get("alg", "RS256")],
            options={"verify_aud": False},
        )
        return payload["sub"]
    except (JWTError, KeyError, ValueError) as exc:
        logger.warning("Token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """FastAPI dependency – returns the authenticated user's *sub* / identifier."""
    return _verify_token(credentials.credentials)
