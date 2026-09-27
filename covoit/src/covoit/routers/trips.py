"""Trajets ponctuels, modèles récurrents, participation et tronçons."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import services
from ..db import get_session
from ..deps import get_current_user
from ..models import (
    Group,
    RecurringModel,
    RecurringParticipant,
    Trip,
    TripParticipation,
    TripSegment,
    TripSegmentOccupant,
    User,
)

router = APIRouter(tags=["trips"])


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


def _get_trip_or_404(session: Session, trip_id: int) -> Trip:
    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trajet introuvable")
    return trip


def _get_recurring_model_or_404(session: Session, model_id: int) -> RecurringModel:
    model = session.get(RecurringModel, model_id)
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modèle récurrent introuvable")
    return model


# --------------------------------------------------------------------------
# Schémas
# --------------------------------------------------------------------------


class RecurringModelRequest(BaseModel):
    name: str
    origin: str
    destination: str
    weekdays: list[int]
    time_of_day: str


class RecurringModelRead(BaseModel):
    id: int
    group_id: int
    name: str
    origin: str
    destination: str
    weekdays: list[int]
    time_of_day: str
    is_paused: bool


class RecurringParticipantRequest(BaseModel):
    user_id: int


class RecurringParticipantRead(BaseModel):
    id: int
    recurring_model_id: int
    user_id: int
    accepted: bool


class GenerateOccurrencesRequest(BaseModel):
    horizon_days: int = 60


class SegmentInput(BaseModel):
    sequence: int | None = None
    distance_km: float
    occupant_ids: list[int] = []
    is_detour: bool = False
    detour_for_id: int | None = None


class CreateTripRequest(BaseModel):
    date: date
    time_of_day: str
    origin: str
    destination: str
    driver_id: int
    vehicle_id: int | None = None
    passenger_ids: list[int] = []
    segments: list[SegmentInput]


class SegmentsReplaceRequest(BaseModel):
    segments: list[SegmentInput]


class TripStatusRequest(BaseModel):
    status: str


class ParticipationRequest(BaseModel):
    boarding_point: str | None = None


class ParticipationDecisionRequest(BaseModel):
    approve: bool


class TripRead(BaseModel):
    id: int
    group_id: int
    recurring_model_id: int | None
    date: date
    time_of_day: str
    origin: str
    destination: str
    driver_id: int
    vehicle_id: int | None
    status: str


class ParticipationRead(BaseModel):
    id: int
    trip_id: int
    user_id: int
    role: str
    status: str
    boarding_point: str | None


class SegmentRead(BaseModel):
    id: int
    sequence: int
    distance_km: float
    is_detour: bool
    detour_for_user_id: int | None
    occupant_ids: list[int]


def _serialize_model(model: RecurringModel) -> RecurringModelRead:
    return RecurringModelRead(
        id=model.id,
        group_id=model.group_id,
        name=model.name,
        origin=model.origin,
        destination=model.destination,
        weekdays=model.weekdays(),
        time_of_day=model.time_of_day,
        is_paused=model.is_paused,
    )


def _serialize_trip(trip: Trip) -> TripRead:
    return TripRead(
        id=trip.id,
        group_id=trip.group_id,
        recurring_model_id=trip.recurring_model_id,
        date=trip.date,
        time_of_day=trip.time_of_day,
        origin=trip.origin,
        destination=trip.destination,
        driver_id=trip.driver_id,
        vehicle_id=trip.vehicle_id,
        status=trip.status,
    )


def _serialize_participation(participation: TripParticipation) -> ParticipationRead:
    return ParticipationRead(
        id=participation.id,
        trip_id=participation.trip_id,
        user_id=participation.user_id,
        role=participation.role,
        status=participation.status,
        boarding_point=participation.boarding_point,
    )


def _serialize_segments(session: Session, trip_id: int) -> list[SegmentRead]:
    segments = session.exec(select(TripSegment).where(TripSegment.trip_id == trip_id)).all()
    segments.sort(key=lambda s: s.sequence)
    result = []
    for segment in segments:
        occupants = session.exec(
            select(TripSegmentOccupant).where(TripSegmentOccupant.segment_id == segment.id)
        ).all()
        result.append(
            SegmentRead(
                id=segment.id,
                sequence=segment.sequence,
                distance_km=segment.distance_km,
                is_detour=segment.is_detour,
                detour_for_user_id=segment.detour_for_user_id,
                occupant_ids=[o.user_id for o in occupants],
            )
        )
    return result


# --------------------------------------------------------------------------
# Modèles récurrents
# --------------------------------------------------------------------------


@router.post(
    "/groups/{group_id}/recurring-models",
    response_model=RecurringModelRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recurring_model(
    group_id: int,
    payload: RecurringModelRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringModelRead:
    group = _get_group_or_404(session, group_id)
    model = _handle(
        services.create_recurring_model,
        session,
        group,
        current_user,
        payload.name,
        payload.origin,
        payload.destination,
        payload.weekdays,
        payload.time_of_day,
    )
    return _serialize_model(model)


@router.get("/groups/{group_id}/recurring-models", response_model=list[RecurringModelRead])
def list_recurring_models(
    group_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[RecurringModelRead]:
    _get_group_or_404(session, group_id)
    models = session.exec(select(RecurringModel).where(RecurringModel.group_id == group_id)).all()
    return [_serialize_model(m) for m in models]


@router.post("/recurring-models/{model_id}/pause", response_model=RecurringModelRead)
def pause_recurring_model(
    model_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringModelRead:
    model = _get_recurring_model_or_404(session, model_id)
    model = _handle(services.pause_recurring_model, session, model, current_user)
    return _serialize_model(model)


@router.post("/recurring-models/{model_id}/resume", response_model=RecurringModelRead)
def resume_recurring_model(
    model_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringModelRead:
    model = _get_recurring_model_or_404(session, model_id)
    model = _handle(services.resume_recurring_model, session, model, current_user)
    return _serialize_model(model)


@router.delete("/recurring-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring_model(
    model_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    model = _get_recurring_model_or_404(session, model_id)
    _handle(services.delete_recurring_model, session, model, current_user)


@router.post(
    "/recurring-models/{model_id}/participants",
    response_model=RecurringParticipantRead,
    status_code=status.HTTP_201_CREATED,
)
def add_recurring_participant(
    model_id: int,
    payload: RecurringParticipantRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringParticipantRead:
    model = _get_recurring_model_or_404(session, model_id)
    participant = _handle(services.add_recurring_participant, session, model, current_user, payload.user_id)
    return RecurringParticipantRead(
        id=participant.id,
        recurring_model_id=participant.recurring_model_id,
        user_id=participant.user_id,
        accepted=participant.accepted,
    )


@router.post(
    "/recurring-models/{model_id}/participants/{participant_id}/accept",
    response_model=RecurringParticipantRead,
)
def accept_recurring_participation(
    model_id: int,
    participant_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> RecurringParticipantRead:
    participant = session.get(RecurringParticipant, participant_id)
    if not participant or participant.recurring_model_id != model_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Participation récurrente introuvable")
    participant = _handle(services.accept_recurring_participation, session, participant, current_user)
    return RecurringParticipantRead(
        id=participant.id,
        recurring_model_id=participant.recurring_model_id,
        user_id=participant.user_id,
        accepted=participant.accepted,
    )


class MyRecurringParticipationRead(BaseModel):
    id: int
    recurring_model_id: int
    group_id: int
    model_name: str


@router.get("/users/me/recurring-participations", response_model=list[MyRecurringParticipationRead])
def list_my_recurring_participations(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[MyRecurringParticipationRead]:
    participations = services.list_my_recurring_participations(session, current_user.id)
    result = []
    for participation in participations:
        model = session.get(RecurringModel, participation.recurring_model_id)
        result.append(
            MyRecurringParticipationRead(
                id=participation.id,
                recurring_model_id=participation.recurring_model_id,
                group_id=model.group_id if model else 0,
                model_name=model.name if model else "",
            )
        )
    return result


@router.post("/recurring-models/{model_id}/generate-occurrences", response_model=list[TripRead])
def generate_occurrences(
    model_id: int,
    payload: GenerateOccurrencesRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[TripRead]:
    model = _get_recurring_model_or_404(session, model_id)
    trips = _handle(services.generate_occurrences, session, model, current_user, payload.horizon_days)
    return [_serialize_trip(t) for t in trips]


# --------------------------------------------------------------------------
# Trajets ponctuels
# --------------------------------------------------------------------------


@router.post("/groups/{group_id}/trips", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(
    group_id: int,
    payload: CreateTripRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TripRead:
    group = _get_group_or_404(session, group_id)
    segments = [segment.model_dump() for segment in payload.segments]
    trip = _handle(
        services.create_trip,
        session,
        group,
        current_user,
        payload.date,
        payload.time_of_day,
        payload.origin,
        payload.destination,
        payload.driver_id,
        payload.vehicle_id,
        payload.passenger_ids,
        segments,
    )
    return _serialize_trip(trip)


@router.get("/groups/{group_id}/trips", response_model=list[TripRead])
def list_trips(
    group_id: int,
    year: int | None = None,
    month: int | None = None,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[TripRead]:
    _get_group_or_404(session, group_id)
    trips = session.exec(select(Trip).where(Trip.group_id == group_id)).all()
    if year is not None:
        trips = [t for t in trips if t.date.year == year]
    if month is not None:
        trips = [t for t in trips if t.date.month == month]
    return [_serialize_trip(t) for t in trips]


@router.get("/trips/{trip_id}", response_model=TripRead)
def read_trip(
    trip_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> TripRead:
    return _serialize_trip(_get_trip_or_404(session, trip_id))


@router.get("/trips/{trip_id}/segments", response_model=list[SegmentRead])
def read_trip_segments(
    trip_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[SegmentRead]:
    _get_trip_or_404(session, trip_id)
    return _serialize_segments(session, trip_id)


@router.get("/trips/{trip_id}/participations", response_model=list[ParticipationRead])
def list_trip_participations(
    trip_id: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[ParticipationRead]:
    _get_trip_or_404(session, trip_id)
    participations = session.exec(
        select(TripParticipation).where(TripParticipation.trip_id == trip_id)
    ).all()
    return [_serialize_participation(p) for p in participations]


@router.put("/trips/{trip_id}/segments", response_model=list[SegmentRead])
def replace_trip_segments(
    trip_id: int,
    payload: SegmentsReplaceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[SegmentRead]:
    trip = _get_trip_or_404(session, trip_id)
    segments = [segment.model_dump() for segment in payload.segments]
    _handle(services.set_trip_segments, session, trip, current_user, segments)
    return _serialize_segments(session, trip_id)


@router.post("/trips/{trip_id}/status", response_model=TripRead)
def set_trip_status(
    trip_id: int,
    payload: TripStatusRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TripRead:
    trip = _get_trip_or_404(session, trip_id)
    trip = _handle(services.set_trip_status, session, trip, current_user, payload.status)
    return _serialize_trip(trip)


@router.post(
    "/trips/{trip_id}/participation-requests",
    response_model=ParticipationRead,
    status_code=status.HTTP_201_CREATED,
)
def request_seat(
    trip_id: int,
    payload: ParticipationRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ParticipationRead:
    trip = _get_trip_or_404(session, trip_id)
    participation = _handle(services.request_seat, session, trip, current_user, payload.boarding_point)
    return _serialize_participation(participation)


@router.post(
    "/trips/{trip_id}/participation-requests/{participation_id}/decision",
    response_model=ParticipationRead,
)
def decide_participation(
    trip_id: int,
    participation_id: int,
    payload: ParticipationDecisionRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ParticipationRead:
    trip = _get_trip_or_404(session, trip_id)
    participation = session.get(TripParticipation, participation_id)
    if not participation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demande introuvable")
    participation = _handle(
        services.decide_participation, session, trip, current_user, participation, payload.approve
    )
    return _serialize_participation(participation)
