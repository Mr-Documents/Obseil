"""Shared schema building blocks."""

from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for schemas read directly from SQLAlchemy instances."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """A single page of results plus everything a client needs to paginate.

    ``total`` is the count of matching rows, not the page length, so the UI can
    render "1-20 of 137" and disable the next-page control correctly.
    """

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class PaginationParams(BaseModel):
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    """The single error envelope returned by every failure path."""

    error: ErrorDetail


class MessageResponse(BaseModel):
    message: str
