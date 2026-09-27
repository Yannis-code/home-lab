"""Authentification locale: connexion, changement de mot de passe, déconnexion."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..deps import get_current_user
from ..models import SessionToken, User
from ..security import (
    generate_session_token,
    hash_password,
    hash_token,
    session_expiry,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides")

    token = generate_session_token()
    record = SessionToken(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=session_expiry(settings.session_ttl_hours),
    )
    session.add(record)
    session.commit()
    return TokenResponse(token=token, must_change_password=user.must_change_password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    # Invalide tous les jetons de l'utilisateur courant (déconnexion simple, sans multi-session ciblée).
    tokens = session.exec(select(SessionToken).where(SessionToken.user_id == current_user.id)).all()
    for token in tokens:
        session.delete(token)
    session.commit()


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Mot de passe actuel incorrect")
    if len(payload.new_password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le nouveau mot de passe est trop court")
    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    session.add(current_user)
    session.commit()
