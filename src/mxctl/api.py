"""HTTP client for the MXroute API (https://api.mxroute.com).

Success is recognized only by the exact expected status code, and every
response body the CLI relies on is validated against the models in
mxctl.models before anything is returned to the caller.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from pydantic import TypeAdapter, ValidationError

from .config import Config
from .models import CatchAll, EmailAccount, ErrorEnvelope, Forwarder, SuccessEnvelope

T = TypeVar("T")

_DOMAINS = TypeAdapter(SuccessEnvelope[list[str]])
_ACCOUNTS = TypeAdapter(SuccessEnvelope[list[EmailAccount]])
_FORWARDERS = TypeAdapter(SuccessEnvelope[list[Forwarder]])
_CATCHALL = TypeAdapter(SuccessEnvelope[CatchAll])


class ApiError(Exception):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


def _segment(value: str) -> str:
    return quote(value, safe="")


class MxrouteClient:
    def __init__(self, config: Config, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=config.api_url,
            headers={
                "X-Server": config.server,
                "X-Username": config.username,
                "X-API-Key": config.api_key,
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MxrouteClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _request(
        self, method: str, path: str, expect: int, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        try:
            response = self._client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise ApiError(f"request failed: {exc}") from exc
        if response.status_code != expect:
            raise self._error_from(response)
        return response

    def _error_from(self, response: httpx.Response) -> ApiError:
        try:
            envelope = ErrorEnvelope.model_validate_json(response.content)
        except ValidationError:
            snippet = response.text.strip()[:200] or "<empty body>"
            return ApiError(f"unexpected API response (HTTP {response.status_code}): {snippet}")
        detail = envelope.error
        return ApiError(f"{detail.message} ({detail.code})", code=detail.code)

    def _validated(self, response: httpx.Response, adapter: TypeAdapter[SuccessEnvelope[T]]) -> T:
        try:
            return adapter.validate_json(response.content).data
        except ValidationError as exc:
            first = str(exc.errors()[0].get("loc", "")) if exc.errors() else ""
            raise ApiError(f"unexpected API response: schema validation failed at {first}") from exc

    def list_domains(self) -> list[str]:
        return self._validated(self._request("GET", "/domains", 200), _DOMAINS)

    def list_accounts(self, domain: str) -> list[EmailAccount]:
        path = f"/domains/{_segment(domain)}/email-accounts"
        return self._validated(self._request("GET", path, 200), _ACCOUNTS)

    def create_account(
        self,
        domain: str,
        username: str,
        password: str,
        quota: int | None = None,
        limit: int | None = None,
    ) -> None:
        body: dict[str, Any] = {"username": username, "password": password}
        if quota is not None:
            body["quota"] = quota
        if limit is not None:
            body["limit"] = limit
        self._request("POST", f"/domains/{_segment(domain)}/email-accounts", 201, json=body)

    def delete_account(self, domain: str, username: str) -> None:
        path = f"/domains/{_segment(domain)}/email-accounts/{_segment(username)}"
        self._request("DELETE", path, 204)

    def list_forwarders(self, domain: str) -> list[Forwarder]:
        path = f"/domains/{_segment(domain)}/forwarders"
        return self._validated(self._request("GET", path, 200), _FORWARDERS)

    def create_forwarder(self, domain: str, alias: str, destinations: list[str]) -> None:
        body = {"alias": alias, "destinations": destinations}
        self._request("POST", f"/domains/{_segment(domain)}/forwarders", 201, json=body)

    def delete_forwarder(self, domain: str, alias: str) -> None:
        path = f"/domains/{_segment(domain)}/forwarders/{_segment(alias)}"
        self._request("DELETE", path, 204)

    def get_catchall(self, domain: str) -> CatchAll:
        path = f"/domains/{_segment(domain)}/catch-all"
        return self._validated(self._request("GET", path, 200), _CATCHALL)

    def set_catchall(self, domain: str, type_: str, address: str | None = None) -> None:
        body: dict[str, Any] = {"type": type_}
        if address is not None:
            body["address"] = address
        self._request("PATCH", f"/domains/{_segment(domain)}/catch-all", 200, json=body)
