import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "gen_completions.py"

spec = importlib.util.spec_from_file_location("gen_completions", SCRIPT)
assert spec is not None and spec.loader is not None
gen = importlib.util.module_from_spec(spec)
sys.modules["gen_completions"] = gen
spec.loader.exec_module(gen)

CLI = gen.walk()
ZSH = gen.render_zsh(CLI)
BASH = gen.render_bash(CLI)


def test_walk_matches_known_tree():
    assert [group.name for group in CLI.groups] == ["address", "forward", "wildcard"]
    assert [cmd.name for cmd in CLI.groups[0].cmds] == ["list", "create", "delete"]


def test_every_command_and_option_is_rendered():
    for script in (ZSH, BASH):
        for opt in CLI.opts:
            assert all(name in script for name in opt.names)
        for group in CLI.groups:
            assert group.name in script
            for cmd in group.cmds:
                assert cmd.name in script
                for opt in cmd.opts:
                    assert all(name in script for name in opt.names)


def test_color_values_are_completed():
    assert "(auto always never)" in ZSH
    assert '"auto always never"' in BASH


def test_zsh_script_shape():
    # compinit only autoloads the file if #compdef is on the first line, and
    # the trailing call makes the first tab press complete
    assert ZSH.splitlines()[0] == "#compdef mxctl"
    assert ZSH.splitlines()[-1] == '_mxctl "$@"'


def test_bash_script_shape():
    assert BASH.splitlines()[-1] == "complete -F _mxctl mxctl"
