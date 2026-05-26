"""
Authentication and authorization using KeyCloak
"""
import logging
import json
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel
from app.config import settings

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
        self.client_secret = settings.keycloak_client_secret
        self.jwks_url = f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/certs"
        self._jwks_cache = None

    async def get_jwks(self):
        """Fetch JWKS from KeyCloak"""
        if self._jwks_cache is None:
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(self.jwks_url)
                    response.raise_for_status()
                    self._jwks_cache = response.json()
            except Exception as e:
                logger.error(f"Failed to fetch JWKS: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to fetch authentication keys"
                )
        return self._jwks_cache

    async def verify_token(self, token: str) -> TokenData:
        """Verify JWT token from KeyCloak"""
        try:
            # Decode without verification first to get the header
            unverified_header = jwt.get_unverified_header(token)

            # Get JWKS
            jwks = await self.get_jwks()

            # Find the key
            key = None
            for k in jwks.get("keys", []):
                if k.get("kid") == unverified_header.get("kid"):
                    key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(k))
                    break

            if key is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token"
                )

            # Verify token
            payload = jwt.decode(
                token,
                key,
                algorithms=[settings.jwt_algorithm],
                audience=self.client_id,
                issuer=f"{self.server_url}/realms/{self.realm}"
            )

            return TokenData(**payload)

        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired"
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
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

