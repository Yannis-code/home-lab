"""Modèles de données SQLModel.

Les statuts (adhésion, trajet, participation, bilan, remboursement) sont
représentés par des colonnes ``str`` dont les valeurs autorisées sont
documentées par les classes ``Enum`` ci-dessous, plutôt que par un mappage
d'énumération SQL natif: cela évite les subtilités de portage entre moteurs
et garde les migrations simples.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel

from .clock import utcnow


class EnergyType(str, Enum):
    petrol = "petrol"
    diesel = "diesel"
    ethanol = "ethanol"
    electric = "electric"


# Unité affichée pour la consommation et le prix mensuel de chaque énergie.
CONSUMPTION_UNIT = {
    EnergyType.petrol: "L/100km",
    EnergyType.diesel: "L/100km",
    EnergyType.ethanol: "L/100km",
    EnergyType.electric: "kWh/100km",
}


class MembershipStatus(str, Enum):
    pending = "pending"
    active = "active"
    left = "left"


class TripStatus(str, Enum):
    planned = "planned"
    completed = "completed"
    cancelled = "cancelled"


class ParticipationRole(str, Enum):
    driver = "driver"
    passenger = "passenger"


class ParticipationStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    refused = "refused"
    waitlisted = "waitlisted"


class LedgerStatus(str, Enum):
    open = "open"
    closed = "closed"


class ReimbursementStatus(str, Enum):
    declared = "declared"
    confirmed = "confirmed"


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(index=True, unique=True)
    password_hash: str
    is_admin: bool = False
    is_active: bool = True
    must_change_password: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class SessionToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    token_hash: str = Field(index=True, unique=True)
    expires_at: datetime
    created_at: datetime = Field(default_factory=utcnow)


class Group(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    manager_id: int = Field(foreign_key="user.id")
    default_driver_id: Optional[int] = Field(default=None, foreign_key="user.id")
    is_archived: bool = False
    archived_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class GroupMembership(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    user_id: int = Field(foreign_key="user.id")
    invited_by_id: int = Field(foreign_key="user.id")
    status: str = Field(default=MembershipStatus.pending.value)
    invited_at: datetime = Field(default_factory=utcnow)
    joined_at: Optional[datetime] = None
    left_at: Optional[datetime] = None


class Vehicle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id")
    brand: str
    model: str
    seats: int


class VehicleEnergy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vehicle_id: int = Field(foreign_key="vehicle.id")
    energy_type: str
    consumption_per_100km: float


class VehicleGroupShare(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vehicle_id: int = Field(foreign_key="vehicle.id")
    group_id: int = Field(foreign_key="group.id")


class RecurringModel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    name: str
    origin: str
    destination: str
    weekdays_csv: str
    time_of_day: str
    created_by_id: int = Field(foreign_key="user.id")
    is_paused: bool = False
    created_at: datetime = Field(default_factory=utcnow)

    def weekdays(self) -> list[int]:
        return [int(value) for value in self.weekdays_csv.split(",") if value != ""]


class RecurringParticipant(SQLModel, table=True):
    """Liste fixe de passagers par défaut d'un modèle récurrent."""

    id: Optional[int] = Field(default=None, primary_key=True)
    recurring_model_id: int = Field(foreign_key="recurringmodel.id")
    user_id: int = Field(foreign_key="user.id")
    accepted: bool = False


class Trip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    recurring_model_id: Optional[int] = Field(default=None, foreign_key="recurringmodel.id")
    date: date
    time_of_day: str
    origin: str
    destination: str
    driver_id: int = Field(foreign_key="user.id")
    vehicle_id: Optional[int] = Field(default=None, foreign_key="vehicle.id")
    status: str = Field(default=TripStatus.planned.value)
    created_by_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)


class TripParticipation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trip_id: int = Field(foreign_key="trip.id")
    user_id: int = Field(foreign_key="user.id")
    role: str
    status: str = Field(default=ParticipationStatus.accepted.value)
    boarding_point: Optional[str] = None
    requested_at: datetime = Field(default_factory=utcnow)
    decided_at: Optional[datetime] = None
    decided_by_id: Optional[int] = Field(default=None, foreign_key="user.id")


class TripSegment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trip_id: int = Field(foreign_key="trip.id")
    sequence: int
    distance_km: float
    is_detour: bool = False
    detour_for_user_id: Optional[int] = Field(default=None, foreign_key="user.id")


class TripSegmentOccupant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    segment_id: int = Field(foreign_key="tripsegment.id")
    user_id: int = Field(foreign_key="user.id")


class MonthlyEnergyPrice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vehicle_id: int = Field(foreign_key="vehicle.id")
    energy_type: str
    year: int
    month: int
    price_per_unit: float
    set_by_id: int = Field(foreign_key="user.id")
    updated_at: datetime = Field(default_factory=utcnow)


class MonthlyLedger(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    year: int
    month: int
    status: str = Field(default=LedgerStatus.open.value)
    closed_at: Optional[datetime] = None
    closed_by_id: Optional[int] = Field(default=None, foreign_key="user.id")


class LedgerValidation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ledger_id: int = Field(foreign_key="monthlyledger.id")
    user_id: int = Field(foreign_key="user.id")
    approved: bool = False
    decided_at: Optional[datetime] = None


class Reimbursement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    year: int
    month: int
    payer_id: int = Field(foreign_key="user.id")
    payee_id: int = Field(foreign_key="user.id")
    amount: float
    status: str = Field(default=ReimbursementStatus.declared.value)
    declared_at: datetime = Field(default_factory=utcnow)
    confirmed_at: Optional[datetime] = None


class LedgerCorrection(SQLModel, table=True):
    """Trace d'audit d'une correction apportée après clôture d'un bilan."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ledger_id: int = Field(foreign_key="monthlyledger.id")
    entity_type: str
    entity_id: int
    field: str
    old_value: str
    new_value: str
    author_id: int = Field(foreign_key="user.id")
    reason: str
    created_at: datetime = Field(default_factory=utcnow)


class LedgerAdjustment(SQLModel, table=True):
    """Écart de solde reporté sur le bilan suivant suite à une correction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="group.id")
    year: int
    month: int
    user_id: int = Field(foreign_key="user.id")
    amount: float
    reason: str
    source_correction_id: Optional[int] = Field(default=None, foreign_key="ledgercorrection.id")
    created_at: datetime = Field(default_factory=utcnow)
