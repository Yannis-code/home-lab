"""Génération des dates d'occurrence d'un modèle de trajet récurrent.

Module pur (aucune dépendance base de données), afin de pouvoir tester
facilement la logique calendaire.
"""

from datetime import date, timedelta
from typing import Iterable


def generate_dates(weekdays: Iterable[int], start: date, end: date) -> list[date]:
    """Dates comprises entre ``start`` et ``end`` (inclus) tombant sur un des jours donnés.

    ``weekdays`` utilise la convention de ``date.weekday()`` (0 = lundi ... 6 = dimanche).
    """
    weekday_set = set(weekdays)
    if start > end:
        return []
    span_days = (end - start).days
    return [
        start + timedelta(days=offset)
        for offset in range(span_days + 1)
        if (start + timedelta(days=offset)).weekday() in weekday_set
    ]
