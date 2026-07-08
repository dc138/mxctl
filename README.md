# mxctl

A small command line tool for managing MXroute email hosting: mailbox
addresses, forwarding rules, and catch-all (wildcard) policies. It talks to
the MXroute REST API at https://api.mxroute.com.

Because MXroute accounts can hold multiple domains, the domain to operate on
is taken from the email address you pass on the command line.

## Requirements

- Python 3.11 or newer
- An MXroute API key, created at https://panel.mxroute.com/api-keys.php

## Installation

With [uv](https://docs.astral.sh/uv/):

```sh
uv tool install .        # install the mxctl command for your user
# or, inside a checkout:
uv sync
uv run mxctl --help
```

## Configuration

Credentials are read from `$XDG_CONFIG_HOME/mxctl/config.toml` (default
`~/.config/mxctl/config.toml`):

```toml
server = "eagle.mxlogin.com"   # your mail server, shown on the API Keys page
username = "johndoe"           # your DirectAdmin username
api_key = "Mx..."              # your API key
# api_url = "https://api.mxroute.com"   # optional override
```

Each key can be overridden with an environment variable, which also allows
running without a config file:

| Config key | Environment variable |
|------------|----------------------|
| `server`   | `MXCTL_SERVER`       |
| `username` | `MXCTL_USERNAME`     |
| `api_key`  | `MXCTL_API_KEY`      |
| `api_url`  | `MXCTL_API_URL`      |

## Usage

```
mxctl [--color {auto,always,never}] [-v] <group> <command> [args]
```

### Addresses (mailboxes)

```sh
mxctl address list [domain]              # list addresses; all domains when omitted
mxctl address create <user>@<domain>     # create a mailbox
mxctl address delete <user>@<domain>     # delete a mailbox (asks first)
```

`list` prints the addresses under the given domain, or under every domain of
the account when the domain is omitted.

`create` prompts twice for the mailbox password with hidden input. For
scripting, pass `--password-stdin` and pipe the password in:

```sh
printf '%s\n' "$PASSWORD" | mxctl address create box@example.com --password-stdin
```

Passwords must be at least 8 characters and contain an uppercase letter, a
lowercase letter, and a digit. `create` also accepts `--quota <MB>` (0 means
unlimited) and `--limit <N>` (daily send limit); the server defaults are used
when omitted.

`delete` destroys the mailbox and all mail stored in it. It asks for
confirmation on the terminal; in scripts (no terminal) it refuses to run
unless you pass `--yes`.

### Forwarders

```sh
mxctl forward list [ends-with]                       # list forwarding rules
mxctl forward create <user1>@<domain1> <user2>@<domain2>
mxctl forward delete <user1>@<domain1>               # asks first
```

`list` prints every rule across all domains of the account as
`source -> destination, destination`. The optional `ends-with` argument
keeps only rules whose source address ends with that string:

```sh
mxctl forward list @example.com   # all rules of example.com
mxctl forward list e.com          # all rules whose domain ends in e.com
mxctl forward list les@e.com      # matches sales@e.com, wholesales@e.com, ...
```

`create` accepts the special destinations `:blackhole:` (silently discard)
and `:fail:` (reject) in place of a destination address. Note that MXroute
enables Expert Spam Filtering on a domain when you forward to Gmail, Yahoo,
AOL, and similar providers.

`delete` removes the entire rule for the given source address, including all
of its destinations, after confirmation (or with `--yes`).

### Catch-all (wildcard) policies

```sh
mxctl wildcard get [domain]         # print policy; without domain, all domains
mxctl wildcard set <domain> <policy>
```

A policy is one of:

- `fail`: reject mail to unknown addresses (the server default)
- `blackhole`: accept and silently discard it
- an email address: forward it there

`get` prints the policy in exactly the form `set` accepts, so the output can
be fed back into `set`. To clear a catch-all rule, set the policy to `fail`.

```sh
mxctl wildcard get                       # example.com fail
mxctl wildcard set example.com all@example.com
mxctl wildcard get example.com           # all@example.com
```

## Output behavior

- Successful operations print nothing. With `-v`/`--verbose`, a short note
  is printed to stderr (for example `created address box@example.com`).
- Listings print one entry per line to stdout and nothing else, so the
  output is easy to pipe.
- Listings pad email addresses with spaces so that the `@` signs line up
  vertically, which makes addresses with a common suffix easy to spot:

  ```
        box@example.com
  long.name@example.com
  ```
- Errors are printed to stderr as `mxctl: error: <message>` and the process
  exits with a non-zero status.

### Sorting

Listings are sorted lexicographically while respecting the domain hierarchy:
the sort key is the address read right to left, one dot separated label at a
time, with the domain labels first and then the local part labels. The local
part is treated as if it had the same dot separated hierarchy. For example:

```
a.a@domain.com
b.a@domain.com
a.b@domain.com
a.a@example.com
a.a@domain.net
```

### Colors

`--color` controls ANSI colors: `auto` (default) enables them only when the
output stream is a terminal and the `NO_COLOR` environment variable is not
set; `always` and `never` force them on or off.

### Exit codes

| Code | Meaning |
|------|---------|
| 0    | Success |
| 1    | Runtime error: API error, invalid response, missing credentials, or a declined confirmation |
| 2    | Usage error: unknown command, bad flag, or malformed argument |

## Safety

Deleting a mailbox erases all mail stored in it, so mxctl is deliberately
strict:

- Every API response is validated against the documented schema (pydantic
  models) before the tool acts on it or prints anything. Unexpected shapes
  abort with an error.
- Deletions are recognized as successful only by the exact expected HTTP
  status code.
- `address delete` and `forward delete` always ask for confirmation, and
  refuse to run non-interactively without an explicit `--yes`.

## Development

```sh
uv sync              # create the virtualenv and install dependencies
uv run pytest        # unit, integration, and end to end tests (mock API)
uv run mypy src      # strict type checking
uv run ruff check    # linting
```

The test suite never talks to the real MXroute API: unit tests cover the
sorting, config, and model validation logic, and integration plus end to end
tests run the CLI against a local mock HTTP server (pytest-httpserver).
