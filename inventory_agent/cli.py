"""Command-line interface for data preparation and environment diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from inventory_agent.config import Settings
from inventory_agent.data.loader import CainiaoZipLoader
from inventory_agent.services.benchmark import benchmark_series
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow


def _doctor(settings: Settings) -> int:
    report = {
        "llm_mode": settings.llm_mode,
        "model": settings.model,
        "base_url": settings.base_url,
        "api_key_configured": bool(settings.api_key),
        "cainiao_zip": str(settings.cainiao_zip_path) if settings.cainiao_zip_path else None,
        "issues": settings.validate(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["issues"] else 0


def _prepare(args: argparse.Namespace, settings: Settings) -> int:
    zip_path = Path(args.zip_path) if args.zip_path else settings.cainiao_zip_path
    if zip_path is None:
        raise SystemExit("Provide --zip-path or set CAINIAO_ZIP_PATH.")
    sample = CainiaoZipLoader(zip_path).prepare_sample(args.output, args.items)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "rows": len(sample),
                "items": int(sample["item_id"].nunique()),
                "stores": int(sample["store_code"].nunique()),
                "start": sample["date"].min().date().isoformat(),
                "end": sample["date"].max().date().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _benchmark(args: argparse.Namespace) -> int:
    frame = pd.read_csv(args.data, parse_dates=["date"])
    report = benchmark_series(
        frame,
        item_id=args.item,
        store_code=args.store,
        model_names=args.models,
        horizon=args.horizon,
        folds=args.folds,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output.resolve()), **report}, ensure_ascii=False, indent=2))
    return 0


def _run_factory(args: argparse.Namespace, settings: Settings) -> int:
    result = InventoryCapabilityWorkflow(settings=settings).run(
        args.description,
        args.data,
        args.output_root,
    )
    print(
        json.dumps(
            {
                "run_id": result["report"]["run_id"],
                "selected_model": result["selected_model"],
                "forecast_total": result["benchmark"]["forecast_total"],
                "reports": result["report_paths"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cainiao Inventory Forecast Capability Factory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local configuration without exposing secrets")

    prepare = subparsers.add_parser("prepare-data", help="Create a deterministic Cainiao sample")
    prepare.add_argument("--zip-path", help="Path to CAINIAO Part II Data_20160509.zip")
    prepare.add_argument("--output", default="data/processed/cainiao_sample.csv")
    prepare.add_argument("--items", type=int, default=20)

    benchmark = subparsers.add_parser("benchmark", help="Backtest models for one item/warehouse")
    benchmark.add_argument("--data", default="data/processed/cainiao_sample.csv")
    benchmark.add_argument("--item", type=int, required=True)
    benchmark.add_argument("--store", required=True)
    benchmark.add_argument("--models", nargs="+")
    benchmark.add_argument("--horizon", type=int, default=14)
    benchmark.add_argument("--folds", type=int, default=3)
    benchmark.add_argument("--output", default="artifacts/benchmark_report.json")

    run = subparsers.add_parser("run", help="Run the complete natural-language Agent workflow")
    run.add_argument("--description", required=True)
    run.add_argument("--data", default="data/processed/cainiao_sample.csv")
    run.add_argument("--output-root", default="artifacts/runs")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    if args.command == "doctor":
        return _doctor(settings)
    if args.command == "prepare-data":
        return _prepare(args, settings)
    if args.command == "benchmark":
        return _benchmark(args)
    if args.command == "run":
        return _run_factory(args, settings)
    raise SystemExit(f"Unknown command: {args.command}")
