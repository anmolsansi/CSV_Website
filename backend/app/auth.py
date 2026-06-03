import time

import jwt
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import OAuthIdentity, User

SUPPORTED_PROVIDERS = ("google", "microsoft", "apple")

oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="microsoft",
    client_id=settings.MICROSOFT_CLIENT_ID,
    client_secret=settings.MICROSOFT_CLIENT_SECRET,
    server_metadata_url=(
        f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT}"
        "/v2.0/.well-known/openid-configuration"
    ),
    client_kwargs={"scope": "openid email profile"},
)


def _apple_client_secret() -> str:
    """Apple requires the client secret to be a short-lived signed JWT."""
    with open(settings.APPLE_PRIVATE_KEY_PATH, "r") as f:
        private_key = f.read()
    now = int(time.time())
    return jwt.encode(
        {
            "iss": settings.APPLE_TEAM_ID,
            "iat": now,
            "exp": now + 86400 * 180,
            "aud": "https://appleid.apple.com",
            "sub": settings.APPLE_CLIENT_ID,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": settings.APPLE_KEY_ID},
    )


oauth.register(
    name="apple",
    client_id=settings.APPLE_CLIENT_ID,
    server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email name", "response_mode": "form_post"},
)


def get_or_create_user(
    db: Session, provider: str, provider_id: str, email: str
) -> User:
    """Link providers by email: one account per email across all providers."""
    identity = (
        db.query(OAuthIdentity)
        .filter_by(provider=provider, provider_id=provider_id)
        .first()
    )
    if identity:
        return identity.user

    user = db.query(User).filter_by(email=email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.flush()

    db.add(OAuthIdentity(user=user, provider=provider, provider_id=provider_id))
    db.commit()
    db.refresh(user)
    return user


def create_token(user: User) -> str:
    return jwt.encode(
        {"sub": str(user.id), "email": user.email},
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user
