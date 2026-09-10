"""Application configuration.

All settings are read from the environment (or a local ``.env``) with the
``OBSEIL_`` prefix. Nothing is hardcoded and no secret has a usable default:
``SECRET_KEY`` is validated on startup when running in production.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]

#: The lowest bcrypt cost production will accept. Twelve is the library
#: default and roughly a tenth of a second per hash on current hardware.
MINIMUM_PRODUCTION_HASH_ROUNDS = 12

_INSECURE_SECRETS = {
    "",
    "change-me",
    "change-me-in-production-use-a-long-random-value",
    "secret",
}

# Repository root: backend/app/core/config.py -> backend/ -> <repo>
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_prefix="OBSEIL_",
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core --------------------------------------------------------------
    env: Environment = "development"
    debug: bool = True
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    project_name: str = "Obseil"
    api_v1_prefix: str = "/api/v1"

    # --- Security ----------------------------------------------------------
    secret_key: str = "change-me-in-production-use-a-long-random-value"
    algorithm: str = "HS256"
    access_token_expire_minutes: Annotated[int, Field(gt=0, le=60 * 24)] = 30
    refresh_token_expire_days: Annotated[int, Field(gt=0, le=365)] = 14

    # --- Login rate limiting -----------------------------------------------
    # Counted per client address, and only on failures, so a legitimate user
    # who signs in correctly never meets it. Ten in five minutes stops a script
    # while leaving room for a person who has genuinely forgotten which
    # password they used.
    # bcrypt's cost is deliberately expensive, which makes the auth tests the
    # slowest in the suite. Lowering it for tests is safe and worth several
    # seconds a run; `_reject_insecure_production_config` refuses anything
    # below `MINIMUM_PRODUCTION_HASH_ROUNDS` outside development.
    password_hash_rounds: Annotated[int, Field(ge=4, le=18)] = 12

    login_rate_limit_enabled: bool = True
    login_max_attempts: Annotated[int, Field(gt=0, le=1000)] = 10
    login_attempt_window_seconds: Annotated[int, Field(gt=0, le=86_400)] = 300

    # --- Database ----------------------------------------------------------
    database_url: str = "postgresql+psycopg://obseil:obseil@localhost:5432/obseil"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # --- CORS --------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Uploads & storage -------------------------------------------------
    storage_backend: Literal["local"] = "local"
    storage_path: str = "./var/datasets"
    max_upload_bytes: Annotated[int, Field(gt=0)] = 50 * 1024 * 1024
    #: Above this the dataset is refused outright: a partial answer presented
    #: as a whole-file answer is worse than no answer.
    max_analysis_rows: Annotated[int, Field(gt=0)] = 1_000_000
    #: Above this the analysis runs on a deterministic head sample, and says so.
    #:
    #: Chosen from measurement, not intuition. Analysis runs inline in the
    #: upload request, so it has to finish in seconds: profiling a 200,000-row,
    #: 60-column file takes ~27s, while 50,000 rows takes ~7s. Fifty thousand
    #: rows is far more than any of the quality statistics need to be reliable,
    #: and the profile records both the sample size and the true row count so
    #: no percentage is ever read against the wrong denominator.
    profile_sample_rows: Annotated[int, Field(gt=0)] = 50_000

    # --- Machine learning --------------------------------------------------
    anomaly_contamination: str = "auto"
    anomaly_random_state: int = 42
    anomaly_max_anomalies_stored: Annotated[int, Field(gt=0)] = 500

    # ----------------------------------------------------------------------
    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Unsupported log level: {value}")
        return level

    @field_validator("anomaly_contamination")
    @classmethod
    def _validate_contamination(cls, value: str) -> str:
        if value == "auto":
            return value
        try:
            parsed = float(value)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError("anomaly_contamination must be 'auto' or a float") from exc
        if not 0.0 < parsed <= 0.5:
            raise ValueError("anomaly_contamination must be in (0, 0.5]")
        return value

    @model_validator(mode="after")
    def _reject_insecure_production_config(self) -> Settings:
        if self.env == "production":
            if self.secret_key in _INSECURE_SECRETS or len(self.secret_key) < 32:
                raise ValueError(
                    "OBSEIL_SECRET_KEY must be set to a strong random value in production."
                )
            if self.debug:
                raise ValueError("OBSEIL_DEBUG must be false in production.")
            if self.password_hash_rounds < MINIMUM_PRODUCTION_HASH_ROUNDS:
                raise ValueError(
                    "OBSEIL_PASSWORD_HASH_ROUNDS must be at least "
                    f"{MINIMUM_PRODUCTION_HASH_ROUNDS} in production."
                )
        return self

    # --- Derived helpers ---------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def contamination(self) -> str | float:
        return "auto" if self.anomaly_contamination == "auto" else float(self.anomaly_contamination)

    @property
    def storage_dir(self) -> Path:
        path = Path(self.storage_path)
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()


settings = get_settings()
