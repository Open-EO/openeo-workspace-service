"""
Keycloak OIDC authentication and authorisation layer.

Flow:
  1. Client sends `Authorization: Bearer <access_token>` (Keycloak JWT).
  2. `verify_token()` fetches the JWKS from Keycloak and validates the token.
  3. `get_current_user()` is a FastAPI dependency that returns a `TokenClaims` object.
  4. `require_workspace_owner()` checks that the authenticated user owns the
     requested workspace (the token `sub` must match the stored `owner_id`).

JWKS keys are cached in-process and refreshed when a `kid` is not found.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JWKError
from pydantic import BaseModel

from openeo_workspace_service.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# JWKS key cache
# ---------------------------------------------------------------------------

_jwks_cache: dict[str, Any] = {}      # kid -> JWK dict
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 300.0  # seconds


async def _fetch_jwks(settings: Settings) -> dict[str, Any]:
    """Fetch JWKS from Keycloak and return a dict keyed by `kid`."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(settings.oidc_jwks_uri)
        response.raise_for_status()
        keys = response.json().get("keys", [])
        return {k["kid"]: k for k in keys}


async def _get_jwks(settings: Settings) -> dict[str, Any]:
    """Return cached JWKS, refreshing if stale."""
    global _jwks_cache, _jwks_fetched_at
    if not _jwks_cache or (time.monotonic() - _jwks_fetched_at) > _JWKS_TTL:
        _jwks_cache = await _fetch_jwks(settings)
        _jwks_fetched_at = time.monotonic()
    return _jwks_cache


async def _get_signing_key(kid: str, settings: Settings) -> dict[str, Any] | None:
    """Return the JWK for `kid`, refreshing the cache once if not found."""
    jwks = await _get_jwks(settings)
    if kid not in jwks:
        # Force a refresh in case of key rotation
        global _jwks_cache, _jwks_fetched_at
        _jwks_fetched_at = 0.0
        jwks = await _get_jwks(settings)
    return jwks.get(kid)


# ---------------------------------------------------------------------------
# Token model
# ---------------------------------------------------------------------------


class TokenClaims(BaseModel):
    """Validated claims extracted from the Keycloak access token."""

    sub: str           # unique user identifier
    preferred_username: str | None = None
    email: str | None = None
    realm_access: dict[str, Any] | None = None   # Keycloak realm roles
    resource_access: dict[str, Any] | None = None  # Keycloak client roles
    raw: dict[str, Any]

    @property
    def roles(self) -> list[str]:
        """Return flattened list of realm-level roles."""
        if self.realm_access:
            return self.realm_access.get("roles", [])
        return []

    def has_role(self, role: str) -> bool:
        return role in self.roles


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


async def verify_token(token: str, settings: Settings) -> TokenClaims:
    """
    Validate the JWT and return extracted claims.

    Raises HTTP 401 on any failure.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode header without verification to extract `kid`
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        logger.debug("failed to decode jwt header", error=str(exc))
        raise credentials_error from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise credentials_error

    signing_key = await _get_signing_key(kid, settings)
    if signing_key is None:
        logger.warning("unknown jwt kid", kid=kid)
        raise credentials_error

    audience = settings.jwt_audience or settings.keycloak_client_id

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key,
            algorithms=settings.jwt_algorithms,
            audience=audience,
            issuer=settings.oidc_issuer,
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except JWTError as exc:
        logger.debug("jwt validation failed", error=str(exc))
        raise credentials_error from exc

    if "sub" not in payload:
        raise credentials_error

    return TokenClaims(
        sub=payload["sub"],
        preferred_username=payload.get("preferred_username"),
        email=payload.get("email"),
        realm_access=payload.get("realm_access"),
        resource_access=payload.get("resource_access"),
        raw=payload,
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> TokenClaims:
    """
    Require a valid Bearer token.  Raises HTTP 401 if missing or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await verify_token(credentials.credentials, settings)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> TokenClaims | None:
    """
    Return token claims if a valid Bearer is present, or None for anonymous requests.
    Used by endpoints that are public but behaviour-aware of authenticated users.
    """
    if credentials is None:
        return None
    try:
        return await verify_token(credentials.credentials, settings)
    except HTTPException:
        return None


class RequireRole:
    """
    FastAPI dependency factory that enforces a Keycloak realm role.

    Usage::

        @router.get("/admin")
        async def admin(user: TokenClaims = Depends(RequireRole("workspace-admin"))):
            ...
    """

    def __init__(self, role: str) -> None:
        self._role = role

    async def __call__(
        self, user: TokenClaims = Depends(get_current_user)
    ) -> TokenClaims:
        if not user.has_role(self._role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{self._role}' is required.",
            )
        return user
