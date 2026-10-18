import argparse
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ai_trader.data.calendar import default_range
from ai_trader.data.pipeline import collect, replay, summary
from ai_trader.knowledge.catalog import check_catalog, load_catalog
from ai_trader.knowledge.index import (
    build_knowledge_snapshot,
    evaluate_knowledge_benchmark,
    load_evaluation_benchmark,
    load_knowledge_snapshot,
    replay_knowledge_snapshot,
    search_knowledge,
)
from ai_trader.service import run_demo
from ai_trader.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Trader research tools")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the synthetic decision pipeline")
    demo.add_argument("--request-id", default="cli-demo-v1")
    commands.add_parser("doctor", help="check the installed research environment")
    model_smoke = commands.add_parser("llm-smoke", help="test offline fixture invocation only")
    model_smoke.add_argument("--request-id", default="offline-smoke-v1")
    data = commands.add_parser("data", help="collect, inspect and replay research data")
    actions = data.add_subparsers(dest="data_action", required=True)
    gather = actions.add_parser("collect")
    gather.add_argument("--start", type=date.fromisoformat)
    gather.add_argument("--end", type=date.fromisoformat)
    gather.add_argument("--symbols", nargs="+")
    gather.add_argument("--refresh", action="store_true")
    verify = actions.add_parser("replay")
    verify.add_argument("snapshot_id")
    knowledge = commands.add_parser("knowledge", help="verify, index, replay and search knowledge")
    knowledge.add_argument("--catalog", type=Path)
    knowledge.add_argument("--root", type=Path, default=Path("."))
    knowledge.add_argument("--as-of", type=datetime.fromisoformat)
    knowledge.add_argument(
        "--purpose", choices=("local_storage", "indexing", "model_context"), default="indexing"
    )
    knowledge.add_argument("--build-snapshot", action="store_true")
    knowledge.add_argument("--replay-snapshot")
    knowledge.add_argument("--snapshot-id")
    knowledge.add_argument("--query")
    knowledge.add_argument("--top-k", type=int, default=5)
    knowledge.add_argument("--evaluate-benchmark", type=Path)
    args = parser.parse_args()
    if args.command == "llm-smoke":
        from ai_trader.llm.fixture import fixture_request
        from ai_trader.llm.models import InvocationPolicy
        from ai_trader.llm.provider import FixtureProvider
        from ai_trader.llm.runtime import invoke

        try:
            policy = InvocationPolicy(
                enabled=True,
                monthly_call_limit=3,
                monthly_reservation_limit_usd=Decimal("0.03"),
                attempt_reservation_usd=Decimal("0.01"),
            )
            result = invoke(
                fixture_request(args.request_id), policy, FixtureProvider(), Settings().state_dir
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            parser.exit(1, f"Offline model operation failed: {type(error).__name__}\n")
        print(json.dumps(result.summary(), indent=2))
        if result.status != "completed":
            raise SystemExit(2)
        return
    if args.command == "knowledge":
        settings = Settings()
        try:
            if args.evaluate_benchmark is not None:
                bench = load_evaluation_benchmark(args.evaluate_benchmark)
                if args.snapshot_id:
                    snap = load_knowledge_snapshot(settings.state_dir, args.snapshot_id)
                else:
                    cat_path = args.catalog or (args.root / Path(bench.catalog_path))
                    snap = build_knowledge_snapshot(
                        load_catalog(cat_path), args.root, settings.state_dir
                    )
                eval_report = evaluate_knowledge_benchmark(bench, snap)
                print(eval_report.model_dump_json(indent=2))
                if eval_report.status != "passed":
                    raise SystemExit(2)
                return
            if args.replay_snapshot:
                result = replay_knowledge_snapshot(
                    settings.state_dir, args.replay_snapshot, args.root
                )
                print(json.dumps(result, indent=2))
                if result["integrity"] != "passed":
                    raise SystemExit(2)
                return
            if args.build_snapshot:
                if args.catalog is None:
                    raise ValueError("catalog is required for snapshot build")
                snap = build_knowledge_snapshot(
                    load_catalog(args.catalog), args.root, settings.state_dir
                )
                print(
                    json.dumps(
                        {
                            "snapshot_id": snap.snapshot_id,
                            "catalog_sha256": snap.catalog_sha256,
                            "documents": len(snap.documents),
                            "chunks": len(snap.chunks),
                            "untrusted_data_only": snap.untrusted_data_only,
                            "historical_backtest_approved": snap.historical_backtest_approved,
                            "trading_approved": snap.trading_approved,
                        },
                        indent=2,
                    )
                )
                return
            if args.query is not None:
                if args.as_of is None:
                    raise ValueError("as-of is required for knowledge search")
                if args.snapshot_id:
                    snap = load_knowledge_snapshot(settings.state_dir, args.snapshot_id)
                elif args.catalog:
                    snap = build_knowledge_snapshot(
                        load_catalog(args.catalog), args.root, settings.state_dir
                    )
                else:
                    raise ValueError("snapshot-id or catalog is required for search")
                report = search_knowledge(
                    snap,
                    args.query,
                    args.as_of,
                    purpose=args.purpose,
                    top_k=args.top_k,
                )
                print(report.model_dump_json(indent=2))
                return
            if args.catalog is None or args.as_of is None:
                raise ValueError("catalog and as-of are required for verification")
            result = check_catalog(load_catalog(args.catalog), args.root, args.as_of, args.purpose)
        except (OSError, ValueError) as error:
            parser.exit(1, f"Knowledge operation failed: {type(error).__name__}\n")
        print(json.dumps(result, indent=2))
        if result["status"] != "passed":
            raise SystemExit(2)
        return
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
