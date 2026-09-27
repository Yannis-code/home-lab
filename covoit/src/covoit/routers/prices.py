"""Prix mensuel des énergies pour un véhicule."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import services
from ..db import get_session
from ..deps import get_current_user
from ..models import MonthlyEnergyPrice, User, Vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/monthly-prices", tags=["prices"])


class SetPriceRequest(BaseModel):
    energy_type: str
    year: int
    month: int
    price_per_unit: float


class PriceRead(BaseModel):
    energy_type: str
    year: int
    month: int
    price_per_unit: float


def _serialize(price: MonthlyEnergyPrice) -> PriceRead:
    return PriceRead(
        energy_type=price.energy_type,
        year=price.year,
        month=price.month,
        price_per_unit=price.price_per_unit,
    )


@router.post("", response_model=PriceRead, status_code=status.HTTP_201_CREATED)
def set_monthly_price(
    vehicle_id: int,
    payload: SetPriceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PriceRead:
    vehicle = session.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Véhicule introuvable")
    try:
        price = services.set_monthly_price(
            session,
            vehicle,
            current_user,
            payload.energy_type,
            payload.year,
            payload.month,
            payload.price_per_unit,
        )
    except services.ForbiddenError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except services.ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _serialize(price)


@router.get("", response_model=list[PriceRead])
def list_monthly_prices(
    vehicle_id: int,
    year: int,
    month: int,
    session: Session = Depends(get_session),
    _current_user: User = Depends(get_current_user),
) -> list[PriceRead]:
    prices = session.exec(
        select(MonthlyEnergyPrice).where(
            MonthlyEnergyPrice.vehicle_id == vehicle_id,
            MonthlyEnergyPrice.year == year,
            MonthlyEnergyPrice.month == month,
        )
    ).all()
    return [_serialize(p) for p in prices]
