"""OIDC bearer-token checks. The browser signs in with Authorization Code + PKCE (see web/); the API only
trusts access tokens whose signature, issuer, audience and expiry it can verify itself."""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    subject: str
    username: str
    roles: frozenset[str]


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().oidc_jwks_url, cache_keys=True)


def verify_token(token: str) -> User:
    settings = get_settings()
    try:
        key = _jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], audience=settings.oidc_audience, issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        # Don't echo token details back to the client or into logs.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
    roles = frozenset(claims.get("realm_access", {}).get("roles", []))
    return User(subject=claims["sub"], username=claims.get("preferred_username", ""), roles=roles)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return verify_token(creds.credentials)


def require_role(role: str):
    def check(user: User = Depends(current_user)) -> User:
        if role not in user.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires the '{role}' role")
        return user

    return check
