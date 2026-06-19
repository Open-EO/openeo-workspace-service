"""
Authentication and authorization using KeyCloak
"""
import asyncio
import json
import logging
import time
from typing import Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from workspace_service.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

class TokenData(BaseModel):
    """JWT token data"""
    sub: str  # subject (user ID)
    iat: int  # issued at
    exp: int  # expiration
    iss: str  # issuer
    aud: Optional[str] = None  # audience
    scope: Optional[str] = None
    preferred_username: Optional[str] = None
    email: Optional[str] = None

class KeyCloakManager:
    """Manage KeyCloak authentication and token verification"""

    def __init__(self):
        self.server_url = settings.keycloak_server_url.rstrip("/")
        self.realm = settings.keycloak_realm
        self.client_id = settings.keycloak_client_id
        self.verify_tls = settings.keycloak_verify_tls

        default_issuer = f"{self.server_url}/realms/{self.realm}"
        self.issuer = (settings.keycloak_issuer or default_issuer).rstrip("/")
        self.discovery_url = (
            f"{self.server_url}/realms/{self.realm}/.well-known/openid-configuration"
        )
        self.jwks_url = f"{self.issuer}/protocol/openid-connect/certs"

        self.jwks_cache_ttl_seconds = settings.keycloak_jwks_cache_ttl_seconds
        self._jwks_cache = None
        self._jwks_cache_expires_at = 0.0
        self._jwks_lock = asyncio.Lock()

    async def _discover_oidc_configuration(self) -> None:
        """Load issuer/JWKS URI from Keycloak's OIDC discovery endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=self.verify_tls) as client:
                response = await client.get(self.discovery_url)
                response.raise_for_status()
                config = response.json()

            discovered_issuer = config.get("issuer")
            discovered_jwks_uri = config.get("jwks_uri")
            if discovered_issuer:
                self.issuer = discovered_issuer.rstrip("/")
            if discovered_jwks_uri:
                self.jwks_url = discovered_jwks_uri
        except Exception as exc:
            # Continue with fallback URLs so development setups remain usable.
            logger.warning("Failed OIDC discovery at %s: %s", self.discovery_url, exc)

    async def get_jwks(self):
        """Fetch JWKS from KeyCloak"""
        now = time.time()
        if self._jwks_cache is not None and now < self._jwks_cache_expires_at:
            return self._jwks_cache

        async with self._jwks_lock:
            now = time.time()
            if self._jwks_cache is not None and now < self._jwks_cache_expires_at:
                return self._jwks_cache
            try:
                await self._discover_oidc_configuration()
                async with httpx.AsyncClient(timeout=10.0, verify=self.verify_tls) as client:
                    response = await client.get(self.jwks_url)
                    response.raise_for_status()
                    self._jwks_cache = response.json()
                    self._jwks_cache_expires_at = now + self.jwks_cache_ttl_seconds
            except Exception as exc:
                logger.error("Failed to fetch JWKS from %s: %s", self.jwks_url, exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service unavailable",
                )
        return self._jwks_cache

    async def _get_signing_key(self, token: str):
        """Get the public key matching the token's key id (kid)."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            logger.warning("Invalid token header: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        jwks = await self.get_jwks()
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))

        # Token key may be rotated: refresh cache once and retry.
        self._jwks_cache = None
        self._jwks_cache_expires_at = 0.0
        jwks = await self.get_jwks()
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    @staticmethod
    def _matches_client(audience_claim, client_id: str) -> bool:
        """Validate a Keycloak audience claim against the configured client id."""
        if audience_claim is None:
            return False
        if isinstance(audience_claim, str):
            return audience_claim == client_id
        if isinstance(audience_claim, list):
            return client_id in audience_claim
        return False

    async def verify_token(self, token: str) -> TokenData:
        """Verify JWT token from KeyCloak"""
        try:
            key = await self._get_signing_key(token)
            payload = jwt.decode(
                token,
                key,
                algorithms=[settings.jwt_algorithm],
                issuer=self.issuer,
                options={"verify_aud": False},
            )

            if settings.keycloak_verify_audience:
                aud = payload.get("aud")
                azp = payload.get("azp")
                if not (
                    self._matches_client(aud, self.client_id)
                    or azp == self.client_id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token audience",
                    )

            return TokenData(**payload)

        except HTTPException:
            raise
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        except Exception as exc:
            logger.error("Unexpected authentication error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

# Initialize KeyCloak manager
keycloak_manager = KeyCloakManager()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """FastAPI dependency to verify JWT token"""
    token = credentials.credentials
    return await keycloak_manager.verify_token(token)

async def verify_token_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security)
) -> Optional[TokenData]:
    """FastAPI dependency for optional authentication"""
    if credentials is None:
        return None
    token = credentials.credentials
    return await keycloak_manager.verify_token(token)
