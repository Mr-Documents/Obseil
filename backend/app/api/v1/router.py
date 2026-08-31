"""Aggregates every v1 route module into a single router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    anomalies,
    auth,
    datasets,
    findings,
    health,
    history,
    projects,
    reports,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(datasets.router)
api_router.include_router(findings.router)
api_router.include_router(anomalies.router)
api_router.include_router(history.router)
api_router.include_router(reports.router)
