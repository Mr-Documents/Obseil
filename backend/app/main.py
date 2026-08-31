"""Obseil API application factory.

Wires together middleware, exception handlers and the versioned router. Keep
this module thin: it should read as a table of contents for the application.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import ObseilError
from app.core.logging import configure_logging, request_id_ctx

logger = logging.getLogger("obseil")

DESCRIPTION = """
**Obseil** — AI-powered data quality intelligence.

Upload a dataset, and Obseil profiles it, runs deterministic quality detectors,
runs unsupervised anomaly detection, and produces an explainable 0-100 quality
score backed by individually reviewable findings.
"""


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the single error envelope used by every failure path."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id_ctx.get() or "-",
            }
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level, settings.log_format)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Obseil API starting",
        extra={"version": __version__, "environment": settings.env},
    )
    yield
    logger.info("Obseil API stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.project_name} API",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # --- Middleware --------------------------------------------------------
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        """Assign a request id, time the request and log its outcome."""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    # --- Exception handlers ------------------------------------------------
    @app.exception_handler(ObseilError)
    async def handle_obseil_error(request: Request, exc: ObseilError) -> JSONResponse:
        log = logger.warning if exc.status_code < 500 else logger.error
        log(
            "%s: %s",
            exc.code,
            exc.message,
            extra={"path": request.url.path, "status_code": exc.status_code},
        )
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]) or "body",
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return _error_response(
            422,
            "validation_error",
            "Some of the submitted values are not valid.",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "authentication_failed", 403: "permission_denied", 404: "not_found"}.get(
            exc.status_code, "http_error"
        )
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database error on %s", request.url.path)
        return _error_response(
            503, "database_error", "The service is temporarily unavailable. Please try again."
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # The traceback goes to the logs, never to the client.
        logger.exception("Unhandled error on %s", request.url.path)
        return _error_response(
            500,
            "internal_error",
            "Something went wrong on our side. Quote the request id when reporting this.",
        )

    # --- Routes ------------------------------------------------------------
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "name": settings.project_name,
            "tagline": "Uncover what's hidden in your data.",
            "version": __version__,
            "docs": "/docs",
        }

    return app


app = create_app()
