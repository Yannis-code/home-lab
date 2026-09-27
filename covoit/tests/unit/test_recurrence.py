from datetime import date

from covoit.recurrence import generate_dates


def test_generate_dates_filters_by_weekday():
    # Monday 2026-01-05 through Sunday 2026-01-11
    dates = generate_dates(weekdays=[0, 1, 2, 3, 4], start=date(2026, 1, 5), end=date(2026, 1, 11))
    assert dates == [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]


def test_generate_dates_empty_when_start_after_end():
    assert generate_dates(weekdays=[0], start=date(2026, 2, 1), end=date(2026, 1, 1)) == []


def test_generate_dates_single_day_included():
    wednesday = date(2026, 1, 7)
    assert generate_dates(weekdays=[2], start=wednesday, end=wednesday) == [wednesday]


def test_generate_dates_no_matching_weekday():
    assert generate_dates(weekdays=[5, 6], start=date(2026, 1, 5), end=date(2026, 1, 9)) == []
