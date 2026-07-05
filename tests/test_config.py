from pathlib import Path

import pytest

from mxctl.config import DEFAULT_API_URL, ConfigError, config_path, load_config


def write_config(tmp_path: Path, content: str) -> None:
    directory = tmp_path / "mxctl"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.toml").write_text(content)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for env in ("MXCTL_SERVER", "MXCTL_USERNAME", "MXCTL_API_KEY", "MXCTL_API_URL"):
        monkeypatch.delenv(env, raising=False)


def test_config_path_respects_xdg(tmp_path: Path) -> None:
    assert config_path() == tmp_path / "mxctl" / "config.toml"


def test_load_from_file(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        'server = "eagle.mxlogin.com"\nusername = "johndoe"\napi_key = "Mxsecret"\n',
    )
    config = load_config()
    assert config.server == "eagle.mxlogin.com"
    assert config.username == "johndoe"
    assert config.api_key == "Mxsecret"
    assert config.api_url == DEFAULT_API_URL


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_config(
        tmp_path,
        'server = "eagle.mxlogin.com"\nusername = "johndoe"\napi_key = "Mxsecret"\n',
    )
    monkeypatch.setenv("MXCTL_API_KEY", "Mxoverride")
    monkeypatch.setenv("MXCTL_API_URL", "http://localhost:1234")
    config = load_config()
    assert config.api_key == "Mxoverride"
    assert config.api_url == "http://localhost:1234"
    assert config.server == "eagle.mxlogin.com"


def test_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MXCTL_SERVER", "eagle.mxlogin.com")
    monkeypatch.setenv("MXCTL_USERNAME", "johndoe")
    monkeypatch.setenv("MXCTL_API_KEY", "Mxsecret")
    config = load_config()
    assert config.username == "johndoe"


def test_missing_keys_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MXCTL_SERVER", "eagle.mxlogin.com")
    with pytest.raises(ConfigError, match="username, api_key"):
        load_config()
    with pytest.raises(ConfigError, match="MXCTL_USERNAME, MXCTL_API_KEY"):
        load_config()


def test_invalid_toml(tmp_path: Path) -> None:
    write_config(tmp_path, "server = \n")
    with pytest.raises(ConfigError, match="invalid config file"):
        load_config()


def test_non_string_value(tmp_path: Path) -> None:
    write_config(tmp_path, 'server = 5\nusername = "x"\napi_key = "y"\n')
    with pytest.raises(ConfigError, match="must be a string"):
        load_config()
