"""Configuration loading for mxctl.

Credentials come from $XDG_CONFIG_HOME/mxctl/config.toml (default
~/.config/mxctl/config.toml) and can be overridden per key with the
MXCTL_SERVER, MXCTL_USERNAME, MXCTL_API_KEY, and MXCTL_API_URL
environment variables.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_URL = "https://api.mxroute.com"

ENV_VARS = {
    "server": "MXCTL_SERVER",
    "username": "MXCTL_USERNAME",
    "api_key": "MXCTL_API_KEY",
    "api_url": "MXCTL_API_URL",
}

REQUIRED_KEYS = ("server", "username", "api_key")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    server: str
    username: str
    api_key: str
    api_url: str = DEFAULT_API_URL


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "")
    root = Path(base) if base else Path.home() / ".config"
    return root / "mxctl" / "config.toml"


def load_config() -> Config:
    path = config_path()
    values: dict[str, str] = {}
    if path.is_file():
        try:
            with path.open("rb") as fh:
                raw = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid config file {path}: {exc}") from exc
        for key in ENV_VARS:
            value = raw.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                raise ConfigError(f"config key '{key}' in {path} must be a string")
            values[key] = value
    for key, env in ENV_VARS.items():
        value = os.environ.get(env)
        if value:
            values[key] = value
    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        keys = ", ".join(missing)
        envs = ", ".join(ENV_VARS[key] for key in missing)
        raise ConfigError(f"missing credentials: {keys}. Set them in {path} or via {envs}")
    return Config(
        server=values["server"],
        username=values["username"],
        api_key=values["api_key"],
        api_url=values.get("api_url", DEFAULT_API_URL),
    )
