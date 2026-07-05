import pytest
from pytest_httpserver import HTTPServer

from mxctl.api import ApiError, MxrouteClient
from mxctl.config import Config

from .conftest import AUTH_HEADERS

ACCOUNT = {
    "username": "box",
    "email": "box@example.com",
    "quota": 1024,
    "usage": 256.5,
    "limit": 9600,
    "sent": 42,
    "suspended": False,
}


def test_auth_headers_are_sent(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request(
        "/domains", method="GET", headers=AUTH_HEADERS
    ).respond_with_json({"success": True, "data": ["example.com"]})
    assert client.list_domains() == ["example.com"]


def test_list_accounts(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request(
        "/domains/example.com/email-accounts", method="GET"
    ).respond_with_json({"success": True, "data": [ACCOUNT]})
    accounts = client.list_accounts("example.com")
    assert [account.email for account in accounts] == ["box@example.com"]


def test_schema_violation_raises(httpserver: HTTPServer, client: MxrouteClient) -> None:
    broken = {key: value for key, value in ACCOUNT.items() if key != "email"}
    httpserver.expect_request(
        "/domains/example.com/email-accounts", method="GET"
    ).respond_with_json({"success": True, "data": [broken]})
    with pytest.raises(ApiError, match="schema validation failed"):
        client.list_accounts("example.com")


def test_success_false_with_200_raises(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request("/domains", method="GET").respond_with_json(
        {"success": False, "data": []}
    )
    with pytest.raises(ApiError, match="schema validation failed"):
        client.list_domains()


def test_create_account_body(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request(
        "/domains/example.com/email-accounts",
        method="POST",
        json={"username": "box", "password": "Secret123", "quota": 2048},
    ).respond_with_json({"success": True, "data": {}}, status=201)
    client.create_account("example.com", "box", "Secret123", quota=2048)


def test_delete_account_requires_exact_204(
    httpserver: HTTPServer, client: MxrouteClient
) -> None:
    httpserver.expect_request(
        "/domains/example.com/email-accounts/box", method="DELETE"
    ).respond_with_json({"success": True, "data": {}}, status=200)
    with pytest.raises(ApiError, match="HTTP 200"):
        client.delete_account("example.com", "box")


def test_delete_account_204(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request(
        "/domains/example.com/email-accounts/box", method="DELETE"
    ).respond_with_data(status=204)
    client.delete_account("example.com", "box")


def test_api_error_envelope_is_surfaced(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request(
        "/domains/example.com/email-accounts/ghost", method="DELETE"
    ).respond_with_json(
        {"success": False, "error": {"code": "NOT_FOUND", "message": "No such account"}},
        status=404,
    )
    with pytest.raises(ApiError, match=r"No such account \(NOT_FOUND\)") as excinfo:
        client.delete_account("example.com", "ghost")
    assert excinfo.value.code == "NOT_FOUND"


def test_unparseable_error_body(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request("/domains", method="GET").respond_with_data(
        "<html>boom</html>", status=502
    )
    with pytest.raises(ApiError, match="HTTP 502"):
        client.list_domains()


def test_forwarders_roundtrip(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request(
        "/domains/example.com/forwarders", method="GET"
    ).respond_with_json(
        {
            "success": True,
            "data": [
                {
                    "alias": "sales",
                    "email": "sales@example.com",
                    "destinations": ["team@other.com"],
                }
            ],
        }
    )
    httpserver.expect_request(
        "/domains/example.com/forwarders",
        method="POST",
        json={"alias": "info", "destinations": ["me@other.com"]},
    ).respond_with_json({"success": True, "data": {}}, status=201)
    httpserver.expect_request(
        "/domains/example.com/forwarders/sales", method="DELETE"
    ).respond_with_data(status=204)

    forwarders = client.list_forwarders("example.com")
    assert forwarders[0].destinations == ["team@other.com"]
    client.create_forwarder("example.com", "info", ["me@other.com"])
    client.delete_forwarder("example.com", "sales")


def test_catchall_roundtrip(httpserver: HTTPServer, client: MxrouteClient) -> None:
    httpserver.expect_request(
        "/domains/example.com/catch-all", method="GET"
    ).respond_with_json(
        {"success": True, "data": {"type": "address", "address": "all@example.com"}}
    )
    httpserver.expect_request(
        "/domains/example.com/catch-all", method="PATCH", json={"type": "fail"}
    ).respond_with_json({"success": True, "data": {}})

    catchall = client.get_catchall("example.com")
    assert catchall.type == "address"
    assert catchall.address == "all@example.com"
    client.set_catchall("example.com", "fail")


def test_connection_error() -> None:
    config = Config(
        server="s", username="u", api_key="k", api_url="http://127.0.0.1:1"
    )
    with MxrouteClient(config, timeout=1.0) as client:
        with pytest.raises(ApiError, match="request failed"):
            client.list_domains()
