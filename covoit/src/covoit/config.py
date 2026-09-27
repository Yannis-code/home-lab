"""Configuration de l'application, lue depuis les variables d'environnement."""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str = os.environ.get("COVOIT_DATABASE_URL", "sqlite:///./covoit.db")
    session_ttl_hours: int = int(os.environ.get("COVOIT_SESSION_TTL_HOURS", "168"))
    admin_name: str = os.environ.get("COVOIT_ADMIN_NAME", "Administrateur")
    admin_email: str = os.environ.get("COVOIT_ADMIN_EMAIL", "admin@covoit.home")
    admin_password: str = os.environ.get("COVOIT_ADMIN_PASSWORD", "")


settings = Settings()
