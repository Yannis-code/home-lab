"""Groupes de covoiturage: création, adhésion, gestion, conducteur par défaut."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import services
from ..db import get_session
from ..deps import get_current_user
from ..models import Group, GroupMembership, User

router = APIRouter(prefix="/groups", tags=["groups"])


class CreateGroupRequest(BaseModel):
    name: str


class GroupRead(BaseModel):
    id: int
    name: str
    manager_id: int
    default_driver_id: int | None
    is_archived: bool


class MembershipRead(BaseModel):
    id: int
    group_id: int
    user_id: int
    status: str


class InviteRequest(BaseModel):
    user_id: int


class TransferManagementRequest(BaseModel):
    new_manager_id: int


class SetDefaultDriverRequest(BaseModel):
    user_id: int


def _serialize_group(group: Group) -> GroupRead:
    return GroupRead(
        id=group.id,
        name=group.name,
        manager_id=group.manager_id,
        default_driver_id=group.default_driver_id,
        is_archived=group.is_archived,
    )


def _serialize_membership(membership: GroupMembership) -> MembershipRead:
    return MembershipRead(
        id=membership.id,
        group_id=membership.group_id,
        user_id=membership.user_id,
        status=membership.status,
    )


def _get_group_or_404(session: Session, group_id: int) -> Group:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Groupe introuvable")
    return group


def _handle(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except services.ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except services.ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: CreateGroupRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GroupRead:
    group = _handle(services.create_group, session, current_user, payload.name)
    return _serialize_group(group)


@router.get("", response_model=list[GroupRead])
def list_my_groups(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[GroupRead]:
    groups = services.list_my_groups(session, current_user.id)
    return [_serialize_group(g) for g in groups]


@router.get("/{group_id}", response_model=GroupRead)
def read_group(
    group_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> GroupRead:
    return _serialize_group(_get_group_or_404(session, group_id))


@router.get("/{group_id}/members", response_model=list[MembershipRead])
def list_members(
    group_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[MembershipRead]:
    _get_group_or_404(session, group_id)
    memberships = session.exec(
        select(GroupMembership).where(GroupMembership.group_id == group_id)
    ).all()
    return [_serialize_membership(m) for m in memberships]


@router.post("/{group_id}/invitations", response_model=MembershipRead, status_code=status.HTTP_201_CREATED)
def invite_member(
    group_id: int,
    payload: InviteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MembershipRead:
    group = _get_group_or_404(session, group_id)
    invitee = session.get(User, payload.user_id)
    if not invitee:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
    membership = _handle(services.invite_member, session, group, current_user, invitee)
    return _serialize_membership(membership)


@router.post("/{group_id}/invitations/{membership_id}/accept", response_model=MembershipRead)
def accept_invitation(
    group_id: int,
    membership_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MembershipRead:
    membership = _get_membership_or_404(session, group_id, membership_id)
    membership = _handle(services.accept_invitation, session, membership, current_user)
    return _serialize_membership(membership)


@router.post("/{group_id}/invitations/{membership_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_invitation(
    group_id: int,
    membership_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    membership = _get_membership_or_404(session, group_id, membership_id)
    _handle(services.decline_invitation, session, membership, current_user)


@router.post("/{group_id}/leave", response_model=MembershipRead)
def leave_group(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> MembershipRead:
    group = _get_group_or_404(session, group_id)
    membership = _handle(services.leave_group, session, group, current_user)
    return _serialize_membership(membership)


@router.post("/{group_id}/transfer-management", response_model=GroupRead)
def transfer_management(
    group_id: int,
    payload: TransferManagementRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GroupRead:
    group = _get_group_or_404(session, group_id)
    group = _handle(services.transfer_management, session, group, current_user, payload.new_manager_id)
    return _serialize_group(group)


@router.post("/{group_id}/default-driver", response_model=GroupRead)
def set_default_driver(
    group_id: int,
    payload: SetDefaultDriverRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GroupRead:
    group = _get_group_or_404(session, group_id)
    group = _handle(services.set_default_driver, session, group, current_user, payload.user_id)
    return _serialize_group(group)


@router.post("/{group_id}/archive", response_model=GroupRead)
def archive_group(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GroupRead:
    group = _get_group_or_404(session, group_id)
    group = _handle(services.archive_group, session, group, current_user)
    return _serialize_group(group)


def _get_membership_or_404(session: Session, group_id: int, membership_id: int) -> GroupMembership:
    membership = session.get(GroupMembership, membership_id)
    if not membership or membership.group_id != group_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation introuvable")
    return membership
