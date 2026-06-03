from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user, oauth
from ..config import settings
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login/google")
async def login_google(request: Request):
    redirect_uri = f"{settings.OAUTH_REDIRECT_BASE}/auth/callback/google"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback/google")
async def callback_google(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=oauth")
    info = token.get("userinfo")
    email = info["email"]
    provider_id = info["sub"]

    user = (
        db.query(User)
        .filter_by(oauth_provider="google", provider_id=provider_id)
        .first()
    )
    if not user:
        user = User(email=email, oauth_provider="google", provider_id=provider_id)
        db.add(user)
        db.commit()
        db.refresh(user)

    jwt_token = create_token(user)
    resp = RedirectResponse(settings.FRONTEND_URL)
    resp.set_cookie(
        "session_token", jwt_token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7
    )
    return resp


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}


@router.post("/logout")
def logout():
    resp = RedirectResponse(settings.FRONTEND_URL, status_code=303)
    resp.delete_cookie("session_token")
    return resp
