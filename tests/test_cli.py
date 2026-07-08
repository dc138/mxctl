from typing import Any

import pytest
from pytest_httpserver import HTTPServer
from typer.testing import CliRunner

from mxctl.cli import app

runner = CliRunner()


def account(email: str, **overrides: Any) -> dict[str, Any]:
    local, _, _ = email.rpartition("@")
    data: dict[str, Any] = {
        "username": local,
        "email": email,
        "quota": 1024,
        "usage": 10.5,
        "limit": 9600,
        "sent": 3,
        "suspended": False,
    }
    data.update(overrides)
    return data


def forwarder(email: str, *destinations: str) -> dict[str, Any]:
    local, _, _ = email.rpartition("@")
    return {"alias": local, "email": email, "destinations": list(destinations)}


def ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


def test_address_list_sorted(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(
        ok([account("b.a@domain.com"), account("a.b@domain.com"), account("a.a@domain.com")])
    )
    result = runner.invoke(app, ["address", "list", "domain.com"])
    assert result.exit_code == 0
    assert result.stdout == "a.a@domain.com\nb.a@domain.com\na.b@domain.com\n"
    assert result.stderr == ""


def test_address_list_all_domains_sorted(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(
        ok(["example.com", "domain.com"])
    )
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("b.a@domain.com"), account("a.a@domain.com")]))
    api_env.expect_request(
        "/domains/example.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("box@example.com")]))
    result = runner.invoke(app, ["address", "list"])
    assert result.exit_code == 0
    assert result.stdout == "a.a@domain.com\nb.a@domain.com\nbox@example.com\n"
    assert result.stderr == ""


def test_address_list_aligns_at_signs(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(
        ok(["example.com", "domain.com"])
    )
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("long.name@domain.com")]))
    api_env.expect_request(
        "/domains/example.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("box@example.com")]))
    result = runner.invoke(app, ["address", "list"])
    assert result.exit_code == 0
    assert result.stdout == "long.name@domain.com\n      box@example.com\n"


def test_address_list_verbose_aligns_extras(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(
        ok(["example.com", "domain.com"])
    )
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("long.name@domain.com")]))
    api_env.expect_request(
        "/domains/example.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("box@example.com")]))
    result = runner.invoke(app, ["-v", "address", "list"])
    assert result.exit_code == 0
    assert result.stdout == (
        "long.name@domain.com  quota=1024MB usage=10.5MB sent=3/9600\n"
        "      box@example.com quota=1024MB usage=10.5MB sent=3/9600\n"
    )


def test_address_list_alignment_ignores_color_codes(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("long.name@domain.com"), account("box@domain.com")]))
    result = runner.invoke(app, ["--color=always", "address", "list", "domain.com"])
    assert result.exit_code == 0
    assert result.stdout == (
        "      box\x1b[36m@domain.com\x1b[0m\nlong.name\x1b[36m@domain.com\x1b[0m\n"
    )


def test_address_list_plain_skips_padding(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("long.name@domain.com"), account("box@domain.com")]))
    result = runner.invoke(app, ["--plain", "address", "list", "domain.com"])
    assert result.exit_code == 0
    assert result.stdout == "box@domain.com\nlong.name@domain.com\n"


def test_plain_overrides_color_always(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("box@domain.com")]))
    result = runner.invoke(app, ["--plain", "--color=always", "address", "list", "domain.com"])
    assert result.exit_code == 0
    assert result.stdout == "box@domain.com\n"


def test_address_list_color_always(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("box@domain.com")]))
    result = runner.invoke(app, ["--color=always", "address", "list", "domain.com"])
    assert result.exit_code == 0
    assert result.stdout == "box\x1b[36m@domain.com\x1b[0m\n"


def test_address_list_verbose(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("box@domain.com", suspended=True)]))
    result = runner.invoke(app, ["-v", "address", "list", "domain.com"])
    assert result.exit_code == 0
    assert result.stdout == "box@domain.com quota=1024MB usage=10.5MB sent=3/9600 suspended\n"


def test_address_create_password_stdin(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts",
        method="POST",
        json={"username": "box", "password": "Secret123"},
    ).respond_with_json(ok({}), status=201)
    result = runner.invoke(
        app, ["address", "create", "box@domain.com", "--password-stdin"], input="Secret123\n"
    )
    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_address_create_flags_forwarded(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts",
        method="POST",
        json={"username": "box", "password": "Secret123", "quota": 0, "limit": 100},
    ).respond_with_json(ok({}), status=201)
    result = runner.invoke(
        app,
        [
            "-v",
            "address",
            "create",
            "box@domain.com",
            "--password-stdin",
            "--quota",
            "0",
            "--limit",
            "100",
        ],
        input="Secret123\n",
    )
    assert result.exit_code == 0
    assert "created address box@domain.com" in result.stderr


def test_address_create_weak_password(api_env: HTTPServer) -> None:
    result = runner.invoke(
        app, ["address", "create", "box@domain.com", "--password-stdin"], input="weak\n"
    )
    assert result.exit_code == 1
    assert "mxctl: error:" in result.stderr
    assert "password must be" in result.stderr
    assert len(api_env.log) == 0


def test_address_create_invalid_email(api_env: HTTPServer) -> None:
    result = runner.invoke(app, ["address", "create", "not-an-email"])
    assert result.exit_code == 2
    assert len(api_env.log) == 0


def test_address_delete_with_yes(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts/box", method="DELETE"
    ).respond_with_data(status=204)
    result = runner.invoke(app, ["address", "delete", "box@domain.com", "--yes"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert len(api_env.log) == 1


def test_address_delete_declined(
    api_env: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mxctl.cli.stdin_is_interactive", lambda: True)
    result = runner.invoke(app, ["address", "delete", "box@domain.com"], input="n\n")
    assert result.exit_code == 1
    assert "aborted" in result.stderr
    assert len(api_env.log) == 0


def test_address_delete_confirmed(
    api_env: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mxctl.cli.stdin_is_interactive", lambda: True)
    api_env.expect_request(
        "/domains/domain.com/email-accounts/box", method="DELETE"
    ).respond_with_data(status=204)
    result = runner.invoke(app, ["address", "delete", "box@domain.com"], input="y\n")
    assert result.exit_code == 0
    assert "Delete address box@domain.com?" in result.stderr
    assert len(api_env.log) == 1


def test_address_delete_requires_tty_or_yes(api_env: HTTPServer) -> None:
    result = runner.invoke(app, ["address", "delete", "box@domain.com"])
    assert result.exit_code == 1
    assert "pass --yes" in result.stderr
    assert len(api_env.log) == 0


def setup_forward_fixtures(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/domains", method="GET").respond_with_json(
        ok(["example.com", "domain.com"])
    )
    httpserver.expect_request(
        "/domains/domain.com/forwarders", method="GET"
    ).respond_with_json(
        ok(
            [
                forwarder("sales@domain.com", "team@other.net", "boss@other.com"),
                forwarder("info@domain.com", "me@other.com"),
            ]
        )
    )
    httpserver.expect_request(
        "/domains/example.com/forwarders", method="GET"
    ).respond_with_json(ok([forwarder("info@example.com", "me@other.com")]))


def test_forward_list_all(api_env: HTTPServer) -> None:
    setup_forward_fixtures(api_env)
    result = runner.invoke(app, ["forward", "list"])
    assert result.exit_code == 0
    assert result.stdout == (
        " info@domain.com  -> me@other.com\n"
        "sales@domain.com  -> boss@other.com, team@other.net\n"
        " info@example.com -> me@other.com\n"
    )


def test_forward_list_domain_suffix(api_env: HTTPServer) -> None:
    setup_forward_fixtures(api_env)
    result = runner.invoke(app, ["forward", "list", "@domain.com"])
    assert result.exit_code == 0
    assert result.stdout == (
        " info@domain.com -> me@other.com\n"
        "sales@domain.com -> boss@other.com, team@other.net\n"
    )


def test_forward_list_local_and_domain_suffix(api_env: HTTPServer) -> None:
    setup_forward_fixtures(api_env)
    result = runner.invoke(app, ["forward", "list", "es@domain.com"])
    assert result.exit_code == 0
    assert result.stdout == "sales@domain.com -> boss@other.com, team@other.net\n"


def test_forward_list_plain(api_env: HTTPServer) -> None:
    setup_forward_fixtures(api_env)
    result = runner.invoke(app, ["--plain", "forward", "list"])
    assert result.exit_code == 0
    assert result.stdout == (
        "info@domain.com: me@other.com\n"
        "sales@domain.com: boss@other.com, team@other.net\n"
        "info@example.com: me@other.com\n"
    )


def test_forward_list_bare_suffix(api_env: HTTPServer) -> None:
    setup_forward_fixtures(api_env)
    result = runner.invoke(app, ["forward", "list", ".com"])
    assert result.exit_code == 0
    assert "info@domain.com" in result.stdout
    assert "info@example.com" in result.stdout


def test_forward_list_unknown_domain_is_empty(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(ok(["domain.com"]))
    result = runner.invoke(app, ["forward", "list", "@nosuch.org"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert len(api_env.log) == 1


def test_forward_create(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/forwarders",
        method="POST",
        json={"alias": "info", "destinations": ["me@other.com"]},
    ).respond_with_json(ok({}), status=201)
    result = runner.invoke(app, ["forward", "create", "info@domain.com", "me@other.com"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_forward_create_blackhole_destination(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/forwarders",
        method="POST",
        json={"alias": "spam", "destinations": [":blackhole:"]},
    ).respond_with_json(ok({}), status=201)
    result = runner.invoke(app, ["forward", "create", "spam@domain.com", ":blackhole:"])
    assert result.exit_code == 0


def test_forward_create_invalid_destination(api_env: HTTPServer) -> None:
    result = runner.invoke(app, ["forward", "create", "info@domain.com", "nonsense"])
    assert result.exit_code == 2
    assert len(api_env.log) == 0


def test_forward_delete_with_yes(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/forwarders/info", method="DELETE"
    ).respond_with_data(status=204)
    result = runner.invoke(app, ["forward", "delete", "info@domain.com", "-y"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_wildcard_get_single(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/catch-all", method="GET"
    ).respond_with_json(ok({"type": "fail"}))
    result = runner.invoke(app, ["wildcard", "get", "domain.com"])
    assert result.exit_code == 0
    assert result.stdout == "fail\n"


def test_wildcard_get_single_address(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/catch-all", method="GET"
    ).respond_with_json(ok({"type": "address", "address": "all@domain.com"}))
    result = runner.invoke(app, ["wildcard", "get", "domain.com"])
    assert result.exit_code == 0
    assert result.stdout == "all@domain.com\n"


def test_wildcard_get_all_sorted(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(
        ok(["domain.net", "example.com", "domain.com"])
    )
    api_env.expect_request(
        "/domains/domain.com/catch-all", method="GET"
    ).respond_with_json(ok({"type": "fail"}))
    api_env.expect_request(
        "/domains/example.com/catch-all", method="GET"
    ).respond_with_json(ok({"type": "blackhole"}))
    api_env.expect_request(
        "/domains/domain.net/catch-all", method="GET"
    ).respond_with_json(ok({"type": "address", "address": "all@domain.net"}))
    result = runner.invoke(app, ["wildcard", "get"])
    assert result.exit_code == 0
    assert result.stdout == (
        "domain.com  fail\nexample.com blackhole\ndomain.net  all@domain.net\n"
    )


def test_wildcard_get_all_plain(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(
        ok(["example.com", "domain.com"])
    )
    api_env.expect_request(
        "/domains/domain.com/catch-all", method="GET"
    ).respond_with_json(ok({"type": "fail"}))
    api_env.expect_request(
        "/domains/example.com/catch-all", method="GET"
    ).respond_with_json(ok({"type": "address", "address": "all@example.com"}))
    result = runner.invoke(app, ["--plain", "wildcard", "get"])
    assert result.exit_code == 0
    assert result.stdout == "domain.com fail\nexample.com all@example.com\n"


def test_wildcard_get_all_aligns_address_policies(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(ok(["a.com", "b.com"]))
    api_env.expect_request("/domains/a.com/catch-all", method="GET").respond_with_json(
        ok({"type": "address", "address": "all@a.com"})
    )
    api_env.expect_request("/domains/b.com/catch-all", method="GET").respond_with_json(
        ok({"type": "address", "address": "forward.this@b.com"})
    )
    result = runner.invoke(app, ["wildcard", "get"])
    assert result.exit_code == 0
    assert result.stdout == "a.com          all@a.com\nb.com forward.this@b.com\n"


def test_wildcard_set_fail(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/catch-all", method="PATCH", json={"type": "fail"}
    ).respond_with_json(ok({}))
    result = runner.invoke(app, ["wildcard", "set", "domain.com", "fail"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_wildcard_set_address(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/catch-all",
        method="PATCH",
        json={"type": "address", "address": "all@other.com"},
    ).respond_with_json(ok({}))
    result = runner.invoke(app, ["wildcard", "set", "domain.com", "all@other.com"])
    assert result.exit_code == 0


def test_api_error_is_rendered(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/nosuch.com/email-accounts", method="GET"
    ).respond_with_json(
        {"success": False, "error": {"code": "NOT_FOUND", "message": "Domain not found"}},
        status=404,
    )
    result = runner.invoke(app, ["address", "list", "nosuch.com"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "mxctl: error: Domain not found (NOT_FOUND)" in result.stderr


def test_malformed_response_prints_nothing(api_env: HTTPServer) -> None:
    broken = account("box@domain.com")
    del broken["email"]
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([broken]))
    result = runner.invoke(app, ["address", "list", "domain.com"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "unexpected API response" in result.stderr


def test_missing_credentials(
    api_env: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MXCTL_API_KEY")
    result = runner.invoke(app, ["address", "list", "domain.com"])
    assert result.exit_code == 1
    assert "missing credentials" in result.stderr
    assert "MXCTL_API_KEY" in result.stderr
    assert len(api_env.log) == 0
