"""Command line interface for mxctl.

Output contract: mutations print nothing on success unless --verbose is
given (verbose notes go to stderr). Errors are printed to stderr as
'mxctl: error: ...' and exit with status 1; usage errors exit with 2.
"""

from __future__ import annotations

import enum
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, NoReturn, TextIO

import typer

from . import __version__
from .api import ApiError, MxrouteClient
from .config import ConfigError, load_config
from .models import CatchAll
from .sorting import hierarchical_key

RESET = "\x1b[0m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
DIM = "\x1b[2m"


class ColorMode(enum.StrEnum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


@dataclass
class State:
    color_mode: ColorMode
    verbose: bool
    plain: bool

    def color_for(self, stream: TextIO) -> bool:
        if self.plain:
            return False
        if self.color_mode is ColorMode.ALWAYS:
            return True
        if self.color_mode is ColorMode.NEVER:
            return False
        return stream.isatty() and not os.environ.get("NO_COLOR")


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
    help="Manage MXroute email accounts, forwarders, and catch-all policies.",
)
address_app = typer.Typer(
    no_args_is_help=True, rich_markup_mode=None, help="Manage email accounts."
)
forward_app = typer.Typer(
    no_args_is_help=True, rich_markup_mode=None, help="Manage email forwarders."
)
wildcard_app = typer.Typer(
    no_args_is_help=True, rich_markup_mode=None, help="Manage catch-all policies."
)
app.add_typer(address_app, name="address")
app.add_typer(forward_app, name="forward")
app.add_typer(wildcard_app, name="wildcard")


def _version_callback(value: bool) -> None:
    if value:
        print(__version__)
        raise typer.Exit(0)


@app.callback()
def root(
    ctx: typer.Context,
    color: Annotated[
        ColorMode,
        typer.Option(
            "--color",
            help="Color output: auto (only on a terminal, honors NO_COLOR), always, or never.",
        ),
    ] = ColorMode.AUTO,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Print a note on stderr for successful operations."),
    ] = False,
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Machine readable listing output: no alignment padding, implies --color=never.",
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    ctx.obj = State(color_mode=color, verbose=verbose, plain=plain)


def get_state(ctx: typer.Context) -> State:
    state = ctx.find_object(State)
    assert state is not None
    return state


def paint(enabled: bool, code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if enabled else text


def format_address(
    enabled: bool, address: str, local_width: int = 0, domain_width: int = 0
) -> str:
    local, sep, domain = address.rpartition("@")
    if not sep:
        return paint(enabled, CYAN, address)
    lead = " " * (local_width - len(local))
    trail = " " * (domain_width - len(domain) - 1)
    return lead + local + paint(enabled, CYAN, "@" + domain) + trail


def address_widths(addresses: list[str]) -> tuple[int, int]:
    """Column widths (longest local part, longest '@domain') to align addresses on '@'."""
    parts = [address.rpartition("@") for address in addresses]
    local_width = max((len(local) for local, _, _ in parts), default=0)
    domain_width = max((len(domain) + 1 for _, _, domain in parts), default=0)
    return local_width, domain_width


def render_policy(enabled: bool, catchall: CatchAll, local_width: int = 0) -> str:
    if catchall.type == "fail":
        return paint(enabled, YELLOW, "fail")
    if catchall.type == "blackhole":
        return paint(enabled, RED, "blackhole")
    assert catchall.address is not None
    lead = " " * (local_width - len(catchall.address.rpartition("@")[0]))
    return lead + paint(enabled, GREEN, catchall.address)


def fail(state: State, message: str) -> NoReturn:
    prefix = paint(state.color_for(sys.stderr), RED, "mxctl: error:")
    print(f"{prefix} {message}", file=sys.stderr)
    raise typer.Exit(1)


def note(state: State, message: str) -> None:
    if state.verbose:
        print(message, file=sys.stderr)


def split_email(value: str) -> tuple[str, str]:
    local, sep, domain = value.partition("@")
    if not sep or not local or not domain or "@" in domain:
        raise typer.BadParameter(f"invalid email address: {value}")
    return local, domain


def stdin_is_interactive() -> bool:
    return sys.stdin.isatty()


def confirm_or_abort(state: State, prompt: str, yes: bool) -> None:
    if yes:
        return
    if not stdin_is_interactive():
        fail(state, "refusing to prompt for confirmation without a terminal; pass --yes")
    if not typer.confirm(prompt, default=False, err=True):
        print("aborted", file=sys.stderr)
        raise typer.Exit(1)


def read_password(state: State, password_stdin: bool) -> str:
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        if not stdin_is_interactive():
            fail(state, "no terminal for the password prompt; use --password-stdin")
        prompted: str = typer.prompt(
            "Password", hide_input=True, confirmation_prompt=True, err=True
        )
        password = prompted
    if (
        len(password) < 8
        or not re.search(r"[A-Z]", password)
        or not re.search(r"[a-z]", password)
        or not re.search(r"[0-9]", password)
    ):
        fail(
            state,
            "password must be at least 8 characters and contain an uppercase letter, "
            "a lowercase letter, and a digit",
        )
    return password


@contextmanager
def api_client(state: State) -> Iterator[MxrouteClient]:
    try:
        config = load_config()
    except ConfigError as exc:
        fail(state, str(exc))
    with MxrouteClient(config) as client:
        try:
            yield client
        except ApiError as exc:
            fail(state, str(exc))


@address_app.command("list")
def address_list(
    ctx: typer.Context,
    domain: Annotated[
        str,
        typer.Argument(
            metavar="[DOMAIN]",
            help="Domain whose addresses to list; all domains when omitted.",
        ),
    ] = "",
) -> None:
    """List email accounts under a domain, or under all domains."""
    state = get_state(ctx)
    with api_client(state) as client:
        if domain:
            accounts = client.list_accounts(domain)
        else:
            accounts = []
            for name in client.list_domains():
                accounts.extend(client.list_accounts(name))
    accounts.sort(key=lambda account: hierarchical_key(account.email))
    enabled = state.color_for(sys.stdout)
    local_width, domain_width = (
        (0, 0) if state.plain else address_widths([account.email for account in accounts])
    )
    for account in accounts:
        line = format_address(
            enabled, account.email, local_width, domain_width if state.verbose else 0
        )
        if state.verbose:
            extras = (
                f"quota={account.quota}MB usage={account.usage}MB "
                f"sent={account.sent}/{account.limit}"
            )
            if account.suspended:
                extras += " suspended"
            line = f"{line} {paint(enabled, DIM, extras)}"
        print(line)


@address_app.command("create")
def address_create(
    ctx: typer.Context,
    email: Annotated[str, typer.Argument(metavar="USER@DOMAIN")],
    quota: Annotated[
        int | None, typer.Option("--quota", help="Storage quota in MB (0 = unlimited).")
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Daily send limit.")] = None,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read the password from the first line of stdin."),
    ] = False,
) -> None:
    """Create an email account. Prompts for the password."""
    state = get_state(ctx)
    local, domain = split_email(email)
    password = read_password(state, password_stdin)
    with api_client(state) as client:
        client.create_account(domain, local, password, quota=quota, limit=limit)
    note(state, f"created address {email}")


@address_app.command("delete")
def address_delete(
    ctx: typer.Context,
    email: Annotated[str, typer.Argument(metavar="USER@DOMAIN")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")
    ] = False,
) -> None:
    """Delete an email account and all mail stored in it."""
    state = get_state(ctx)
    local, domain = split_email(email)
    confirm_or_abort(state, f"Delete address {email}? This destroys all stored mail.", yes)
    with api_client(state) as client:
        client.delete_account(domain, local)
    note(state, f"deleted address {email}")


@forward_app.command("list")
def forward_list(
    ctx: typer.Context,
    suffix: Annotated[
        str,
        typer.Argument(
            metavar="[ENDS-WITH]",
            help="Only show rules whose source address ends with this string.",
        ),
    ] = "",
) -> None:
    """List forwarding rules across all domains."""
    state = get_state(ctx)
    with api_client(state) as client:
        domains = client.list_domains()
        if "@" in suffix:
            domain_part = suffix.rpartition("@")[2]
            candidates = [name for name in domains if name == domain_part]
        else:
            candidates = [name for name in domains if name.endswith(suffix)]
        rules = []
        for name in candidates:
            rules.extend(client.list_forwarders(name))
    matching = [rule for rule in rules if rule.email.endswith(suffix)]
    matching.sort(key=lambda rule: hierarchical_key(rule.email))
    enabled = state.color_for(sys.stdout)
    arrow = paint(enabled, DIM, "->")
    local_width, domain_width = address_widths([rule.email for rule in matching])
    for rule in matching:
        destinations = ", ".join(sorted(rule.destinations, key=hierarchical_key))
        if state.plain:
            print(f"{rule.email}: {destinations}")
        else:
            source = format_address(enabled, rule.email, local_width, domain_width)
            print(f"{source} {arrow} {destinations}")


@forward_app.command("create")
def forward_create(
    ctx: typer.Context,
    source: Annotated[str, typer.Argument(metavar="USER@DOMAIN")],
    destination: Annotated[
        str,
        typer.Argument(
            metavar="DEST@DOMAIN",
            help="Destination address, or the specials :blackhole: and :fail:.",
        ),
    ],
) -> None:
    """Create a forwarding rule from source to destination."""
    state = get_state(ctx)
    local, domain = split_email(source)
    if destination not in (":blackhole:", ":fail:"):
        split_email(destination)
    with api_client(state) as client:
        client.create_forwarder(domain, local, [destination])
    note(state, f"created forwarder {source} -> {destination}")


@forward_app.command("delete")
def forward_delete(
    ctx: typer.Context,
    source: Annotated[str, typer.Argument(metavar="USER@DOMAIN")],
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")
    ] = False,
) -> None:
    """Delete a forwarding rule (the whole rule, with all destinations)."""
    state = get_state(ctx)
    local, domain = split_email(source)
    confirm_or_abort(
        state, f"Delete forwarder {source}? This removes the rule with all destinations.", yes
    )
    with api_client(state) as client:
        client.delete_forwarder(domain, local)
    note(state, f"deleted forwarder {source}")


@wildcard_app.command("get")
def wildcard_get(
    ctx: typer.Context,
    domain: Annotated[str, typer.Argument(metavar="[DOMAIN]")] = "",
) -> None:
    """Print the catch-all policy: fail, blackhole, or the forwarding address."""
    state = get_state(ctx)
    enabled = state.color_for(sys.stdout)
    with api_client(state) as client:
        if domain:
            catchall = client.get_catchall(domain)
            print(render_policy(enabled, catchall))
            if catchall.description:
                note(state, catchall.description)
        else:
            names = sorted(client.list_domains(), key=hierarchical_key)
            catchalls = [(name, client.get_catchall(name)) for name in names]
            domain_width = local_width = 0
            if not state.plain:
                domain_width = max((len(name) for name in names), default=0)
                local_width = max(
                    (
                        len(catchall.address.rpartition("@")[0])
                        for _, catchall in catchalls
                        if catchall.address is not None
                    ),
                    default=0,
                )
            for name, catchall in catchalls:
                padded = paint(enabled, CYAN, name) + " " * (domain_width - len(name))
                print(f"{padded} {render_policy(enabled, catchall, local_width)}")


@wildcard_app.command("set")
def wildcard_set(
    ctx: typer.Context,
    domain: Annotated[str, typer.Argument()],
    policy: Annotated[
        str, typer.Argument(help="One of 'fail', 'blackhole', or a destination email address.")
    ],
) -> None:
    """Set the catch-all policy for a domain. Use 'fail' to clear it."""
    state = get_state(ctx)
    if policy in ("fail", "blackhole"):
        type_, address = policy, None
    elif "@" in policy:
        split_email(policy)
        type_, address = "address", policy
    else:
        raise typer.BadParameter("policy must be 'fail', 'blackhole', or an email address")
    with api_client(state) as client:
        client.set_catchall(domain, type_, address)
    note(state, f"set catch-all for {domain} to {policy}")


def main() -> None:
    app()
