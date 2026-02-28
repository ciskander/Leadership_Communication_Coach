"""
api/app.py — FastAPI application factory.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from ..auth.sqlite_db import init_db
from .routes_auth import router as auth_router
from .routes_transcripts import router as transcripts_router
from .routes_runs import router as runs_router
from .routes_coachee import router as coachee_router
from .routes_experiments import router as experiments_router
from .routes_coach import router as coach_router
from .routes_admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Leadership Coach API",
        version="0.2.1",
        lifespan=lifespan,
    )

    # ── Session middleware (required by authlib Starlette client) ─────────────
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get("SESSION_SECRET", "change-me"),
        https_only=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        same_site="lax",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    origins = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://localhost:5173",
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(auth_router)
    app.include_router(transcripts_router)
    app.include_router(runs_router)
    app.include_router(coachee_router)
    app.include_router(experiments_router)
    app.include_router(coach_router)
    app.include_router(admin_router)

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.2.1"}

    # ── Global exception handler ──────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                },
                "status": "error",
            },
        )

    return app
