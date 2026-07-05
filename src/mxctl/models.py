"""Pydantic models for MXroute API responses.

Every 2xx response body is validated against these models before the CLI
acts on it. Required fields and types are enforced; unknown extra fields
are ignored so future API additions do not break the tool.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class EmailAccount(ApiModel):
    username: str
    email: str
    quota: int
    usage: float
    limit: int
    sent: int
    suspended: bool


class Forwarder(ApiModel):
    alias: str
    email: str
    destinations: list[str]


class CatchAll(ApiModel):
    type: Literal["fail", "blackhole", "address"]
    address: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _address_required_for_address_type(self) -> CatchAll:
        if self.type == "address" and not self.address:
            raise ValueError("catch-all type is 'address' but no address was provided")
        return self


class SuccessEnvelope(ApiModel, Generic[T]):
    success: Literal[True]
    data: T


class ApiErrorDetail(ApiModel):
    code: str
    message: str
    field: str | None = None


class ErrorEnvelope(ApiModel):
    success: Literal[False]
    error: ApiErrorDetail
