"""Calcul des frais de carburant et des soldes du groupe.

Ce module est intentionnellement indépendant de la base de données: il ne
manipule que des structures simples (dataclasses, dict), ce qui permet de le
tester unitairement sans FastAPI ni SQLModel.

Règles reprises de la spécification (``covoit/SPEC.md``):

- le coût d'un tronçon est calculé à partir de sa distance, de la
  consommation moyenne du véhicule pour chaque source d'énergie configurée et
  du prix mensuel de cette énergie;
- un tronçon normal est partagé également entre toutes les personnes à bord,
  conducteur inclus;
- un tronçon de détour n'est pas partagé: son coût est intégralement imputé
  au passager pour lequel le détour est effectué;
- le conducteur avance le coût total du trajet; chaque autre participant lui
  doit sa part calculée;
- le bilan mensuel additionne ces dettes trajet par trajet, applique les
  remboursements confirmés, puis propose un nombre minimal de virements pour
  solder le groupe.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Hashable, Sequence

TWO_PLACES = Decimal("0.01")
UserId = Hashable


class MissingPriceError(Exception):
    """Le prix mensuel d'une énergie utilisée par le trajet n'est pas renseigné."""

    def __init__(self, energy_type: str):
        self.energy_type = energy_type
        super().__init__(f"Prix manquant pour l'énergie '{energy_type}'")


def to_money(value) -> Decimal:
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class EnergyConsumption:
    energy_type: str
    consumption_per_100km: float


@dataclass(frozen=True)
class SegmentInput:
    distance_km: float
    occupant_ids: Sequence[UserId]
    is_detour: bool = False
    detour_for_id: UserId | None = None


def segment_fuel_cost(
    distance_km: float,
    consumptions: Sequence[EnergyConsumption],
    prices: dict[str, float],
) -> Decimal:
    """Coût carburant d'un tronçon, somme des coûts de chaque énergie du véhicule."""
    distance = Decimal(str(distance_km))
    total = Decimal("0")
    for consumption in consumptions:
        price = prices.get(consumption.energy_type)
        if price is None:
            raise MissingPriceError(consumption.energy_type)
        consumption_amount = Decimal(str(consumption.consumption_per_100km))
        price_amount = Decimal(str(price))
        total += (distance / Decimal("100")) * consumption_amount * price_amount
    return total


def compute_trip_shares(
    segments: Sequence[SegmentInput],
    consumptions: Sequence[EnergyConsumption],
    prices: dict[str, float],
) -> dict[UserId, Decimal]:
    """Part de chaque participant pour l'ensemble des tronçons d'un trajet."""
    shares: dict[UserId, Decimal] = {}
    for segment in segments:
        cost = segment_fuel_cost(segment.distance_km, consumptions, prices)
        if segment.is_detour:
            if segment.detour_for_id is None:
                raise ValueError("Un tronçon de détour doit préciser le passager concerné")
            shares[segment.detour_for_id] = shares.get(segment.detour_for_id, Decimal("0")) + cost
        else:
            if not segment.occupant_ids:
                raise ValueError("Un tronçon normal doit avoir au moins un occupant")
            per_person = cost / len(segment.occupant_ids)
            for occupant_id in segment.occupant_ids:
                shares[occupant_id] = shares.get(occupant_id, Decimal("0")) + per_person
    return {user_id: to_money(amount) for user_id, amount in shares.items()}


def trip_debts(
    shares: dict[UserId, Decimal], driver_id: UserId
) -> list[tuple[UserId, UserId, Decimal]]:
    """Dettes (débiteur, créancier=conducteur, montant) engendrées par un trajet.

    La part du conducteur n'engendre pas de dette puisqu'il se la doit à
    lui-même (il l'a déjà avancée).
    """
    debts = []
    for user_id, amount in shares.items():
        if user_id == driver_id:
            continue
        if amount != 0:
            debts.append((user_id, driver_id, amount))
    return debts


def net_balances(
    debts: Sequence[tuple[UserId, UserId, Decimal]]
) -> dict[UserId, Decimal]:
    """Solde net par utilisateur: positif = doit recevoir, négatif = doit payer."""
    balances: dict[UserId, Decimal] = {}
    for debtor_id, creditor_id, amount in debts:
        balances[creditor_id] = balances.get(creditor_id, Decimal("0")) + amount
        balances[debtor_id] = balances.get(debtor_id, Decimal("0")) - amount
    return balances


def apply_reimbursement(
    balances: dict[UserId, Decimal], payer_id: UserId, payee_id: UserId, amount
) -> None:
    """Un remboursement confirmé réduit ce que le payeur doit et ce qui est dû au payé."""
    money = Decimal(str(amount))
    balances[payer_id] = balances.get(payer_id, Decimal("0")) + money
    balances[payee_id] = balances.get(payee_id, Decimal("0")) - money


def simplify_debts(
    balances: dict[UserId, Decimal]
) -> list[tuple[UserId, UserId, Decimal]]:
    """Réduit les soldes nets à un nombre minimal de virements (min cash-flow glouton).

    Retourne une liste de tuples ``(débiteur, créancier, montant)``.
    """
    creditors = [[user_id, amount] for user_id, amount in balances.items() if amount > 0]
    debtors = [[user_id, -amount] for user_id, amount in balances.items() if amount < 0]
    creditors.sort(key=lambda item: item[1], reverse=True)
    debtors.sort(key=lambda item: item[1], reverse=True)

    transfers: list[tuple[UserId, UserId, Decimal]] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor_id, debt_amount = debtors[i]
        creditor_id, credit_amount = creditors[j]
        amount = min(debt_amount, credit_amount)
        if amount > 0:
            transfers.append((debtor_id, creditor_id, to_money(amount)))
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] <= Decimal("0.00"):
            i += 1
        if creditors[j][1] <= Decimal("0.00"):
            j += 1
    return transfers
