import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="devsper",
        description="Devsper — self-evolving AI workflow engine",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a .devsper workflow")
    run_p.add_argument("spec", help="Path to .devsper file")
    run_p.add_argument(
        "--input",
        metavar="KEY=VALUE",
        action="append",
        default=[],
        dest="inputs",
        help="Workflow input (repeatable)",
    )

    args = parser.parse_args()

    if args.command == "run":
        inputs: dict[str, str] = {}
        for kv in args.inputs:
            if "=" not in kv:
                print(f"error: expected KEY=VALUE, got '{kv}'", file=sys.stderr)
                sys.exit(1)
            k, v = kv.split("=", 1)
            inputs[k] = v

        from devsper._core import run as _run

        results = _run(args.spec, inputs or None)
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
