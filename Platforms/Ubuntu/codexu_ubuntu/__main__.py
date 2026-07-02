from __future__ import annotations

import argparse
import json
import sys

from .models import snapshot_to_dict
from .reader import CodexUsageReader


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codexu-ubuntu",
        description="Native Ubuntu desktop widget for codexU usage.",
    )
    parser.add_argument(
        "--codex-home",
        help="Override CODEX_HOME for this run. Defaults to $CODEX_HOME or ~/.codex.",
    )
    parser.add_argument(
        "--no-app-server",
        action="store_true",
        help="Skip optional codex app-server JSON-RPC reads.",
    )
    parser.add_argument(
        "--dump-json",
        action="store_true",
        help="Print the current snapshot as JSON and exit without GTK.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run a data-path smoke check and exit without GTK.",
    )
    args = parser.parse_args(argv)

    if args.dump_json or args.check:
        reader = CodexUsageReader(
            args.codex_home,
            enable_app_server=not args.no_app_server,
        )
        snapshot = reader.load()
        if args.dump_json:
            print(
                json.dumps(
                    snapshot_to_dict(snapshot),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("codexU Ubuntu data check completed")
            for message in snapshot.messages:
                print(f"- {message}")
        return 0

    from .ui import CodexUApplication

    app = CodexUApplication(
        codex_home=args.codex_home,
        enable_app_server=not args.no_app_server,
    )
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    raise SystemExit(main())
