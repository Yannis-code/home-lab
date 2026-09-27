"""Dépendances FastAPI: session base de données et utilisateur courant."""

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from .clock import utcnow
from .db import get_session
from .models import SessionToken, User
from .security import hash_token


def get_current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    token = authorization.split(" ", 1)[1].strip()
    token_hash = hash_token(token)
    record = session.exec(
        select(SessionToken).where(SessionToken.token_hash == token_hash)
    ).first()
    if not record or record.expires_at < utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée")
    user = session.get(User, record.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte inactif")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'administrateur")
    return user
