"""Couche de service: règles métier reliant les modèles SQLModel à la logique
pure de ``billing.py`` et ``recurrence.py``.

Les fonctions lèvent des exceptions de domaine (``NotFoundError``,
``ForbiddenError``, ``ConflictError``) que les routers traduisent en réponses
HTTP appropriées, ce qui garde cette couche indépendante de FastAPI.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from . import billing
from .clock import utcnow
from .models import (
    Group,
    GroupMembership,
    LedgerAdjustment,
    LedgerCorrection,
    LedgerStatus,
    LedgerValidation,
    MembershipStatus,
    MonthlyEnergyPrice,
    MonthlyLedger,
    ParticipationRole,
    ParticipationStatus,
    RecurringModel,
    RecurringParticipant,
    Reimbursement,
    ReimbursementStatus,
    Trip,
    TripParticipation,
    TripSegment,
    TripSegmentOccupant,
    TripStatus,
    User,
    Vehicle,
    VehicleEnergy,
    VehicleGroupShare,
)
from .recurrence import generate_dates


class ServiceError(Exception):
    """Base des erreurs de règles métier."""


class NotFoundError(ServiceError):
    pass


class ForbiddenError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass


# --------------------------------------------------------------------------
# Adhésion aux groupes
# --------------------------------------------------------------------------


def get_membership(session: Session, group_id: int, user_id: int) -> Optional[GroupMembership]:
    return session.exec(
        select(GroupMembership).where(
            GroupMembership.group_id == group_id, GroupMembership.user_id == user_id
        )
    ).first()


def list_my_groups(session: Session, user_id: int) -> list[Group]:
    """Groupes dont l'utilisateur est membre actif."""
    memberships = session.exec(
        select(GroupMembership).where(
            GroupMembership.user_id == user_id,
            GroupMembership.status == MembershipStatus.active.value,
        )
    ).all()
    groups = [session.get(Group, m.group_id) for m in memberships]
    return [g for g in groups if g is not None]


def list_my_invitations(session: Session, user_id: int) -> list[GroupMembership]:
    """Invitations en attente d'acceptation pour l'utilisateur."""
    return session.exec(
        select(GroupMembership).where(
            GroupMembership.user_id == user_id,
            GroupMembership.status == MembershipStatus.pending.value,
        )
    ).all()


def search_users(session: Session, query: str, limit: int = 20) -> list[User]:
    """Recherche de comptes par nom, pour sélectionner un invité existant."""
    statement = select(User).where(User.is_active == True)  # noqa: E712
    if query:
        pattern = f"%{query.lower()}%"
        statement = statement.where(func.lower(User.name).like(pattern))
    return session.exec(statement.limit(limit)).all()


def list_my_recurring_participations(session: Session, user_id: int) -> list[RecurringParticipant]:
    """Participations récurrentes proposées à l'utilisateur mais pas encore acceptées."""
    return session.exec(
        select(RecurringParticipant).where(
            RecurringParticipant.user_id == user_id,
            RecurringParticipant.accepted == False,  # noqa: E712
        )
    ).all()


def list_group_vehicles(session: Session, group_id: int, driver_id: int) -> list[Vehicle]:
    """Véhicules accessibles à ``driver_id`` dans ce groupe (siens + partagés)."""
    owned = session.exec(select(Vehicle).where(Vehicle.owner_id == driver_id)).all()
    shared_ids = {
        share.vehicle_id
        for share in session.exec(
            select(VehicleGroupShare).where(VehicleGroupShare.group_id == group_id)
        ).all()
    }
    shared = [session.get(Vehicle, vid) for vid in shared_ids if vid not in {v.id for v in owned}]
    return owned + [v for v in shared if v is not None]


def require_active_member(session: Session, group_id: int, user_id: int) -> GroupMembership:
    membership = get_membership(session, group_id, user_id)
    if not membership or membership.status != MembershipStatus.active.value:
        raise ForbiddenError("Réservé aux membres actifs du groupe")
    return membership


def create_group(session: Session, creator: User, name: str) -> Group:
    if not name or not name.strip():
        raise ConflictError("Le nom du groupe est obligatoire")
    group = Group(name=name, manager_id=creator.id, default_driver_id=creator.id)
    session.add(group)
    session.commit()
    session.refresh(group)
    membership = GroupMembership(
        group_id=group.id,
        user_id=creator.id,
        invited_by_id=creator.id,
        status=MembershipStatus.active.value,
        joined_at=utcnow(),
    )
    session.add(membership)
    session.commit()
    return group


def invite_member(session: Session, group: Group, inviter: User, invitee: User) -> GroupMembership:
    if group.is_archived:
        raise ConflictError("Le groupe est archivé")
    if inviter.id != group.manager_id:
        raise ForbiddenError("Seul le gestionnaire invite des membres")
    existing = get_membership(session, group.id, invitee.id)
    if existing and existing.status in (MembershipStatus.pending.value, MembershipStatus.active.value):
        raise ConflictError("Cette personne est déjà membre ou invitée")
    if existing:
        session.delete(existing)
        session.commit()
    membership = GroupMembership(group_id=group.id, user_id=invitee.id, invited_by_id=inviter.id)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


def accept_invitation(session: Session, membership: GroupMembership, user: User) -> GroupMembership:
    if membership.user_id != user.id:
        raise ForbiddenError("Seule la personne invitée peut accepter l'invitation")
    if membership.status != MembershipStatus.pending.value:
        raise ConflictError("Cette invitation a déjà été traitée")
    membership.status = MembershipStatus.active.value
    membership.joined_at = utcnow()
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return membership


def decline_invitation(session: Session, membership: GroupMembership, user: User) -> None:
    if membership.user_id != user.id:
        raise ForbiddenError("Seule la personne invitée peut refuser l'invitation")
    if membership.status != MembershipStatus.pending.value:
        raise ConflictError("Cette invitation a déjà été traitée")
    session.delete(membership)
    session.commit()


def leave_group(session: Session, group: Group, user: User) -> GroupMembership:
    membership = require_active_member(session, group.id, user.id)
    if group.manager_id == user.id:
        raise ConflictError("Le gestionnaire doit transférer la gestion avant de quitter le groupe")
    membership.status = MembershipStatus.left.value
    membership.left_at = utcnow()
    session.add(membership)
    if group.default_driver_id == user.id:
        group.default_driver_id = None
        session.add(group)
    session.commit()
    session.refresh(membership)
    return membership


def transfer_management(session: Session, group: Group, actor: User, new_manager_id: int) -> Group:
    if actor.id != group.manager_id:
        raise ForbiddenError("Seul le gestionnaire peut transférer la gestion")
    require_active_member(session, group.id, new_manager_id)
    group.manager_id = new_manager_id
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def set_default_driver(session: Session, group: Group, actor: User, driver_user_id: int) -> Group:
    require_active_member(session, group.id, actor.id)
    require_active_member(session, group.id, driver_user_id)
    group.default_driver_id = driver_user_id
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def archive_group(session: Session, group: Group, actor: User) -> Group:
    if actor.id != group.manager_id:
        raise ForbiddenError("Seul le gestionnaire peut archiver le groupe")
    group.is_archived = True
    group.archived_at = utcnow()
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


# --------------------------------------------------------------------------
# Véhicules
# --------------------------------------------------------------------------


def add_vehicle(
    session: Session,
    owner: User,
    brand: str,
    model: str,
    seats: int,
    energies: list[tuple[str, float]],
) -> Vehicle:
    if seats < 1:
        raise ConflictError("Le nombre de places doit être positif (conducteur inclus)")
    if not energies:
        raise ConflictError("Un véhicule doit avoir au moins une source d'énergie")
    vehicle = Vehicle(owner_id=owner.id, brand=brand, model=model, seats=seats)
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)
    for energy_type, consumption in energies:
        if consumption <= 0:
            raise ConflictError("La consommation moyenne doit être positive")
        session.add(
            VehicleEnergy(
                vehicle_id=vehicle.id,
                energy_type=energy_type,
                consumption_per_100km=consumption,
            )
        )
    session.commit()
    return vehicle


def share_vehicle_with_group(session: Session, vehicle: Vehicle, owner: User, group: Group) -> VehicleGroupShare:
    if vehicle.owner_id != owner.id:
        raise ForbiddenError("Seul le propriétaire peut partager le véhicule")
    require_active_member(session, group.id, owner.id)
    existing = session.exec(
        select(VehicleGroupShare).where(
            VehicleGroupShare.vehicle_id == vehicle.id, VehicleGroupShare.group_id == group.id
        )
    ).first()
    if existing:
        return existing
    share = VehicleGroupShare(vehicle_id=vehicle.id, group_id=group.id)
    session.add(share)
    session.commit()
    session.refresh(share)
    return share


def vehicle_accessible_to(session: Session, vehicle_id: int, driver_id: int, group_id: int) -> bool:
    vehicle = session.get(Vehicle, vehicle_id)
    if not vehicle:
        return False
    if vehicle.owner_id == driver_id:
        return True
    share = session.exec(
        select(VehicleGroupShare).where(
            VehicleGroupShare.vehicle_id == vehicle_id, VehicleGroupShare.group_id == group_id
        )
    ).first()
    return share is not None


# --------------------------------------------------------------------------
# Modèles récurrents
# --------------------------------------------------------------------------


def create_recurring_model(
    session: Session,
    group: Group,
    actor: User,
    name: str,
    origin: str,
    destination: str,
    weekdays: list[int],
    time_of_day: str,
) -> RecurringModel:
    require_active_member(session, group.id, actor.id)
    if group.is_archived:
        raise ConflictError("Le groupe est archivé")
    if not weekdays:
        raise ConflictError("Au moins un jour de semaine est requis")
    model = RecurringModel(
        group_id=group.id,
        name=name,
        origin=origin,
        destination=destination,
        weekdays_csv=",".join(str(day) for day in sorted(set(weekdays))),
        time_of_day=time_of_day,
        created_by_id=actor.id,
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def pause_recurring_model(session: Session, model: RecurringModel, actor: User) -> RecurringModel:
    require_active_member(session, model.group_id, actor.id)
    model.is_paused = True
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def resume_recurring_model(session: Session, model: RecurringModel, actor: User) -> RecurringModel:
    require_active_member(session, model.group_id, actor.id)
    model.is_paused = False
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def delete_recurring_model(session: Session, model: RecurringModel, actor: User) -> None:
    require_active_member(session, model.group_id, actor.id)
    today = utcnow().date()
    future_trips = session.exec(
        select(Trip).where(
            Trip.recurring_model_id == model.id,
            Trip.date >= today,
            Trip.status == TripStatus.planned.value,
        )
    ).all()
    for trip in future_trips:
        trip.status = TripStatus.cancelled.value
        session.add(trip)
    session.delete(model)
    session.commit()


def add_recurring_participant(
    session: Session, model: RecurringModel, actor: User, user_id: int
) -> RecurringParticipant:
    require_active_member(session, model.group_id, actor.id)
    require_active_member(session, model.group_id, user_id)
    existing = session.exec(
        select(RecurringParticipant).where(
            RecurringParticipant.recurring_model_id == model.id,
            RecurringParticipant.user_id == user_id,
        )
    ).first()
    if existing:
        return existing
    participant = RecurringParticipant(recurring_model_id=model.id, user_id=user_id)
    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant


def accept_recurring_participation(
    session: Session, participant: RecurringParticipant, user: User
) -> RecurringParticipant:
    if participant.user_id != user.id:
        raise ForbiddenError("Seule la personne concernée accepte sa présence récurrente")
    participant.accepted = True
    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant


def generate_occurrences(
    session: Session, model: RecurringModel, actor: User, horizon_days: int = 60
) -> list[Trip]:
    require_active_member(session, model.group_id, actor.id)
    if model.is_paused:
        return []
    group = session.get(Group, model.group_id)
    if not group.default_driver_id:
        raise ConflictError("Le groupe doit avoir un conducteur par défaut pour générer des occurrences")

    today = utcnow().date()
    horizon = today + timedelta(days=horizon_days)
    dates = generate_dates(model.weekdays(), today, horizon)

    existing_dates = {
        trip.date
        for trip in session.exec(
            select(Trip).where(Trip.recurring_model_id == model.id, Trip.date >= today)
        ).all()
    }
    accepted_participants = session.exec(
        select(RecurringParticipant).where(
            RecurringParticipant.recurring_model_id == model.id,
            RecurringParticipant.accepted == True,  # noqa: E712
        )
    ).all()

    created: list[Trip] = []
    for occurrence_date in dates:
        if occurrence_date in existing_dates:
            continue
        trip = Trip(
            group_id=model.group_id,
            recurring_model_id=model.id,
            date=occurrence_date,
            time_of_day=model.time_of_day,
            origin=model.origin,
            destination=model.destination,
            driver_id=group.default_driver_id,
            vehicle_id=None,
            status=TripStatus.planned.value,
            created_by_id=actor.id,
        )
        session.add(trip)
        session.flush()
        session.add(
            TripParticipation(
                trip_id=trip.id,
                user_id=trip.driver_id,
                role=ParticipationRole.driver.value,
                status=ParticipationStatus.accepted.value,
                decided_at=utcnow(),
                decided_by_id=actor.id,
            )
        )
        for participant in accepted_participants:
            if participant.user_id == trip.driver_id:
                continue
            session.add(
                TripParticipation(
                    trip_id=trip.id,
                    user_id=participant.user_id,
                    role=ParticipationRole.passenger.value,
                    status=ParticipationStatus.accepted.value,
                    decided_at=utcnow(),
                    decided_by_id=actor.id,
                )
            )
        created.append(trip)

    session.commit()
    for trip in created:
        session.refresh(trip)
    return created


# --------------------------------------------------------------------------
# Trajets ponctuels, participation et tronçons
# --------------------------------------------------------------------------


def _accepted_participant_ids(session: Session, trip_id: int) -> set[int]:
    rows = session.exec(
        select(TripParticipation).where(
            TripParticipation.trip_id == trip_id,
            TripParticipation.status == ParticipationStatus.accepted.value,
        )
    ).all()
    return {row.user_id for row in rows}


def _replace_segments(session: Session, trip: Trip, segments: list[dict]) -> None:
    if not segments:
        raise ConflictError("Un trajet doit comporter au moins un tronçon")
    accepted_ids = _accepted_participant_ids(session, trip.id)

    existing_segments = session.exec(select(TripSegment).where(TripSegment.trip_id == trip.id)).all()
    for segment in existing_segments:
        occupants = session.exec(
            select(TripSegmentOccupant).where(TripSegmentOccupant.segment_id == segment.id)
        ).all()
        for occupant in occupants:
            session.delete(occupant)
        session.delete(segment)
    session.flush()

    for index, raw in enumerate(segments):
        distance_km = raw["distance_km"]
        if distance_km <= 0:
            raise ConflictError("La distance d'un tronçon doit être positive")
        is_detour = bool(raw.get("is_detour", False))
        detour_for_id = raw.get("detour_for_id")
        occupant_ids = list(dict.fromkeys(raw.get("occupant_ids", [])))

        if is_detour:
            if not detour_for_id:
                raise ConflictError("Un tronçon de détour doit préciser le passager concerné")
            if detour_for_id not in accepted_ids:
                raise ConflictError("Le passager du détour doit être inscrit et accepté sur le trajet")
            if not occupant_ids:
                occupant_ids = [detour_for_id]
        else:
            if not occupant_ids:
                raise ConflictError("Un tronçon normal doit avoir au moins un occupant")
            for user_id in occupant_ids:
                if user_id not in accepted_ids:
                    raise ConflictError(
                        f"L'utilisateur {user_id} n'est pas un participant accepté du trajet"
                    )

        sequence = raw.get("sequence")
        if sequence is None:
            sequence = index
        segment = TripSegment(
            trip_id=trip.id,
            sequence=sequence,
            distance_km=distance_km,
            is_detour=is_detour,
            detour_for_user_id=detour_for_id,
        )
        session.add(segment)
        session.flush()
        for user_id in occupant_ids:
            session.add(TripSegmentOccupant(segment_id=segment.id, user_id=user_id))

    session.commit()


def create_trip(
    session: Session,
    group: Group,
    actor: User,
    trip_date: date,
    time_of_day: str,
    origin: str,
    destination: str,
    driver_id: int,
    vehicle_id: Optional[int],
    passenger_ids: list[int],
    segments: list[dict],
) -> Trip:
    require_active_member(session, group.id, actor.id)
    if group.is_archived:
        raise ConflictError("Le groupe est archivé")
    require_active_member(session, group.id, driver_id)

    unique_passenger_ids = [pid for pid in dict.fromkeys(passenger_ids) if pid != driver_id]
    for passenger_id in unique_passenger_ids:
        require_active_member(session, group.id, passenger_id)

    if vehicle_id is not None:
        if not vehicle_accessible_to(session, vehicle_id, driver_id, group.id):
            raise ConflictError("Ce véhicule n'est pas accessible à ce conducteur dans ce groupe")
        vehicle = session.get(Vehicle, vehicle_id)
        if 1 + len(unique_passenger_ids) > vehicle.seats:
            raise ConflictError("Le nombre de participants dépasse la capacité du véhicule")

    trip = Trip(
        group_id=group.id,
        date=trip_date,
        time_of_day=time_of_day,
        origin=origin,
        destination=destination,
        driver_id=driver_id,
        vehicle_id=vehicle_id,
        created_by_id=actor.id,
    )
    session.add(trip)
    session.flush()

    session.add(
        TripParticipation(
            trip_id=trip.id,
            user_id=driver_id,
            role=ParticipationRole.driver.value,
            status=ParticipationStatus.accepted.value,
            decided_at=utcnow(),
            decided_by_id=actor.id,
        )
    )
    for passenger_id in unique_passenger_ids:
        session.add(
            TripParticipation(
                trip_id=trip.id,
                user_id=passenger_id,
                role=ParticipationRole.passenger.value,
                status=ParticipationStatus.accepted.value,
                decided_at=utcnow(),
                decided_by_id=actor.id,
            )
        )
    session.commit()

    _replace_segments(session, trip, segments)
    session.refresh(trip)
    return trip


def set_trip_segments(session: Session, trip: Trip, actor: User, segments: list[dict]) -> Trip:
    require_active_member(session, trip.group_id, actor.id)
    _replace_segments(session, trip, segments)
    session.refresh(trip)
    return trip


def request_seat(
    session: Session, trip: Trip, user: User, boarding_point: Optional[str] = None
) -> TripParticipation:
    require_active_member(session, trip.group_id, user.id)
    existing = session.exec(
        select(TripParticipation).where(
            TripParticipation.trip_id == trip.id, TripParticipation.user_id == user.id
        )
    ).first()
    if existing and existing.status in (
        ParticipationStatus.accepted.value,
        ParticipationStatus.pending.value,
        ParticipationStatus.waitlisted.value,
    ):
        raise ConflictError("Une demande est déjà en cours ou acceptée pour ce trajet")

    accepted_count = len(_accepted_participant_ids(session, trip.id))
    vehicle = session.get(Vehicle, trip.vehicle_id) if trip.vehicle_id else None
    status_value = ParticipationStatus.pending.value
    if vehicle and accepted_count >= vehicle.seats:
        status_value = ParticipationStatus.waitlisted.value

    if existing:
        existing.status = status_value
        existing.boarding_point = boarding_point
        existing.requested_at = utcnow()
        participation = existing
    else:
        participation = TripParticipation(
            trip_id=trip.id,
            user_id=user.id,
            role=ParticipationRole.passenger.value,
            status=status_value,
            boarding_point=boarding_point,
        )
    session.add(participation)
    session.commit()
    session.refresh(participation)
    return participation


def decide_participation(
    session: Session,
    trip: Trip,
    driver_actor: User,
    participation: TripParticipation,
    approve: bool,
) -> TripParticipation:
    if driver_actor.id != trip.driver_id:
        raise ForbiddenError("Seul le conducteur décide des demandes de place")
    if participation.trip_id != trip.id:
        raise ConflictError("Cette demande ne concerne pas ce trajet")
    if participation.status not in (ParticipationStatus.pending.value, ParticipationStatus.waitlisted.value):
        raise ConflictError("Cette demande a déjà été traitée")

    if approve:
        vehicle = session.get(Vehicle, trip.vehicle_id) if trip.vehicle_id else None
        accepted_count = len(_accepted_participant_ids(session, trip.id))
        if vehicle and accepted_count >= vehicle.seats:
            raise ConflictError("La capacité du véhicule est atteinte")
        participation.status = ParticipationStatus.accepted.value
    else:
        participation.status = ParticipationStatus.refused.value

    participation.decided_at = utcnow()
    participation.decided_by_id = driver_actor.id
    session.add(participation)
    session.commit()
    session.refresh(participation)
    return participation


def set_trip_status(session: Session, trip: Trip, actor: User, new_status: str) -> Trip:
    require_active_member(session, trip.group_id, actor.id)
    valid_statuses = {status.value for status in TripStatus}
    if new_status not in valid_statuses:
        raise ConflictError("Statut de trajet invalide")
    trip.status = new_status
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip


# --------------------------------------------------------------------------
# Prix mensuels du carburant/énergie
# --------------------------------------------------------------------------


def set_monthly_price(
    session: Session,
    vehicle: Vehicle,
    owner_actor: User,
    energy_type: str,
    year: int,
    month: int,
    price_per_unit: float,
) -> MonthlyEnergyPrice:
    if vehicle.owner_id != owner_actor.id:
        raise ForbiddenError("Seul le propriétaire du véhicule saisit son prix mensuel")
    if price_per_unit < 0:
        raise ConflictError("Le prix ne peut pas être négatif")
    existing = session.exec(
        select(MonthlyEnergyPrice).where(
            MonthlyEnergyPrice.vehicle_id == vehicle.id,
            MonthlyEnergyPrice.energy_type == energy_type,
            MonthlyEnergyPrice.year == year,
            MonthlyEnergyPrice.month == month,
        )
    ).first()
    if existing:
        existing.price_per_unit = price_per_unit
        existing.set_by_id = owner_actor.id
        existing.updated_at = utcnow()
        price = existing
    else:
        price = MonthlyEnergyPrice(
            vehicle_id=vehicle.id,
            energy_type=energy_type,
            year=year,
            month=month,
            price_per_unit=price_per_unit,
            set_by_id=owner_actor.id,
        )
    session.add(price)
    session.commit()
    session.refresh(price)
    return price


# --------------------------------------------------------------------------
# Bilan mensuel
# --------------------------------------------------------------------------


@dataclass
class LedgerIssue:
    code: str
    message: str


@dataclass
class LedgerComputation:
    group_id: int
    year: int
    month: int
    balances: dict[int, Decimal]
    transfers: list[tuple[int, int, Decimal]]
    concerned_user_ids: set[int] = field(default_factory=set)
    issues: list[LedgerIssue] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return bool(self.issues)


def compute_group_month(session: Session, group_id: int, year: int, month: int) -> LedgerComputation:
    trips = session.exec(
        select(Trip).where(Trip.group_id == group_id)
    ).all()
    trips_in_month = [trip for trip in trips if trip.date.year == year and trip.date.month == month]

    today = utcnow().date()
    issues: list[LedgerIssue] = []
    all_debts: list[tuple[int, int, Decimal]] = []
    concerned: set[int] = set()

    for trip in trips_in_month:
        if trip.status == TripStatus.cancelled.value:
            continue
        if trip.status == TripStatus.planned.value:
            if trip.date < today:
                issues.append(
                    LedgerIssue(
                        "unresolved_occurrence",
                        f"Le trajet du {trip.date} doit être marqué effectué ou annulé avant validation",
                    )
                )
            continue

        # trip.status == completed
        if trip.vehicle_id is None:
            issues.append(
                LedgerIssue("missing_vehicle", f"Le trajet du {trip.date} n'a pas de véhicule assigné")
            )
            continue

        vehicle_energies = session.exec(
            select(VehicleEnergy).where(VehicleEnergy.vehicle_id == trip.vehicle_id)
        ).all()
        consumptions = [
            billing.EnergyConsumption(energy.energy_type, energy.consumption_per_100km)
            for energy in vehicle_energies
        ]

        prices: dict[str, float] = {}
        missing_price = False
        for energy in vehicle_energies:
            price_row = session.exec(
                select(MonthlyEnergyPrice).where(
                    MonthlyEnergyPrice.vehicle_id == trip.vehicle_id,
                    MonthlyEnergyPrice.energy_type == energy.energy_type,
                    MonthlyEnergyPrice.year == year,
                    MonthlyEnergyPrice.month == month,
                )
            ).first()
            if not price_row:
                issues.append(
                    LedgerIssue(
                        "missing_price",
                        f"Prix manquant pour le véhicule {trip.vehicle_id} "
                        f"({energy.energy_type}) en {month:02d}/{year}",
                    )
                )
                missing_price = True
            else:
                prices[energy.energy_type] = price_row.price_per_unit

        segments_db = session.exec(
            select(TripSegment).where(TripSegment.trip_id == trip.id)
        ).all()
        segments_db.sort(key=lambda segment: segment.sequence)
        if not segments_db:
            issues.append(
                LedgerIssue("missing_segments", f"Le trajet du {trip.date} n'a aucun tronçon renseigné")
            )
            continue
        if missing_price:
            continue

        segment_inputs = []
        for segment in segments_db:
            occupant_rows = session.exec(
                select(TripSegmentOccupant).where(TripSegmentOccupant.segment_id == segment.id)
            ).all()
            occupant_ids = [occupant.user_id for occupant in occupant_rows]
            segment_inputs.append(
                billing.SegmentInput(
                    distance_km=segment.distance_km,
                    occupant_ids=occupant_ids,
                    is_detour=segment.is_detour,
                    detour_for_id=segment.detour_for_user_id,
                )
            )

        shares = billing.compute_trip_shares(segment_inputs, consumptions, prices)
        concerned.update(shares.keys())
        concerned.add(trip.driver_id)
        all_debts.extend(billing.trip_debts(shares, trip.driver_id))

    balances = billing.net_balances(all_debts)

    reimbursements = session.exec(
        select(Reimbursement).where(
            Reimbursement.group_id == group_id,
            Reimbursement.year == year,
            Reimbursement.month == month,
            Reimbursement.status == ReimbursementStatus.confirmed.value,
        )
    ).all()
    for reimbursement in reimbursements:
        billing.apply_reimbursement(balances, reimbursement.payer_id, reimbursement.payee_id, reimbursement.amount)

    adjustments = session.exec(
        select(LedgerAdjustment).where(
            LedgerAdjustment.group_id == group_id,
            LedgerAdjustment.year == year,
            LedgerAdjustment.month == month,
        )
    ).all()
    for adjustment in adjustments:
        balances[adjustment.user_id] = balances.get(adjustment.user_id, Decimal("0")) + Decimal(
            str(adjustment.amount)
        )

    transfers = billing.simplify_debts(balances) if not issues else []
    return LedgerComputation(
        group_id=group_id,
        year=year,
        month=month,
        balances=balances,
        transfers=transfers,
        concerned_user_ids=concerned,
        issues=issues,
    )


def get_or_create_ledger(session: Session, group_id: int, year: int, month: int) -> MonthlyLedger:
    ledger = session.exec(
        select(MonthlyLedger).where(
            MonthlyLedger.group_id == group_id, MonthlyLedger.year == year, MonthlyLedger.month == month
        )
    ).first()
    if not ledger:
        ledger = MonthlyLedger(group_id=group_id, year=year, month=month)
        session.add(ledger)
        session.commit()
        session.refresh(ledger)
    return ledger


def validate_ledger(
    session: Session, group: Group, actor: User, year: int, month: int
) -> tuple[MonthlyLedger, LedgerComputation]:
    computation = compute_group_month(session, group.id, year, month)
    if actor.id not in computation.concerned_user_ids:
        raise ForbiddenError("Seuls les participants des trajets du mois valident le bilan")

    ledger = get_or_create_ledger(session, group.id, year, month)
    if ledger.status == LedgerStatus.closed.value:
        raise ConflictError("Le bilan est déjà clôturé")

    validation = session.exec(
        select(LedgerValidation).where(
            LedgerValidation.ledger_id == ledger.id, LedgerValidation.user_id == actor.id
        )
    ).first()
    if not validation:
        validation = LedgerValidation(ledger_id=ledger.id, user_id=actor.id)
    validation.approved = True
    validation.decided_at = utcnow()
    session.add(validation)
    session.commit()

    if not computation.issues:
        approved_rows = session.exec(
            select(LedgerValidation).where(
                LedgerValidation.ledger_id == ledger.id, LedgerValidation.approved == True  # noqa: E712
            )
        ).all()
        approved_ids = {row.user_id for row in approved_rows}
        if computation.concerned_user_ids and computation.concerned_user_ids.issubset(approved_ids):
            ledger.status = LedgerStatus.closed.value
            ledger.closed_at = utcnow()
            ledger.closed_by_id = actor.id
            session.add(ledger)
            session.commit()
            session.refresh(ledger)

    return ledger, computation


def declare_reimbursement(
    session: Session, group: Group, payer_actor: User, payee_id: int, amount: float, year: int, month: int
) -> Reimbursement:
    require_active_member(session, group.id, payer_actor.id)
    if amount <= 0:
        raise ConflictError("Le montant remboursé doit être positif")
    reimbursement = Reimbursement(
        group_id=group.id,
        year=year,
        month=month,
        payer_id=payer_actor.id,
        payee_id=payee_id,
        amount=amount,
    )
    session.add(reimbursement)
    session.commit()
    session.refresh(reimbursement)
    return reimbursement


def confirm_reimbursement(session: Session, reimbursement: Reimbursement, payee_actor: User) -> Reimbursement:
    if reimbursement.payee_id != payee_actor.id:
        raise ForbiddenError("Seul le bénéficiaire confirme le remboursement")
    if reimbursement.status == ReimbursementStatus.confirmed.value:
        raise ConflictError("Ce remboursement est déjà confirmé")
    reimbursement.status = ReimbursementStatus.confirmed.value
    reimbursement.confirmed_at = utcnow()
    session.add(reimbursement)
    session.commit()
    session.refresh(reimbursement)
    return reimbursement


def correct_segment_distance(
    session: Session,
    ledger: MonthlyLedger,
    actor: User,
    segment: TripSegment,
    new_distance_km: float,
    reason: str,
) -> tuple[LedgerCorrection, list[LedgerAdjustment]]:
    group = session.get(Group, ledger.group_id)
    if actor.id != group.manager_id:
        raise ForbiddenError("Seul le gestionnaire du groupe corrige un bilan clôturé")
    if ledger.status != LedgerStatus.closed.value:
        raise ConflictError("Seul un bilan clôturé peut faire l'objet d'une correction tracée")
    if not reason or not reason.strip():
        raise ConflictError("Un motif de correction est obligatoire")
    if new_distance_km <= 0:
        raise ConflictError("La distance doit être positive")

    before = compute_group_month(session, ledger.group_id, ledger.year, ledger.month)
    old_value = segment.distance_km
    segment.distance_km = new_distance_km
    session.add(segment)
    session.commit()
    after = compute_group_month(session, ledger.group_id, ledger.year, ledger.month)

    correction = LedgerCorrection(
        ledger_id=ledger.id,
        entity_type="trip_segment",
        entity_id=segment.id,
        field="distance_km",
        old_value=str(old_value),
        new_value=str(new_distance_km),
        author_id=actor.id,
        reason=reason,
    )
    session.add(correction)
    session.commit()
    session.refresh(correction)

    if ledger.month == 12:
        next_year, next_month = ledger.year + 1, 1
    else:
        next_year, next_month = ledger.year, ledger.month + 1

    adjustments: list[LedgerAdjustment] = []
    all_user_ids = set(before.balances) | set(after.balances)
    for user_id in all_user_ids:
        delta = after.balances.get(user_id, Decimal("0")) - before.balances.get(user_id, Decimal("0"))
        if delta != 0:
            adjustment = LedgerAdjustment(
                group_id=ledger.group_id,
                year=next_year,
                month=next_month,
                user_id=user_id,
                amount=float(delta),
                reason=reason,
                source_correction_id=correction.id,
            )
            session.add(adjustment)
            adjustments.append(adjustment)
    session.commit()
    for adjustment in adjustments:
        session.refresh(adjustment)
    return correction, adjustments
