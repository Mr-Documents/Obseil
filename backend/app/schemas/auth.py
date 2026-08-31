"""Authentication request and response contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.schemas.common import ORMModel

MIN_PASSWORD_LENGTH = 8

_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")


class PasswordMixin(BaseModel):
    """Password policy, applied identically wherever a password is accepted.

    The rules are deliberately modest — length matters far more than symbol
    classes — but a password with no digit or no letter is rejected because it
    is almost always a dictionary word or a PIN.
    """

    password: Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=BCRYPT_MAX_BYTES)]

    @field_validator("password")
    @classmethod
    def _validate_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes.")
        if not _HAS_LETTER.search(value) or not _HAS_DIGIT.search(value):
            raise ValueError("Password must contain at least one letter and one number.")
        return value


class RegisterRequest(PasswordMixin):
    email: EmailStr
    full_name: Annotated[str, Field(min_length=1, max_length=120)]

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Please enter your name.")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    # No strength validation on login: the policy may have changed since the
    # account was created, and rejecting early would leak that a password is
    # "too weak to be real" for this account.
    password: Annotated[str, Field(min_length=1, max_length=BCRYPT_MAX_BYTES)]


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")


class UserRead(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    created_at: datetime


class AuthResponse(BaseModel):
    """Returned by register and login: the tokens plus who you now are."""

    user: UserRead
    tokens: TokenPair
