"""Gestion des comptes utilisateurs par l'administrateur global."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from .. import services
from ..db import get_session
from ..deps import get_current_user, require_admin
from ..models import Group, User
from ..security import generate_temporary_password, hash_password

router = APIRouter(tags=["users"])


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr


class UserRead(BaseModel):
    id: int
    name: str
    is_admin: bool
    is_active: bool


class UserCreatedResponse(BaseModel):
    user: UserRead
    temporary_password: str


class MeResponse(BaseModel):
    id: int
    name: str
    email: str
    is_admin: bool
    must_change_password: bool


class TemporaryPasswordResponse(BaseModel):
    temporary_password: str


class InvitationRead(BaseModel):
    id: int
    group_id: int
    group_name: str
    invited_by_id: int


def _serialize(user: User) -> UserRead:
    return UserRead(id=user.id, name=user.name, is_admin=user.is_admin, is_active=user.is_active)


@router.post("/admin/users", response_model=UserCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_admin),
) -> UserCreatedResponse:
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail")
    temporary_password = generate_temporary_password()
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(temporary_password),
        must_change_password=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserCreatedResponse(user=_serialize(user), temporary_password=temporary_password)


@router.get("/admin/users", response_model=list[UserRead])
def list_all_users(
    session: Session = Depends(get_session),
    _admin: User = Depends(require_admin),
) -> list[UserRead]:
    # Contrairement à GET /users (recherche pour inviter, actifs uniquement),
    # l'administrateur doit voir aussi les comptes désactivés pour les gérer.
    users = session.exec(select(User)).all()
    return [_serialize(u) for u in users]


@router.post("/admin/users/{user_id}/reset-password", response_model=TemporaryPasswordResponse)
def reset_password(
    user_id: int,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_admin),
) -> TemporaryPasswordResponse:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
    temporary_password = generate_temporary_password()
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    session.add(user)
    session.commit()
    return TemporaryPasswordResponse(temporary_password=temporary_password)


@router.patch("/admin/users/{user_id}/deactivate", response_model=UserRead)
def deactivate_user(
    user_id: int,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_admin),
) -> UserRead:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
    user.is_active = False
    session.add(user)
    session.commit()
    session.refresh(user)
    return _serialize(user)


@router.get("/users/me", response_model=MeResponse)
def read_me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        is_admin=current_user.is_admin,
        must_change_password=current_user.must_change_password,
    )


@router.get("/users/me/invitations", response_model=list[InvitationRead])
def list_my_invitations(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[InvitationRead]:
    memberships = services.list_my_invitations(session, current_user.id)
    result = []
    for membership in memberships:
        group = session.get(Group, membership.group_id)
        result.append(
            InvitationRead(
                id=membership.id,
                group_id=membership.group_id,
                group_name=group.name if group else "",
                invited_by_id=membership.invited_by_id,
            )
        )
    return result


@router.get("/users", response_model=list[UserRead])
def search_users(
    query: str = "",
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[UserRead]:
    # Seul le nom est exposé, utilisé pour choisir un compte existant à inviter.
    return [_serialize(u) for u in services.search_users(session, query)]


@router.get("/users/{user_id}", response_model=UserRead)
def read_user_profile(
    user_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> UserRead:
    # Seul le nom de profil est exposé: l'adresse e-mail n'est pas visible des autres membres.
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
    return _serialize(user)
