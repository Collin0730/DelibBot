"""Deliberation Partner: one FastAPI service that serves the API and the web app."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import settings
from .db import SessionLocal
from .realtime import hub
from .routers import organiser, participant, review, room

WEB = Path(__file__).resolve().parent.parent / "web"
log = logging.getLogger("delib")


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.loop = asyncio.get_running_loop()
    if settings.ADMIN_PASSWORD == "change-me" or settings.SECRET_KEY.startswith("dev-only"):
        if os.environ.get("RAILWAY_ENVIRONMENT"):
            # A public site must not run with the well-known defaults.
            raise RuntimeError("Set the SECRET_KEY and ADMIN_PASSWORD variables on Railway before the service can start.")
        log.warning("Using the default ADMIN_PASSWORD or SECRET_KEY. Set both before deploying.")
    with SessionLocal() as db:
        organiser.bootstrap_admin(db)
    yield


app = FastAPI(title="Deliberation Partner API", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
for r in (organiser.router, participant.router, room.router, review.router):
    app.include_router(r)
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Every other path is a page of the web app, which does its own routing."""
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})
