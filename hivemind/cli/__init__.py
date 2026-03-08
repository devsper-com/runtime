"""CLI: main entrypoint and subcommands init, doctor."""

from hivemind.cli.main import main
from hivemind.cli.init import run_doctor, run_init

__all__ = ["main", "run_init", "run_doctor"]
