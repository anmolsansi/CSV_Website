from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import (
    SUPPORTED_PROVIDERS,
    _apple_client_secret,
    create_token,
    get_current_user,
    get_or_create_user,
    oauth,
)
from ..config import settings
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _client(provider: str):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(404, "Unsupported provider")
    return getattr(oauth, provider)


class DevLoginRequest(BaseModel):
    email: str = "test@jobgrid.dev"


@router.post("/dev-login")
def dev_login(payload: DevLoginRequest, db: Session = Depends(get_db)):
    """Test-only endpoint: creates or retrieves a user and returns a session cookie.
    Only available when TEST_AUTH=true."""
    if not settings.TEST_AUTH:
        raise HTTPException(404, "Not found")
    user = db.query(User).filter_by(email=payload.email).first()
    if not user:
        user = User(email=payload.email)
        db.add(user)
        db.commit()
        db.refresh(user)
    jwt_token = create_token(user)
    from fastapi.responses import JSONResponse
    resp = JSONResponse({"id": user.id, "email": user.email})
    resp.set_cookie(
        "session_token",
        jwt_token,
        max_age=60 * 60 * 24 * 7,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return resp


def _cookie_options() -> dict:
    is_production = settings.ENVIRONMENT == "production"
    return {
        "httponly": True,
        "secure": is_production,
        "samesite": "none" if is_production else "lax",
    }


@router.get("/login/{provider}")
async def login(provider: str, request: Request):
    client = _client(provider)
    redirect_uri = f"{settings.OAUTH_REDIRECT_BASE}/auth/callback/{provider}"
    kwargs = {}
    if provider == "apple":
        # Apple needs a freshly signed client secret per request.
        kwargs["client_secret"] = _apple_client_secret()
    return await client.authorize_redirect(request, redirect_uri, **kwargs)


# Apple posts the callback (response_mode=form_post), so accept GET and POST.
@router.api_route("/callback/{provider}", methods=["GET", "POST"])
async def callback(provider: str, request: Request, db: Session = Depends(get_db)):
    client = _client(provider)
    try:
        if provider == "apple":
            token = await client.authorize_access_token(
                request, client_secret=_apple_client_secret()
            )
        else:
            token = await client.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=oauth")

    info = token.get("userinfo") or {}
    email = info.get("email")
    provider_id = info.get("sub")
    if not email or not provider_id:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=no_email")

    user = get_or_create_user(db, provider, provider_id, email)

    jwt_token = create_token(user)
    resp = RedirectResponse(settings.FRONTEND_URL)
    resp.set_cookie(
        "session_token",
        jwt_token,
        max_age=60 * 60 * 24 * 7,
        **_cookie_options(),
    )
    return resp


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}


@router.post("/logout")
def logout():
    resp = RedirectResponse(settings.FRONTEND_URL, status_code=303)
    resp.delete_cookie("session_token", **_cookie_options())
    return resp
