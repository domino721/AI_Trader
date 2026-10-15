import argparse
import json

from ai_trader.service import run_demo
from ai_trader.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Trader offline research tools")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the synthetic decision pipeline")
    demo.add_argument("--request-id", default="cli-demo-v1")
    commands.add_parser("doctor", help="check the installed research environment")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "demo":
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
