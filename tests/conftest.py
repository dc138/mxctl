from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer

from mxctl.api import MxrouteClient
from mxctl.config import Config

TEST_SERVER = "test.mxlogin.com"
TEST_USERNAME = "tester"
TEST_API_KEY = "Mxtestkey"

AUTH_HEADERS = {
    "X-Server": TEST_SERVER,
    "X-Username": TEST_USERNAME,
    "X-API-Key": TEST_API_KEY,
}


@pytest.fixture
def config(httpserver: HTTPServer) -> Config:
    return Config(
        server=TEST_SERVER,
        username=TEST_USERNAME,
        api_key=TEST_API_KEY,
        api_url=httpserver.url_for(""),
    )


@pytest.fixture
def client(config: Config) -> Iterator[MxrouteClient]:
    with MxrouteClient(config) as instance:
        yield instance


@pytest.fixture
def api_env(
    httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> HTTPServer:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("MXCTL_SERVER", TEST_SERVER)
    monkeypatch.setenv("MXCTL_USERNAME", TEST_USERNAME)
    monkeypatch.setenv("MXCTL_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("MXCTL_API_URL", httpserver.url_for(""))
    monkeypatch.delenv("NO_COLOR", raising=False)
    return httpserver
