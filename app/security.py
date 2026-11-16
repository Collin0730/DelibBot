"""Who is calling. Three kinds of caller, all sent as 'Authorization: Bearer <token>':

* organiser: a signed token from POST /api/auth/login
* moderator: 'm.<access_token>' from their personal link
* participant: 'p.<invite_token>' from their invite link

Links stand in for email sign-in, so treat them like passwords.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import timedelta

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as Db

from . import models as m
from . import settings
from .db import get_db


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(got, base64.b64decode(digest))
    except Exception:  # noqa: BLE001
        return False


def organiser_token(organiser: m.Organiser) -> str:
    return jwt.encode({"sub": str(organiser.id), "exp": m.now() + timedelta(hours=settings.TOKEN_HOURS)}, settings.SECRET_KEY, algorithm="HS256")


@dataclass
class Actor:
    role: str  # organiser | moderator | participant
    person: m.Person
    organiser: m.Organiser | None = None
    moderator: m.Moderator | None = None
    participant: m.Participant | None = None

    @property
    def name(self) -> str:
        return self.person.full_name


def resolve_token(db: Db, token: str | None) -> Actor | None:
    if not token:
        return None
    if token.startswith("p."):
        p = db.scalar(select(m.Participant).where(m.Participant.invite_token == token[2:]))
        if p and p.invite_status != "cancelled" and p.invite_status != "not_invited" and not p.is_simulated:
            return Actor("participant", p.person, participant=p)
        return None
    if token.startswith("m."):
        mod = db.scalar(select(m.Moderator).where(m.Moderator.access_token == token[2:], m.Moderator.removed_at.is_(None)))
        return Actor("moderator", mod.person, moderator=mod) if mod else None
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    org = db.get(m.Organiser, data.get("sub"))
    return Actor("organiser", org.person, organiser=org) if org else None


def current_actor(authorization: str | None = Header(default=None), db: Db = Depends(get_db)) -> Actor:
    token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
    actor = resolve_token(db, token)
    if not actor:
        raise HTTPException(401, "Sign in again: this link or session is not valid.")
    return actor


def organiser_only(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role != "organiser":
        raise HTTPException(403, "Only an organiser can do this.")
    return actor


def participant_only(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role != "participant":
        raise HTTPException(403, "Only a participant can do this.")
    return actor


def load_deliberation(db: Db, delib_id, actor: Actor, manage: bool = False) -> m.Deliberation:
    """Fetch a deliberation the caller may see. manage=True means organiser or its moderator."""
    d = db.get(m.Deliberation, delib_id)
    if not d:
        raise HTTPException(404, "Deliberation not found.")
    if actor.role == "organiser":
        return d
    if actor.role == "moderator" and d.moderator_id == actor.moderator.id:
        return d
    if actor.role == "participant" and actor.participant.deliberation_id == d.id and not manage:
        return d
    raise HTTPException(403, "You do not have access to this deliberation.")
