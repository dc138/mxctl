# mxctl

A small command line tool for managing MXroute email hosting: mailbox addresses, forwarding rules, and catch-all (wildcard) policies.
It talks to the MXroute REST API at https://api.mxroute.com.

Because MXroute accounts can hold multiple domains, the domain to operate on is taken from the email address you pass on the command line.

> [!NOTE]
> This project has been developed with help from generative AI tools.
> Still, I'm confident enough to be using it for my own needs.
> If you encounter a bug, please file an issue or PR.
>
> **All contributor interactions (PR / issue description, comments, etc.) must be written by a human, not an LLM.
> AI generated code is allowed, as long as you understand it, take responsibility for it and can explain why its needed by yourself.
> Please do not file slop / low effort submissions.**

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

Credentials are read from `$XDG_CONFIG_HOME/mxctl/config.toml` (default `~/.config/mxctl/config.toml`):

```toml
server = "eagle.mxlogin.com"   # your mail server, shown on the API Keys page
username = "johndoe"           # your DirectAdmin username
api_key = "Mx..."              # your API key
# api_url = "https://api.mxroute.com"   # optional override
```

Each key can be overridden with an environment variable, which also allows running without a config file:

| Config key | Environment variable |
|------------|----------------------|
| `server`   | `MXCTL_SERVER`       |
| `username` | `MXCTL_USERNAME`     |
| `api_key`  | `MXCTL_API_KEY`      |
| `api_url`  | `MXCTL_API_URL`      |

## Usage

```
mxctl [--color {auto,always,never}] [--plain] [-v] <group> <command> [args]
```

Every option has a single-letter shorthand: `-c` (`--color`), `-p` (`--plain`), `-v` (`--verbose`), `-V` (`--version`), `-q` (`--quota`), `-l` (`--limit`), `-P` (`--password-stdin`), and `-y` (`--yes`).

Shell completion for bash, zsh, fish, and PowerShell is built in.
Run `mxctl --install-completion` once to install it for your shell, or print the script with `mxctl --show-completion` to install it manually.
The Arch package ships completions for bash and zsh, so no extra step is needed there.

### Addresses (mailboxes)

```sh
mxctl address list [domain]              # list addresses; all domains when omitted
mxctl address create <user>@<domain>     # create a mailbox
mxctl address delete <user>@<domain>     # delete a mailbox (asks first)
```

`list` prints the addresses under the given domain, or under every domain of the account when the domain is omitted.

`create` prompts twice for the mailbox password with hidden input.
For scripting, pass `--password-stdin` and pipe the password in:

```sh
printf '%s\n' "$PASSWORD" | mxctl address create box@example.com --password-stdin
```

Passwords must be at least 8 characters and contain an uppercase letter, a lowercase letter, and a digit.
`create` also accepts `--quota <MB>` (0 means unlimited) and `--limit <N>` (daily send limit); the server defaults are used when omitted.

`delete` destroys the mailbox and all mail stored in it.
It asks for confirmation on the terminal; in scripts (no terminal) it refuses to run unless you pass `--yes`.

### Forwarders

```sh
mxctl forward list [ends-with]                       # list forwarding rules
mxctl forward create <user1>@<domain1> <user2>@<domain2>
mxctl forward delete <user1>@<domain1>               # asks first
```

`list` prints every rule across all domains of the account as `source -> destination, destination`.
The optional `ends-with` argument keeps only rules whose source address ends with that string:

```sh
mxctl forward list @example.com   # all rules of example.com
mxctl forward list e.com          # all rules whose domain ends in e.com
mxctl forward list les@e.com      # matches sales@e.com, wholesales@e.com, ...
```

`create` accepts the special destinations `:blackhole:` (silently discard) and `:fail:` (reject) in place of a destination address.
Note that MXroute enables Expert Spam Filtering on a domain when you forward to Gmail, Yahoo, AOL, and similar providers.

`delete` removes the entire rule for the given source address, including all of its destinations, after confirmation (or with `--yes`).

### Catch-all (wildcard) policies

```sh
mxctl wildcard get [domain]         # print policy; without domain, all domains
mxctl wildcard set <domain> <policy>
```

A policy is one of:

- `fail`: reject mail to unknown addresses (the server default)
- `blackhole`: accept and silently discard it
- an email address: forward it there

`get` prints the policy in exactly the form `set` accepts, so the output can be fed back into `set`.
To clear a catch-all rule, set the policy to `fail`.

```sh
mxctl wildcard get                       # example.com fail
mxctl wildcard set example.com all@example.com
mxctl wildcard get example.com           # all@example.com
```

## Output behavior

- Successful operations print nothing.
  With `-v`/`--verbose`, a short note is printed to stderr (for example `created address box@example.com`).
- Listings print one entry per line to stdout and nothing else, so the output is easy to pipe.
- Listings pad email addresses with spaces so that the `@` signs line up vertically, which makes addresses with a common suffix easy to spot:

  ```
        box@example.com
  long.name@example.com
  ```

- With `--plain` (`-p`), listings are machine readable: colors are disabled (implies `--color=never`), no alignment padding is added, and forwarding rules are printed as `source: dest1, dest2, ...` instead of using the arrow.
  Prefer `--plain` when piping listings to other tools.
- Errors are printed to stderr as `mxctl: error: <message>` and the process exits with a non-zero status.

### Sorting

Listings are sorted lexicographically while respecting the domain hierarchy: the sort key is the address read right to left, one dot separated label at a time, with the domain labels first and then the local part labels.
The local part is treated as if it had the same dot separated hierarchy.
For example:

```
a.a@domain.com
b.a@domain.com
a.b@domain.com
a.a@example.com
a.a@domain.net
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0    | Success |
| 1    | Runtime error: API error, invalid response, missing credentials, or a declined confirmation |
| 2    | Usage error: unknown command, bad flag, or malformed argument |

## Development

```sh
uv sync              # create the virtualenv and install dependencies
uv run pytest        # unit, integration, and end to end tests (mock API)
uv run mypy src      # strict type checking
uv run ruff check    # linting
```

The test suite never talks to the real MXroute API: unit tests cover the sorting, config, and model validation logic, and integration plus end to end tests run the CLI against a local mock HTTP server (pytest-httpserver).

## License

```
mxctl, a small command line tool for managing MXroute email hosting.
Copyright (c) 2026 Antonio de Haro (dc138) <antonio@adaro.eu>

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the “Software”), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
