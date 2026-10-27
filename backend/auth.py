"""
Authentication & Authorization System.
Implements:
- Password hashing & verification using bcrypt
- JWT token signing & verification using PyJWT
- Role-based authorization: 'platform_admin' and 'business_owner'
- Tenant isolation dependencies preventing cross-tenant data tampering
- Admin API Key verification via environment configuration
"""

from datetime import datetime, timezone, timedelta
import hmac
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import bcrypt
import jwt
from jwt.exceptions import PyJWTError, ExpiredSignatureError, InvalidTokenError
from fastapi import HTTPException, status, Depends, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Roles
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_BUSINESS_OWNER = "business_owner"

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------------------
# Password Hashing & Verification
# ------------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    """Hash a plain text password using bcrypt with salt."""
    if not plain_password:
        return ""
    # bcrypt max length is 72 bytes
    pwd_bytes = plain_password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a stored bcrypt hash."""
    if not plain_password or not hashed_password:
        return False
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


# ------------------------------------------------------------------------------
# JWT Token Generation & Verification (PyJWT)
# ------------------------------------------------------------------------------

def create_access_token(
    data: Optional[Dict[str, Any]] = None,
    subject: Optional[str] = None,
    role: Optional[str] = None,
    business_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a signed JWT token containing claims.
    Standard claims:
      sub: Subject identifier (e.g. business_id or 'admin')
      role: Role identifier ('business_owner' or 'platform_admin')
      exp: Expiration UTC timestamp
      iat: Issued-at UTC timestamp
    """
    settings = get_settings()
    to_encode = data.copy() if data else {}
    if subject is not None:
        to_encode["sub"] = subject
    if role is not None:
        to_encode["role"] = role
    elif "role" not in to_encode:
        to_encode["role"] = "business_owner"
    if business_id is not None:
        to_encode["business_id"] = business_id
    elif "business_id" not in to_encode and to_encode.get("role") == "business_owner":
        to_encode["business_id"] = to_encode.get("sub")

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=settings.JWT_EXPIRE_HOURS)

    to_encode.update({
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    })

    secret = settings.effective_jwt_secret
    algorithm = settings.JWT_ALGORITHM
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT access token.
    Raises HTTPException(401) on expiration, tampered signature, or invalid format.
    """
    settings = get_settings()
    secret = settings.effective_jwt_secret
    algorithm = settings.JWT_ALGORITHM

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as e:
        logger.warning("JWT validation failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except PyJWTError as e:
        logger.warning("PyJWT decoding error: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ------------------------------------------------------------------------------
# Authenticated Principal Model
# ------------------------------------------------------------------------------

@dataclass
class AuthenticatedPrincipal:
    """Represents the verified authenticated entity for a request."""
    id: str
    role: str
    business_id: Optional[str] = None
    email: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_PLATFORM_ADMIN

    @property
    def is_business_owner(self) -> bool:
        return self.role == ROLE_BUSINESS_OWNER


# ------------------------------------------------------------------------------
# FastAPI Dependencies
# ------------------------------------------------------------------------------

def get_current_principal(
    request: Request,
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key"),
) -> AuthenticatedPrincipal:
    """
    Resolve the authenticated principal from either:
    1. An Admin API Key (via X-Admin-API-Key or Bearer token matching ADMIN_API_KEY)
    2. A verified JWT Bearer token signed by the platform
    """
    settings = get_settings()

    # 1. Check Admin API Key via Header
    admin_key_configured = settings.is_admin_configured
    if admin_key_configured and x_admin_api_key:
        if hmac.compare_digest(x_admin_api_key.strip(), settings.ADMIN_API_KEY.strip()):
            return AuthenticatedPrincipal(
                id="admin",
                role=ROLE_PLATFORM_ADMIN,
                business_id=None,
                email="admin@platform.local",
            )

    # 2. Check Authorization Bearer Header
    token = None
    if auth_credentials and auth_credentials.credentials:
        token = auth_credentials.credentials.strip()
    elif "authorization" in request.headers:
        auth_header = request.headers["authorization"].strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided. Include 'Authorization: Bearer <token>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Check if the Bearer token itself is the configured ADMIN_API_KEY
    if admin_key_configured and hmac.compare_digest(token, settings.ADMIN_API_KEY.strip()):
        return AuthenticatedPrincipal(
            id="admin",
            role=ROLE_PLATFORM_ADMIN,
            business_id=None,
            email="admin@platform.local",
        )

    # 4. Decode JWT
    payload = decode_access_token(token)
    sub = payload.get("sub")
    role = payload.get("role", ROLE_BUSINESS_OWNER)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject identity claim ('sub').",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if role == ROLE_PLATFORM_ADMIN:
        return AuthenticatedPrincipal(
            id=sub,
            role=ROLE_PLATFORM_ADMIN,
            business_id=None,
            email=payload.get("email", "admin@platform.local"),
        )

    # For business_owner: sub MUST be a registered business_id
    from backend.database.service import get_database_service
    db = get_database_service()
    if not db.business_exists(sub):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Business tenant '{sub}' referenced by token no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedPrincipal(
        id=sub,
        role=ROLE_BUSINESS_OWNER,
        business_id=sub,
        email=payload.get("email"),
    )


def verify_admin_key(
    request: Request,
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key"),
) -> AuthenticatedPrincipal:
    """
    Enforces Platform Admin authorization for supervisory admin endpoints.
    Accepts configured ADMIN_API_KEY (via header or Bearer) or a valid platform_admin JWT.
    """
    settings = get_settings()

    # If ADMIN_API_KEY is configured, check X-Admin-API-Key header
    if settings.is_admin_configured and x_admin_api_key:
        if hmac.compare_digest(x_admin_api_key.strip(), settings.ADMIN_API_KEY.strip()):
            return AuthenticatedPrincipal(
                id="admin",
                role=ROLE_PLATFORM_ADMIN,
                business_id=None,
                email="admin@platform.local",
            )

    # Check Bearer token
    token = None
    if auth_credentials and auth_credentials.credentials:
        token = auth_credentials.credentials.strip()
    elif "authorization" in request.headers:
        auth_header = request.headers["authorization"].strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    if token:
        # Check against ADMIN_API_KEY directly
        if settings.is_admin_configured and hmac.compare_digest(token, settings.ADMIN_API_KEY.strip()):
            return AuthenticatedPrincipal(
                id="admin",
                role=ROLE_PLATFORM_ADMIN,
                business_id=None,
                email="admin@platform.local",
            )

        # Check JWT platform_admin claim
        try:
            payload = decode_access_token(token)
            if payload.get("role") == ROLE_PLATFORM_ADMIN:
                return AuthenticatedPrincipal(
                    id=payload.get("sub", "admin"),
                    role=ROLE_PLATFORM_ADMIN,
                    business_id=None,
                    email=payload.get("email", "admin@platform.local"),
                )
        except Exception:
            pass

    # In development mode, if ADMIN_API_KEY is not configured, inform administrator clearly
    if not settings.is_admin_configured:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMIN_API_KEY is not configured in the environment. Platform admin endpoints are locked.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Valid platform admin credentials required. Provide 'X-Admin-API-Key' or 'Authorization: Bearer <key>'.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_business_access(
    business_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    """
    Enforces strict tenant isolation.
    Validates that the authenticated principal is either:
    1. A platform_admin
    2. A business_owner whose authenticated identity matches the requested `business_id` exactly.
    Prevents cross-tenant access and unauthorized tampering.
    """
    if principal.is_admin:
        return principal

    if principal.business_id != business_id:
        logger.warning(
            "Cross-tenant access attempt blocked: Principal '%s' attempted to access tenant '%s'",
            principal.id,
            business_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access another tenant's workspace.",
        )

    return principal


def get_current_business(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> Dict[str, Any]:
    """
    Retrieve the trusted business profile for the currently authenticated business owner.
    """
    if not principal.business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated principal has no tenant business context.",
        )

    from backend.database.service import get_database_service
    db = get_database_service()
    profile = db.get_business_profile(principal.business_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business profile '{principal.business_id}' not found.",
        )
    return profile
