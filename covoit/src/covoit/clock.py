"""Horloge centralisée pour les horodatages de l'application.

SQLModel >= 0.0.47 exige des ``datetime`` avec fuseau horaire pour ses
colonnes datetime (type ``UTCDateTime``), qui renvoie toujours un datetime
"aware" en UTC à la lecture, y compris sur SQLite. On utilise donc partout
des datetimes "aware" en UTC plutôt que naïfs.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
