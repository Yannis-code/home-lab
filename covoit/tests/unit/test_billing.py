from decimal import Decimal

import pytest

from covoit import billing


def test_segment_fuel_cost_single_energy():
    cost = billing.segment_fuel_cost(
        distance_km=50,
        consumptions=[billing.EnergyConsumption("petrol", 6.0)],
        prices={"petrol": 1.80},
    )
    # 50 / 100 * 6.0 L * 1.80 EUR = 5.40 EUR
    assert cost == Decimal("5.40")


def test_segment_fuel_cost_sums_hybrid_energies():
    cost = billing.segment_fuel_cost(
        distance_km=100,
        consumptions=[
            billing.EnergyConsumption("petrol", 3.0),
            billing.EnergyConsumption("electric", 12.0),
        ],
        prices={"petrol": 1.90, "electric": 0.20},
    )
    # (100/100 * 3.0 * 1.90) + (100/100 * 12.0 * 0.20) = 5.70 + 2.40 = 8.10
    assert cost == Decimal("8.10")


def test_segment_fuel_cost_missing_price_raises():
    with pytest.raises(billing.MissingPriceError):
        billing.segment_fuel_cost(
            distance_km=10,
            consumptions=[billing.EnergyConsumption("diesel", 5.0)],
            prices={},
        )


def test_compute_trip_shares_splits_regular_segment_equally():
    segments = [
        billing.SegmentInput(distance_km=100, occupant_ids=["driver", "alice"]),
    ]
    shares = billing.compute_trip_shares(
        segments,
        consumptions=[billing.EnergyConsumption("petrol", 6.0)],
        prices={"petrol": 2.00},
    )
    # cost = 100/100 * 6.0 * 2.00 = 12.00, split between 2 people = 6.00 each
    assert shares == {"driver": Decimal("6.00"), "alice": Decimal("6.00")}


def test_compute_trip_shares_sums_across_segments():
    segments = [
        billing.SegmentInput(distance_km=50, occupant_ids=["driver"]),
        billing.SegmentInput(distance_km=50, occupant_ids=["driver", "alice"]),
    ]
    shares = billing.compute_trip_shares(
        segments,
        consumptions=[billing.EnergyConsumption("petrol", 6.0)],
        prices={"petrol": 2.00},
    )
    # segment 1: cost 6.00 solo -> driver += 6.00
    # segment 2: cost 6.00 split in two -> +3.00 each
    assert shares == {"driver": Decimal("9.00"), "alice": Decimal("3.00")}


def test_compute_trip_shares_detour_is_not_shared():
    segments = [
        billing.SegmentInput(distance_km=100, occupant_ids=["driver", "alice", "bob"]),
        billing.SegmentInput(
            distance_km=10,
            occupant_ids=["driver", "bob"],
            is_detour=True,
            detour_for_id="bob",
        ),
    ]
    shares = billing.compute_trip_shares(
        segments,
        consumptions=[billing.EnergyConsumption("petrol", 6.0)],
        prices={"petrol": 2.00},
    )
    # main segment: cost 12.00 split 3 ways = 4.00 each
    # detour segment: cost 1.20 fully charged to bob
    assert shares["driver"] == Decimal("4.00")
    assert shares["alice"] == Decimal("4.00")
    assert shares["bob"] == Decimal("4.00") + Decimal("1.20")


def test_compute_trip_shares_detour_without_target_raises():
    segments = [
        billing.SegmentInput(distance_km=10, occupant_ids=["bob"], is_detour=True),
    ]
    with pytest.raises(ValueError):
        billing.compute_trip_shares(
            segments,
            consumptions=[billing.EnergyConsumption("petrol", 6.0)],
            prices={"petrol": 2.00},
        )


def test_compute_trip_shares_segment_without_occupants_raises():
    segments = [billing.SegmentInput(distance_km=10, occupant_ids=[])]
    with pytest.raises(ValueError):
        billing.compute_trip_shares(
            segments,
            consumptions=[billing.EnergyConsumption("petrol", 6.0)],
            prices={"petrol": 2.00},
        )


def test_trip_debts_excludes_driver_own_share():
    shares = {"driver": Decimal("6.00"), "alice": Decimal("6.00")}
    debts = billing.trip_debts(shares, driver_id="driver")
    assert debts == [("alice", "driver", Decimal("6.00"))]


def test_net_balances_aggregates_multiple_trips():
    debts = [
        ("alice", "driver", Decimal("6.00")),
        ("bob", "driver", Decimal("4.00")),
        ("driver", "alice", Decimal("2.00")),  # driver was a passenger on another trip
    ]
    balances = billing.net_balances(debts)
    assert balances["driver"] == Decimal("6.00") + Decimal("4.00") - Decimal("2.00")
    assert balances["alice"] == Decimal("-6.00") + Decimal("2.00")
    assert balances["bob"] == Decimal("-4.00")


def test_apply_reimbursement_reduces_both_sides():
    balances = {"alice": Decimal("-30.00"), "bob": Decimal("30.00")}
    billing.apply_reimbursement(balances, payer_id="alice", payee_id="bob", amount=30)
    assert balances["alice"] == Decimal("0.00")
    assert balances["bob"] == Decimal("0.00")


def test_simplify_debts_minimizes_transfers():
    # alice owes 10, bob owes 20, driver is owed 30 in total.
    balances = {"alice": Decimal("-10.00"), "bob": Decimal("-20.00"), "driver": Decimal("30.00")}
    transfers = billing.simplify_debts(balances)
    assert len(transfers) == 2
    total_to_driver = sum(amount for debtor, creditor, amount in transfers if creditor == "driver")
    assert total_to_driver == Decimal("30.00")


def test_simplify_debts_handles_three_way_cycle_with_two_transfers():
    # A owes B 10, B owes C 10 -> net: A owes 10, C is owed 10, B is neutral.
    balances = {"a": Decimal("-10.00"), "b": Decimal("0.00"), "c": Decimal("10.00")}
    transfers = billing.simplify_debts(balances)
    assert transfers == [("a", "c", Decimal("10.00"))]
