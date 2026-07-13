"""Generate static shell completion scripts for mxctl.

Usage: python scripts/gen_completions.py {zsh,bash}

Walks the typer command tree, so the emitted scripts always match the CLI
they were generated from. CLI shapes the emitters cannot render (nesting
deeper than two levels, unknown parameter kinds, multi-value options) raise
an error instead of producing incomplete completions.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import typer.main

from mxctl.cli import app

PROG = "mxctl"


@dataclass
class Opt:
    names: list[str]  # shortest first, e.g. ["-c", "--color"]
    help: str
    choices: list[str]  # empty when the value is free-form
    takes_value: bool


@dataclass
class Arg:
    metavar: str
    required: bool


@dataclass
class Cmd:
    name: str
    help: str
    opts: list[Opt]
    args: list[Arg]


@dataclass
class Group:
    name: str
    help: str
    cmds: list[Cmd]


@dataclass
class Cli:
    opts: list[Opt]
    groups: list[Group]


HELP_OPT = Opt(
    names=["--help"], help="Show this message and exit.", choices=[], takes_value=False
)


def first_line(text: str | None) -> str:
    stripped = (text or "").strip()
    return stripped.splitlines()[0] if stripped else ""


def walk_params(params: list[Any]) -> tuple[list[Opt], list[Arg]]:
    opts: list[Opt] = []
    args: list[Arg] = []
    for param in params:
        kind = param.param_type_name
        if kind == "option":
            if param.hidden:
                continue
            if param.nargs != 1 or param.count:
                raise ValueError(f"cannot render option {param.name}")
            names = sorted(param.opts + param.secondary_opts, key=len)
            choices = list(getattr(param.type, "choices", []))
            opts.append(Opt(names, first_line(param.help), choices, not param.is_flag))
        elif kind == "argument":
            if param.nargs != 1:
                raise ValueError(f"cannot render argument {param.name}")
            metavar = (param.metavar or param.name or "ARG").strip("[]").upper()
            args.append(Arg(metavar, param.required))
        else:
            raise ValueError(f"unknown parameter kind {kind}")
    return opts + [HELP_OPT], args


def walk() -> Cli:
    root = typer.main.get_command(app)
    if not hasattr(root, "commands"):
        raise ValueError("root command is not a group")
    root_opts, root_args = walk_params(root.params)
    if root_args:
        raise ValueError("root arguments are not supported")
    groups = []
    for group_name, group in root.commands.items():
        if not hasattr(group, "commands"):
            raise ValueError(f"top level command {group_name} is not a group")
        group_opts, group_args = walk_params(group.params)
        if group_args or any(opt.names != ["--help"] for opt in group_opts):
            raise ValueError(f"group level parameters on {group_name} are not supported")
        cmds = []
        for cmd_name, cmd in group.commands.items():
            if hasattr(cmd, "commands"):
                raise ValueError(f"{group_name} {cmd_name}: nesting deeper than two levels")
            cmd_opts, cmd_args = walk_params(cmd.params)
            cmds.append(Cmd(cmd_name, first_line(cmd.help), cmd_opts, cmd_args))
        groups.append(Group(group_name, first_line(group.help), cmds))
    return Cli(root_opts, groups)


def value_options(cli: Cli) -> list[Opt]:
    """All value-taking options, checked for conflicting meanings across commands."""
    by_name: dict[str, Opt] = {}
    all_opts = list(cli.opts)
    for group in cli.groups:
        for cmd in group.cmds:
            all_opts.extend(cmd.opts)
    result = []
    for opt in all_opts:
        if not opt.takes_value:
            continue
        known = by_name.get(opt.names[-1])
        if known is None:
            by_name[opt.names[-1]] = opt
            result.append(opt)
        elif known.choices != opt.choices:
            raise ValueError(f"option {opt.names[-1]} has conflicting values across commands")
    return result


def zsh_quote(text: str) -> str:
    """Escape for use inside a single-quoted _arguments spec or _describe entry."""
    text = text.replace("'", "'\\''")
    for char in "[]:":
        text = text.replace(char, "\\" + char)
    return text


def zsh_opt_spec(opt: Opt) -> str:
    value = ""
    if opt.takes_value:
        choices = f"({' '.join(opt.choices)})" if opt.choices else ""
        value = f":{opt.names[-1].lstrip('-')}:{choices}"
    body = f"[{zsh_quote(opt.help)}]{value}"
    if len(opt.names) == 1:
        return f"'{opt.names[0]}{body}'"
    exclusion = " ".join(opt.names)
    braces = ",".join(opt.names)
    return f"'({exclusion})'{{{braces}}}'{body}'"


def render_zsh(cli: Cli) -> str:
    lines = [f"#compdef {PROG}", ""]
    for group in cli.groups:
        lines += [
            f"_{PROG}_{group.name}() {{",
            "  integer ret=1",
            '  local curcontext="$curcontext" state line',
            "  _arguments -C \\",
            f"    {zsh_opt_spec(HELP_OPT)} \\",
            "    '1: :->cmd' \\",
            "    '*::arg:->args' && ret=0",
            "  case $state in",
            "    (cmd)",
            "      local -a cmds=(",
        ]
        lines += [f"        '{cmd.name}:{zsh_quote(cmd.help)}'" for cmd in group.cmds]
        lines += [
            "      )",
            f"      _describe -t commands '{PROG} {group.name} command' cmds && ret=0",
            "      ;;",
            "    (args)",
            "      case $line[1] in",
        ]
        for cmd in group.cmds:
            lines += [f"        ({cmd.name})", "          _arguments \\"]
            specs = [zsh_opt_spec(opt) for opt in cmd.opts]
            for position, arg in enumerate(cmd.args, start=1):
                optional = "" if arg.required else ":"
                specs.append(f"'{position}:{optional}{zsh_quote(arg.metavar)}:'")
            lines += [f"            {spec} \\" for spec in specs[:-1]]
            lines += [f"            {specs[-1]} && ret=0", "          ;;"]
        lines += ["      esac", "      ;;", "  esac", "  return ret", "}", ""]
    lines += [
        f"_{PROG}() {{",
        "  integer ret=1",
        '  local curcontext="$curcontext" state line',
        "  _arguments -C \\",
    ]
    lines += [f"    {zsh_opt_spec(opt)} \\" for opt in cli.opts]
    lines += [
        "    '1: :->group' \\",
        "    '*::arg:->args' && ret=0",
        "  case $state in",
        "    (group)",
        "      local -a groups=(",
    ]
    lines += [f"        '{group.name}:{zsh_quote(group.help)}'" for group in cli.groups]
    lines += [
        "      )",
        f"      _describe -t commands '{PROG} command' groups && ret=0",
        "      ;;",
        "    (args)",
        "      case $line[1] in",
    ]
    lines += [
        f"        ({group.name}) _{PROG}_{group.name} && ret=0 ;;" for group in cli.groups
    ]
    lines += ["      esac", "      ;;", "  esac", "  return ret", "}", ""]
    lines += [f'_{PROG} "$@"']
    return "\n".join(lines)


def render_bash(cli: Cli) -> str:
    def words(opts: list[Opt], extra: list[str] | None = None) -> str:
        return " ".join((extra or []) + [name for opt in opts for name in opt.names])

    value_opt_names = " ".join(name for opt in value_options(cli) for name in opt.names)
    lines = [
        f"# bash completion for {PROG}, generated by scripts/gen_completions.py",
        f"_{PROG}() {{",
        '    local cur=${COMP_WORDS[COMP_CWORD]} prev="" group="" cmd="" w p i',
        f'    local valueopts=" {value_opt_names} "',
        "    (( COMP_CWORD > 0 )) && prev=${COMP_WORDS[COMP_CWORD-1]}",
        "    if [[ $prev == = ]] && (( COMP_CWORD >= 2 )); then",
        "        prev=${COMP_WORDS[COMP_CWORD-2]}",
        "    fi",
        "    for (( i=1; i < COMP_CWORD; i++ )); do",
        "        w=${COMP_WORDS[i]}",
        '        [[ $w == -* || $w == = ]] && continue',
        "        p=${COMP_WORDS[i-1]}",
        '        [[ $p == = ]] && (( i >= 2 )) && p=${COMP_WORDS[i-2]}',
        '        [[ $valueopts == *" $p "* ]] && continue',
        '        if [[ -z $group ]]; then group=$w',
        '        elif [[ -z $cmd ]]; then cmd=$w',
        "        fi",
        "    done",
        '    local words=""',
        "    case $prev in",
    ]
    for opt in value_options(cli):
        pattern = "|".join(opt.names)
        if opt.choices:
            reply = f'COMPREPLY=( $(compgen -W "{" ".join(opt.choices)}" -- "$cur") )'
            lines.append(f"        {pattern}) {reply}; return ;;")
        else:
            lines.append(f"        {pattern}) return ;;")
    lines += [
        "    esac",
        "    if [[ -z $group ]]; then",
        f'        words="{words(cli.opts, [group.name for group in cli.groups])}"',
        "    elif [[ -z $cmd ]]; then",
        "        case $group in",
    ]
    for group in cli.groups:
        cmd_names = [cmd.name for cmd in group.cmds]
        lines.append(f'            {group.name}) words="{" ".join(cmd_names)} --help" ;;')
    lines += [
        "        esac",
        "    else",
        '        case "$group $cmd" in',
    ]
    for group in cli.groups:
        for cmd in group.cmds:
            lines.append(f'            "{group.name} {cmd.name}") words="{words(cmd.opts)}" ;;')
    lines += [
        "        esac",
        "    fi",
        '    COMPREPLY=( $(compgen -W "$words" -- "$cur") )',
        "}",
        f"complete -F _{PROG} {PROG}",
    ]
    return "\n".join(lines)


def main() -> None:
    renderers = {"zsh": render_zsh, "bash": render_bash}
    if len(sys.argv) != 2 or sys.argv[1] not in renderers:
        print("usage: gen_completions.py {zsh,bash}", file=sys.stderr)
        raise SystemExit(2)
    print(renderers[sys.argv[1]](walk()))


if __name__ == "__main__":
    main()
