"""Point d'entrée FastAPI: création de l'application, routers, démarrage."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .config import settings
from .db import engine, init_db
from .models import User
from .routers import auth, groups, ledger, prices, trips, users, vehicles
from .security import generate_temporary_password, hash_password
from .services import ConflictError, ForbiddenError, NotFoundError

logger = logging.getLogger("covoit")


def _bootstrap_admin() -> None:
    """Crée le compte administrateur unique s'il n'existe pas encore."""
    with Session(engine) as session:
        existing_admin = session.exec(select(User).where(User.is_admin == True)).first()  # noqa: E712
        if existing_admin:
            return
        password = settings.admin_password or generate_temporary_password()
        admin = User(
            name=settings.admin_name,
            email=settings.admin_email,
            password_hash=hash_password(password),
            is_admin=True,
            must_change_password=True,
        )
        session.add(admin)
        session.commit()
        if not settings.admin_password:
            logger.warning(
                "Compte administrateur créé: %s / mot de passe temporaire (à changer): %s",
                settings.admin_email,
                password,
            )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _bootstrap_admin()
    yield


app = FastAPI(title="Covoit", version="0.1.0", lifespan=lifespan)


@app.exception_handler(ForbiddenError)
def _handle_forbidden(_request: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
def _handle_conflict(_request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(NotFoundError)
def _handle_not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(groups.router)
app.include_router(vehicles.router)
app.include_router(prices.router)
app.include_router(trips.router)
app.include_router(ledger.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Application web statique (PWA): montée en dernier pour ne jamais masquer les routes API ci-dessus.
_WEB_DIR = Path(__file__).resolve().parents[2] / "web"
if _WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")


def run() -> None:
    import uvicorn

    uvicorn.run("covoit.main:app", host="0.0.0.0", port=8000, reload=False)
