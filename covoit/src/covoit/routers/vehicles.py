"""Véhicules des utilisateurs et partage avec des groupes."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import services
from ..db import get_session
from ..deps import get_current_user
from ..models import Group, User, Vehicle, VehicleEnergy

router = APIRouter(tags=["vehicles"])


class EnergyInput(BaseModel):
    energy_type: str
    consumption_per_100km: float


class CreateVehicleRequest(BaseModel):
    brand: str
    model: str
    seats: int
    energies: list[EnergyInput]


class VehicleEnergyRead(BaseModel):
    energy_type: str
    consumption_per_100km: float


class VehicleRead(BaseModel):
    id: int
    owner_id: int
    brand: str
    model: str
    seats: int
    energies: list[VehicleEnergyRead]


class ShareVehicleRequest(BaseModel):
    group_id: int


def _serialize_vehicle(session: Session, vehicle: Vehicle) -> VehicleRead:
    energies = session.exec(select(VehicleEnergy).where(VehicleEnergy.vehicle_id == vehicle.id)).all()
    return VehicleRead(
        id=vehicle.id,
        owner_id=vehicle.owner_id,
        brand=vehicle.brand,
        model=vehicle.model,
        seats=vehicle.seats,
        energies=[
            VehicleEnergyRead(energy_type=e.energy_type, consumption_per_100km=e.consumption_per_100km)
            for e in energies
        ],
    )


@router.post("/vehicles", response_model=VehicleRead, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    payload: CreateVehicleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> VehicleRead:
    try:
        vehicle = services.add_vehicle(
            session,
            current_user,
            payload.brand,
            payload.model,
            payload.seats,
            [(e.energy_type, e.consumption_per_100km) for e in payload.energies],
        )
    except services.ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _serialize_vehicle(session, vehicle)


@router.get("/vehicles/mine", response_model=list[VehicleRead])
def list_my_vehicles(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[VehicleRead]:
    vehicles = session.exec(select(Vehicle).where(Vehicle.owner_id == current_user.id)).all()
    return [_serialize_vehicle(session, v) for v in vehicles]


@router.get("/groups/{group_id}/vehicles", response_model=list[VehicleRead])
def list_group_vehicles(
    group_id: int,
    driver_id: int | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[VehicleRead]:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Groupe introuvable")
    target_driver_id = driver_id if driver_id is not None else current_user.id
    vehicles = services.list_group_vehicles(session, group_id, target_driver_id)
    return [_serialize_vehicle(session, v) for v in vehicles]


@router.post("/vehicles/{vehicle_id}/share", status_code=status.HTTP_204_NO_CONTENT)
def share_vehicle(
    vehicle_id: int,
    payload: ShareVehicleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    vehicle = session.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Véhicule introuvable")
    group = session.get(Group, payload.group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Groupe introuvable")
    try:
        services.share_vehicle_with_group(session, vehicle, current_user, group)
    except services.ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
