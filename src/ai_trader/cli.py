import argparse
import json
from datetime import date

from ai_trader.data.calendar import default_range
from ai_trader.data.pipeline import collect, replay, summary
from ai_trader.service import run_demo
from ai_trader.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Trader research tools")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the synthetic decision pipeline")
    demo.add_argument("--request-id", default="cli-demo-v1")
    commands.add_parser("doctor", help="check the installed research environment")
    data = commands.add_parser("data", help="collect, inspect and replay research data")
    actions = data.add_subparsers(dest="data_action", required=True)
    gather = actions.add_parser("collect")
    gather.add_argument("--start", type=date.fromisoformat)
    gather.add_argument("--end", type=date.fromisoformat)
    gather.add_argument("--symbols", nargs="+")
    gather.add_argument("--refresh", action="store_true")
    verify = actions.add_parser("replay")
    verify.add_argument("snapshot_id")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "data":
        try:
            if args.data_action == "replay":
                print(json.dumps(replay(settings, args.snapshot_id), indent=2))
            else:
                start, end = default_range()
                snapshot = collect(
                    settings,
                    args.start or start,
                    args.end or end,
                    tuple(args.symbols) if args.symbols else None,
                    refresh=args.refresh,
                )
                print(json.dumps(summary(snapshot), indent=2))
                if not snapshot.quality.research_approved:
                    raise SystemExit(2)
        except (ValueError, OSError) as error:
            parser.exit(1, f"Data operation failed: {type(error).__name__}\n")
    elif args.command == "demo":
        print(run_demo(args.request_id, settings).model_dump_json(indent=2))
    else:
        import duckdb
        import numpy as np
        import pandas as pd

        frame = pd.DataFrame({"return": np.array([0.01, -0.02, 0.03])})
        with duckdb.connect(":memory:") as connection:
            connection.register("sample_returns", frame)
            count = connection.execute("SELECT count(*) FROM sample_returns").fetchone()[0]
        if count != 3:
            raise RuntimeError("research dependency check failed")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "python_target": "3.12",
                    "research_rows_checked": count,
                    "execution_mode": settings.execution_mode,
                    "credentials_required": False,
                }
            )
        )
