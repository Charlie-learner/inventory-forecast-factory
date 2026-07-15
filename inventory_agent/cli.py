"""CLI for diagnostics, sample preparation, benchmarking, and Agent workflow execution."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from inventory_agent.config import Settings
from inventory_agent.data.costs import UNIT_COSTS, resolve_inventory_costs
from inventory_agent.data.loader import (
    CainiaoZipLoader,
    create_cainiao_loader,
    load_location_frame,
)
from inventory_agent.services.benchmark import benchmark_series
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow
from inventory_agent.validation.profiles import default_validation_profiles


def _doctor(settings: Settings) -> int:
    """Print a secret-safe environment diagnosis and return its exit code."""

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


def _prepare_sample(args: argparse.Namespace, settings: Settings) -> int:
    """Optionally extract a small demonstration sample from the raw Cainiao ZIP."""

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
    """Backtest candidate models for one item/location and save a JSON report."""

    source = Path(args.data)
    is_raw_source = source.is_dir() or source.suffix.lower() == ".zip"
    # Raw sources provide real A/B costs; standalone panel CSVs use neutral unit costs.
    if is_raw_source:
        frame = load_location_frame(source, args.store)
        costs = resolve_inventory_costs(
            create_cainiao_loader(source).load_costs(),
            args.item,
            args.store,
        )
    else:
        frame = pd.read_csv(source, parse_dates=["date"])
        costs = UNIT_COSTS
    report = benchmark_series(
        frame,
        item_id=args.item,
        store_code=args.store,
        model_names=args.models,
        horizon=args.horizon,
        folds=args.folds,
        costs=costs,
        allow_missing=is_raw_source,
        validation_profile=default_validation_profiles().get(args.task_type),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output.resolve()), **report}, ensure_ascii=False, indent=2))
    return 0


def _run_factory(args: argparse.Namespace, settings: Settings) -> int:
    """Run the complete natural-language Agent workflow and print its summary."""

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
                "target_inventory": result["benchmark"]["target_inventory"],
                "costs": result["benchmark"]["costs"],
                "reports": result["report_paths"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _visualize_graph(args: argparse.Namespace) -> int:
    """Render a saved knowledge graph as a standalone HTML visualization."""

    source = Path(args.knowledge)
    knowledge = (
        CapabilityKnowledgeGraph.load(source)
        if source.exists()
        else CapabilityKnowledgeGraph.bootstrap()
    )
    output = knowledge.render_html(args.output)
    print(json.dumps({"visualization": str(output.resolve())}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the root parser and all supported CLI subcommands."""

    parser = argparse.ArgumentParser(
        description="AI Agent Algorithm Capability Factory - Inventory Forecasting Scenario"
    )
    parser.add_argument("--verbose", action="store_true", help="Show workflow progress logs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local configuration without exposing secrets")

    prepare_sample = subparsers.add_parser(
        "prepare-sample",
        help="Optionally create a lightweight demonstration sample from the raw Cainiao ZIP",
    )
    prepare_sample.add_argument(
        "--zip-path", help="Path to CAINIAO Part II Data_20160509.zip"
    )
    prepare_sample.add_argument("--output", default="data/processed/cainiao_sample.csv")
    prepare_sample.add_argument("--items", type=int, default=20)

    benchmark = subparsers.add_parser("benchmark", help="Backtest models for one item/warehouse")
    benchmark.add_argument(
        "--data",
        default="data",
        help="Extracted Cainiao directory, original ZIP, or prepared panel CSV",
    )
    benchmark.add_argument("--item", type=int, required=True)
    benchmark.add_argument("--store", required=True)
    benchmark.add_argument("--models", nargs="+")
    benchmark.add_argument("--horizon", type=int, default=14)
    benchmark.add_argument(
        "--folds", type=int, help="Override the validation profile's fold count"
    )
    benchmark.add_argument(
        "--task-type",
        choices=default_validation_profiles().names(),
        default="inventory_target",
        help="Validation policy used to rank candidate models",
    )
    benchmark.add_argument("--output", default="artifacts/benchmark_report.json")

    run = subparsers.add_parser("run", help="Run the complete natural-language Agent workflow")
    run.add_argument("--description", required=True)
    run.add_argument(
        "--data",
        default="data",
        help="Extracted Cainiao directory, original ZIP, or prepared panel CSV",
    )
    run.add_argument("--output-root", default="artifacts/runs")

    visualize = subparsers.add_parser(
        "visualize-graph", help="Render the knowledge graph as standalone HTML"
    )
    visualize.add_argument(
        "--knowledge", default="knowledge/base_capability_graph.json"
    )
    visualize.add_argument(
        "--output", default="artifacts/knowledge/capability_graph.html"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, load settings, and dispatch the selected command."""

    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    if args.command == "doctor":
        return _doctor(settings)
    if args.command == "prepare-sample":
        return _prepare_sample(args, settings)
    if args.command == "benchmark":
        return _benchmark(args)
    if args.command == "run":
        return _run_factory(args, settings)
    if args.command == "visualize-graph":
        return _visualize_graph(args)
    raise SystemExit(f"Unknown command: {args.command}")
