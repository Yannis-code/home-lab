"""Hachage de mots de passe, jetons de session et mots de passe temporaires.

Les mots de passe sont hachés avec bcrypt (jamais stockés en clair). Les
jetons de session sont générés aléatoirement côté serveur et seul leur hachage
SHA-256 est persisté, afin qu'une fuite de la base ne permette pas de rejouer
une session active.
"""

import hashlib
import secrets

import bcrypt

from .clock import utcnow
from datetime import timedelta, datetime

_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Le mot de passe ne peut pas être vide")
    encoded = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    encoded = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        return False


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(9)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(hours: int) -> datetime:
    return utcnow() + timedelta(hours=hours)
