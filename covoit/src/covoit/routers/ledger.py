"""Bilan mensuel: consultation, validation, remboursements, corrections, export."""

import csv
import io
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import services
from ..db import get_session
from ..deps import get_current_user
from ..models import Group, Reimbursement, TripSegment, User

router = APIRouter(tags=["ledger"])


def _handle(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except services.ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except services.ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


def _get_group_or_404(session: Session, group_id: int) -> Group:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Groupe introuvable")
    return group


class LedgerIssueRead(BaseModel):
    code: str
    message: str


class TransferRead(BaseModel):
    debtor_id: int
    creditor_id: int
    amount: Decimal


class LedgerRead(BaseModel):
    group_id: int
    year: int
    month: int
    status: str
    balances: dict[str, Decimal]
    transfers: list[TransferRead]
    concerned_user_ids: list[int]
    issues: list[LedgerIssueRead]


class ValidateLedgerRequest(BaseModel):
    year: int
    month: int


class DeclareReimbursementRequest(BaseModel):
    payee_id: int
    amount: float
    year: int
    month: int


class ReimbursementRead(BaseModel):
    id: int
    group_id: int
    year: int
    month: int
    payer_id: int
    payee_id: int
    amount: float
    status: str


class CorrectionRequest(BaseModel):
    year: int
    month: int
    segment_id: int
    new_distance_km: float
    reason: str


def _serialize_ledger(group_id: int, year: int, month: int, ledger_status: str, computation) -> LedgerRead:
    return LedgerRead(
        group_id=group_id,
        year=year,
        month=month,
        status=ledger_status,
        balances={str(k): v for k, v in computation.balances.items()},
        transfers=[
            TransferRead(debtor_id=debtor, creditor_id=creditor, amount=amount)
            for debtor, creditor, amount in computation.transfers
        ],
        concerned_user_ids=sorted(computation.concerned_user_ids),
        issues=[LedgerIssueRead(code=i.code, message=i.message) for i in computation.issues],
    )


def _serialize_reimbursement(r: Reimbursement) -> ReimbursementRead:
    return ReimbursementRead(
        id=r.id,
        group_id=r.group_id,
        year=r.year,
        month=r.month,
        payer_id=r.payer_id,
        payee_id=r.payee_id,
        amount=r.amount,
        status=r.status,
    )


@router.get("/groups/{group_id}/ledger", response_model=LedgerRead)
def read_ledger(
    group_id: int,
    year: int,
    month: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> LedgerRead:
    _get_group_or_404(session, group_id)
    computation = services.compute_group_month(session, group_id, year, month)
    ledger = services.get_or_create_ledger(session, group_id, year, month)
    return _serialize_ledger(group_id, year, month, ledger.status, computation)


@router.post("/groups/{group_id}/ledger/validate", response_model=LedgerRead)
def validate_ledger(
    group_id: int,
    payload: ValidateLedgerRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> LedgerRead:
    group = _get_group_or_404(session, group_id)
    ledger, computation = _handle(
        services.validate_ledger, session, group, current_user, payload.year, payload.month
    )
    return _serialize_ledger(group_id, payload.year, payload.month, ledger.status, computation)


@router.post(
    "/groups/{group_id}/reimbursements",
    response_model=ReimbursementRead,
    status_code=status.HTTP_201_CREATED,
)
def declare_reimbursement(
    group_id: int,
    payload: DeclareReimbursementRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReimbursementRead:
    group = _get_group_or_404(session, group_id)
    reimbursement = _handle(
        services.declare_reimbursement,
        session,
        group,
        current_user,
        payload.payee_id,
        payload.amount,
        payload.year,
        payload.month,
    )
    return _serialize_reimbursement(reimbursement)


@router.get("/groups/{group_id}/reimbursements", response_model=list[ReimbursementRead])
def list_reimbursements(
    group_id: int,
    year: int,
    month: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[ReimbursementRead]:
    _get_group_or_404(session, group_id)
    reimbursements = session.exec(
        select(Reimbursement).where(
            Reimbursement.group_id == group_id,
            Reimbursement.year == year,
            Reimbursement.month == month,
        )
    ).all()
    return [_serialize_reimbursement(r) for r in reimbursements]


@router.post("/reimbursements/{reimbursement_id}/confirm", response_model=ReimbursementRead)
def confirm_reimbursement(
    reimbursement_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReimbursementRead:
    reimbursement = session.get(Reimbursement, reimbursement_id)
    if not reimbursement:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Remboursement introuvable")
    reimbursement = _handle(services.confirm_reimbursement, session, reimbursement, current_user)
    return _serialize_reimbursement(reimbursement)


@router.post("/groups/{group_id}/ledger/corrections", status_code=status.HTTP_201_CREATED)
def correct_ledger(
    group_id: int,
    payload: CorrectionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    _get_group_or_404(session, group_id)
    ledger = services.get_or_create_ledger(session, group_id, payload.year, payload.month)
    segment = session.get(TripSegment, payload.segment_id)
    if not segment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tronçon introuvable")
    correction, adjustments = _handle(
        services.correct_segment_distance,
        session,
        ledger,
        current_user,
        segment,
        payload.new_distance_km,
        payload.reason,
    )
    return {
        "correction_id": correction.id,
        "adjustments": [
            {"user_id": a.user_id, "year": a.year, "month": a.month, "amount": a.amount}
            for a in adjustments
        ],
    }


@router.get("/groups/{group_id}/ledger/export")
def export_ledger(
    group_id: int,
    year: int,
    month: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _get_group_or_404(session, group_id)
    computation = services.compute_group_month(session, group_id, year, month)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["type", "user_id_or_debtor", "creditor_id", "amount"])
    for user_id, amount in computation.balances.items():
        writer.writerow(["balance", user_id, "", amount])
    for debtor, creditor, amount in computation.transfers:
        writer.writerow(["transfer", debtor, creditor, amount])
    buffer.seek(0)
    filename = f"bilan-{group_id}-{year:04d}-{month:02d}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
