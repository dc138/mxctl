"""End to end tests: run mxctl as a subprocess against a mock API server.

The api_env fixture exports MXCTL_* variables into the test process
environment, which the subprocess inherits.
"""

import subprocess
import sys

from pytest_httpserver import HTTPServer

from .test_cli import account, forwarder, ok


def run_mxctl(
    *args: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mxctl", *args],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_help_runs() -> None:
    result = run_mxctl("--help")
    assert result.returncode == 0
    assert "Usage" in result.stdout


def test_address_list(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("b.a@domain.com"), account("a.a@domain.com")]))
    result = run_mxctl("address", "list", "domain.com")
    assert result.returncode == 0
    assert result.stdout == "a.a@domain.com\nb.a@domain.com\n"
    assert result.stderr == ""


def test_address_list_all_domains(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(
        ok(["example.com", "domain.com"])
    )
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("box@domain.com")]))
    api_env.expect_request(
        "/domains/example.com/email-accounts", method="GET"
    ).respond_with_json(ok([account("box@example.com")]))
    result = run_mxctl("address", "list")
    assert result.returncode == 0
    assert result.stdout == "box@domain.com\nbox@example.com\n"
    assert result.stderr == ""


def test_address_create_with_password_stdin(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts",
        method="POST",
        json={"username": "box", "password": "Secret123"},
    ).respond_with_json(ok({}), status=201)
    result = run_mxctl(
        "address", "create", "box@domain.com", "--password-stdin", input_text="Secret123\n"
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_address_delete_refuses_without_tty(api_env: HTTPServer) -> None:
    result = run_mxctl("address", "delete", "box@domain.com")
    assert result.returncode == 1
    assert "pass --yes" in result.stderr
    assert len(api_env.log) == 0


def test_address_delete_with_yes(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts/box", method="DELETE"
    ).respond_with_data(status=204)
    result = run_mxctl("address", "delete", "box@domain.com", "--yes")
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_forward_roundtrip(api_env: HTTPServer) -> None:
    api_env.expect_request("/domains", method="GET").respond_with_json(ok(["domain.com"]))
    api_env.expect_request(
        "/domains/domain.com/forwarders", method="GET"
    ).respond_with_json(ok([forwarder("info@domain.com", "me@other.com")]))
    api_env.expect_request(
        "/domains/domain.com/forwarders",
        method="POST",
        json={"alias": "sales", "destinations": ["team@other.com"]},
    ).respond_with_json(ok({}), status=201)

    created = run_mxctl("forward", "create", "sales@domain.com", "team@other.com")
    assert created.returncode == 0
    listed = run_mxctl("forward", "list")
    assert listed.returncode == 0
    assert listed.stdout == "info@domain.com -> me@other.com\n"


def test_wildcard_get_and_set(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/catch-all", method="GET"
    ).respond_with_json(ok({"type": "blackhole"}))
    api_env.expect_request(
        "/domains/domain.com/catch-all", method="PATCH", json={"type": "fail"}
    ).respond_with_json(ok({}))

    got = run_mxctl("wildcard", "get", "domain.com")
    assert got.returncode == 0
    assert got.stdout == "blackhole\n"
    updated = run_mxctl("-v", "wildcard", "set", "domain.com", "fail")
    assert updated.returncode == 0
    assert updated.stdout == ""
    assert "set catch-all for domain.com to fail" in updated.stderr


def test_api_error_exit_code(api_env: HTTPServer) -> None:
    api_env.expect_request(
        "/domains/domain.com/email-accounts", method="GET"
    ).respond_with_json(
        {"success": False, "error": {"code": "UNAUTHORIZED", "message": "Invalid key"}},
        status=401,
    )
    result = run_mxctl("address", "list", "domain.com")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Invalid key (UNAUTHORIZED)" in result.stderr
