from __future__ import annotations

import os

from runtime_config import PROJECT_ROOT  # Loads .env before route/database imports.
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import (
    auth,
    gmail,
    meta,
    profile,
    resume,
    recommendations,
    researchers,
    search,
    user_state,
    usage as usage_routes,
)
from database import professor_count
from api.production_config import validate_production_config
from api.auth.account_lock import account_lock
from api.auth.dependencies import optional_user
from fastapi.responses import JSONResponse
from api.retention import lifespan, enabled as retention_enabled
from api.admission import Admission, AdmissionMiddleware
from api import usage
import asyncio

def create_app() -> FastAPI:
    validate_production_config()
    app = FastAPI(
        lifespan=lifespan,
        title="Research Mentor Finder API",
        description=(
            "API over the existing professor database and search services. "
            "Serves Discover, professor profiles, recommended professors, "
            "authenticated per-user saved/outreach state and student profiles, "
            "and Gmail draft creation (drafts only — nothing is sent "
            "automatically)."
        ),
        version="0.7.0",
    )

    app.state.admission = Admission()
    app.add_middleware(AdmissionMiddleware, limiter=app.state.admission)
    origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app.middleware("http")
    async def protect_api_responses(request, call_next):
        private_change = request.url.path.startswith("/api/") and (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            or request.url.path.startswith("/api/gmail/")
            or request.url.path == "/api/auth/callback"
        )
        user = optional_user(request) if private_change else None
        if user:
            try:
                async with account_lock(user.user_id):
                    current = optional_user(request)
                    if current is None or current.user_id != user.user_id:
                        response = JSONResponse({"detail": "Your session ended. Sign in again."}, status_code=401)
                    else:
                        response = await call_next(request)
            except (TimeoutError, OSError):
                response = JSONResponse({"detail": "Account changes are temporarily unavailable. Try again."}, status_code=503)
        else:
            response = await call_next(request)
        metric = usage.action_metric(request.method, request.url.path)
        if metric and 200 <= response.status_code < 300 and request.headers.get('dnt') != '1' and request.headers.get('sec-gpc') != '1':
            await asyncio.to_thread(usage.increment, metric)
        if request.url.path.startswith("/api/"):
            # Covers account data, OAuth redirects, and stateless profile POSTs.
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(resume.router)
    app.include_router(search.router)
    app.include_router(researchers.router)
    app.include_router(meta.router)
    app.include_router(recommendations.router)
    app.include_router(user_state.router)
    app.include_router(gmail.router)
    app.include_router(usage_routes.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, object]:
        result = {"status": "ok", "total_researchers": professor_count()}
        if retention_enabled():
            result["retention"] = getattr(app.state, "retention", {"status": "starting"})
            result["offsite"] = getattr(app.state, "offsite", {"status": "starting"})
        return result

    return app


app = create_app()
