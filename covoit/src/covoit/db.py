"""Connexion et session SQLModel/SQLAlchemy."""

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)


def init_db() -> None:
    # Les imports sont locaux pour garantir que tous les modèles SQLModel
    # sont enregistrés dans les métadonnées avant la création des tables.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
