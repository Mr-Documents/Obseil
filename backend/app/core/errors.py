"""Application error types and their HTTP translation.

Every error raised deliberately by the application inherits from
:class:`ObseilError`. Handlers registered in ``app.main`` turn these into a
consistent JSON envelope::

    {"error": {"code": "dataset_invalid", "message": "...",
               "details": {...}, "request_id": "..."}}

Unhandled exceptions never leak a traceback to the client; they are logged with
the request id and returned as a generic ``internal_error``.
"""

from __future__ import annotations

from typing import Any


class ObseilError(Exception):
    """Base class for all deliberate application errors."""

    status_code: int = 400
    code: str = "bad_request"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        if code:
            self.code = code
        super().__init__(self.message)


# --- 4xx --------------------------------------------------------------------
class ValidationError(ObseilError):
    status_code = 422
    code = "validation_error"
    message = "The submitted data is not valid."


class AuthenticationError(ObseilError):
    status_code = 401
    code = "authentication_failed"
    message = "Could not validate credentials."


class PermissionDeniedError(ObseilError):
    status_code = 403
    code = "permission_denied"
    message = "You do not have access to this resource."


class NotFoundError(ObseilError):
    status_code = 404
    code = "not_found"
    message = "The requested resource does not exist."


class ConflictError(ObseilError):
    status_code = 409
    code = "conflict"
    message = "The resource already exists."


class PayloadTooLargeError(ObseilError):
    status_code = 413
    code = "payload_too_large"
    message = "The uploaded file is too large."


class UnsupportedMediaTypeError(ObseilError):
    status_code = 415
    code = "unsupported_media_type"
    message = "This file type is not supported."


# --- Domain specific --------------------------------------------------------
class DatasetError(ObseilError):
    """Raised when a dataset cannot be read, parsed, or is unusable."""

    status_code = 422
    code = "dataset_invalid"
    message = "The dataset could not be read."


class AnalysisError(ObseilError):
    """Raised when the analysis pipeline fails for an otherwise readable dataset."""

    status_code = 500
    code = "analysis_failed"
    message = "The analysis could not be completed."


class StorageError(ObseilError):
    status_code = 500
    code = "storage_error"
    message = "The file could not be stored or retrieved."
