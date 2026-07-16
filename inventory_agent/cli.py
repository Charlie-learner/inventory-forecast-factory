"""CLI for diagnostics, sample preparation, benchmarking, and Agent workflow execution."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from inventory_agent.agents.extraction import CapabilityExtractionAgent
from inventory_agent.codegen.replication import CapabilityReplicator
from inventory_agent.config import Settings
from inventory_agent.data.costs import UNIT_COSTS, resolve_inventory_costs
from inventory_agent.data.loader import (
    CainiaoZipLoader,
    create_cainiao_loader,
    load_location_frame,
)
from inventory_agent.services.benchmark import benchmark_series
from inventory_agent.knowledge.graph import CapabilityKnowledgeGraph
from inventory_agent.llm.client import create_llm
from inventory_agent.plugins import load_plugins, plugin_manifest
from inventory_agent.workflow.factory import InventoryCapabilityWorkflow
from inventory_agent.validation.metrics import default_metric_registry
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

    metric_registry = default_metric_registry()
    validation_profiles = default_validation_profiles()
    loaded_plugins = load_plugins(
        args.plugin,
        metric_registry,
        validation_profiles,
    )
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
        validation_profile=validation_profiles.get(args.task_type),
        metric_registry=metric_registry,
    )
    report["plugins"] = plugin_manifest(loaded_plugins)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output.resolve()), **report}, ensure_ascii=False, indent=2))
    return 0


def _run_factory(args: argparse.Namespace, settings: Settings) -> int:
    """Run the complete natural-language Agent workflow and print its summary."""

    result = InventoryCapabilityWorkflow(
        settings=settings,
        plugin_specs=args.plugin,
    ).run(
        args.description,
        args.data,
        args.output_root,
        capability_sources=args.capability_source,
        trace_level=args.trace_level,
        keep_runs=args.keep_runs,
        task_type_override=args.task_type,
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
                "extracted_capabilities": result["report"]["capability_extraction"][
                    "count"
                ],
                "generation_mode": result["generated"].generation_mode,
                "candidate_code_solutions": len(
                    result.get("candidate_code_solutions", [])
                ),
                "detailed_trace": result.get("trace_paths"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _inspect_plugins(args: argparse.Namespace) -> int:
    """Load trusted plugins and print the resulting extension registry."""

    metric_registry = default_metric_registry()
    validation_profiles = default_validation_profiles()
    loaded = load_plugins(args.plugin, metric_registry, validation_profiles)
    print(
        json.dumps(
            {
                "loaded_plugins": plugin_manifest(loaded),
                "metrics": metric_registry.names(),
                "validation_profiles": validation_profiles.names(),
                "security_note": "Only load reviewed local Python plugins.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _serve_web(args: argparse.Namespace, settings: Settings) -> int:
    """Start the local Web dashboard and JSON API."""

    from inventory_agent.web import serve

    serve(
        host=args.host,
        port=args.port,
        open_browser=args.open_browser,
        output_root=args.output_root,
        knowledge_path=args.knowledge,
        settings=settings,
    )
    return 0


def _extract_capabilities(args: argparse.Namespace, settings: Settings) -> int:
    """Extract capability specs and optionally merge them into a knowledge graph."""

    agent = CapabilityExtractionAgent(create_llm(settings))
    capabilities = agent.extract_sources([Path(source) for source in args.source])
    output = agent.write_result(capabilities, args.output, agent.scan_reports)
    knowledge_paths = None
    if args.knowledge:
        knowledge_path = Path(args.knowledge)
        knowledge = (
            CapabilityKnowledgeGraph.load(knowledge_path)
            if knowledge_path.exists()
            else CapabilityKnowledgeGraph.bootstrap()
        )
        knowledge.ingest_capabilities(capabilities)
        graphml_path = knowledge_path.with_suffix(".graphml")
        html_path = knowledge_path.with_suffix(".html")
        knowledge.save(knowledge_path, graphml_path, html_path)
        knowledge_paths = {
            "json": str(knowledge_path.resolve()),
            "graphml": str(graphml_path.resolve()),
            "html": str(html_path.resolve()),
        }
    print(
        json.dumps(
            {
                "count": len(capabilities),
                "capabilities": [capability.capability_id for capability in capabilities],
                "scan_reports": agent.scan_reports,
                "result": str(output.resolve()),
                "knowledge_graph": knowledge_paths,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _replicate_capability(args: argparse.Namespace, settings: Settings) -> int:
    """Replicate one extracted capability and write its review manifest."""

    llm = create_llm(settings)
    agent = CapabilityExtractionAgent(llm)
    capabilities = agent.extract_sources([Path(source) for source in args.source])
    if args.capability:
        matches = [item for item in capabilities if item.name == args.capability]
        if len(matches) != 1:
            raise SystemExit(
                f"Expected one extracted capability named {args.capability!r}; "
                f"found {len(matches)}"
            )
        spec = matches[0]
    elif len(capabilities) == 1:
        spec = capabilities[0]
    else:
        names = ", ".join(capability.name for capability in capabilities)
        raise SystemExit(
            f"Source contains {len(capabilities)} capabilities ({names}); "
            "select one with --capability"
        )

    manifest = CapabilityReplicator().replicate(
        spec,
        args.output_dir,
        args.manifest,
        llm=llm,
        reference_model=args.reference_model,
        approved=args.approve,
    )
    print(
        json.dumps(
            {
                "capability": spec.capability_id,
                "generated": manifest["generation"]["path"],
                "generation_mode": manifest["generation"]["mode"],
                "valid": manifest["validation"]["valid"],
                "reference_model": manifest["reference_model"],
                "review": manifest["review"],
                "manifests": manifest["manifest_paths"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if manifest["validation"]["valid"] else 2


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


def _manage_versions(args: argparse.Namespace) -> int:
    """List, compare, promote, or roll back validated capability versions."""

    knowledge_path = Path(args.knowledge)
    if not knowledge_path.exists():
        raise SystemExit(f"Knowledge graph not found: {knowledge_path}")
    knowledge = CapabilityKnowledgeGraph.load(knowledge_path)
    if args.version_command == "list":
        payload = {
            "model": args.model,
            "versions": knowledge.capability_versions(args.model),
        }
    elif args.version_command == "compare":
        payload = knowledge.compare_versions(args.model, args.left, args.right)
    elif args.version_command in {"promote", "rollback"}:
        event = (
            knowledge.promote_version(args.model, args.version)
            if args.version_command == "promote"
            else knowledge.rollback_version(args.model, args.version)
        )
        knowledge.save(
            knowledge_path,
            knowledge_path.with_suffix(".graphml"),
            knowledge_path.with_suffix(".html"),
        )
        payload = {
            "action": args.version_command,
            "model": args.model,
            "selected": args.version,
            "event": event,
            "versions": knowledge.capability_versions(args.model),
        }
    else:  # pragma: no cover - argparse restricts this value.
        raise SystemExit(f"Unknown version command: {args.version_command}")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
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
        default="inventory_target",
        help="Built-in or plugin validation policy used to rank candidate models",
    )
    benchmark.add_argument(
        "--plugin",
        action="append",
        default=[],
        help="Trusted module:callable or path.py:callable registration plugin",
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
    run.add_argument(
        "--task-type",
        help="Override the validation profile inferred from the natural-language request",
    )
    run.add_argument(
        "--plugin",
        action="append",
        default=[],
        help="Trusted module:callable or path.py:callable registration plugin",
    )
    run.add_argument(
        "--trace-level",
        choices=["off", "basic", "full"],
        default="full",
        help="full also generates and validates code for every candidate",
    )
    run.add_argument(
        "--keep-runs",
        type=int,
        default=10,
        help="Keep only the newest N timestamped run directories",
    )
    run.add_argument(
        "--capability-source",
        action="append",
        default=[],
        help="Optional document, Python file, or local repository to extract before planning",
    )

    extract = subparsers.add_parser(
        "extract-capability",
        help="Extract source-traceable capability specifications",
    )
    extract.add_argument(
        "--source",
        nargs="+",
        required=True,
        help="Capability documents, Python files, or local repository directories",
    )
    extract.add_argument(
        "--output", default="artifacts/extraction/extracted_capabilities.json"
    )
    extract.add_argument(
        "--knowledge",
        help="Optional knowledge JSON path to update alongside GraphML and HTML",
    )

    replicate = subparsers.add_parser(
        "replicate-capability",
        help="Generate and validate one extracted capability with a review manifest",
    )
    replicate.add_argument(
        "--source",
        nargs="+",
        required=True,
        help="Capability file or local repository directory",
    )
    replicate.add_argument(
        "--capability",
        help="Capability name when the source contains more than one",
    )
    replicate.add_argument(
        "--reference-model",
        help="Optional registered model used for behavioral equivalence validation",
    )
    replicate.add_argument(
        "--output-dir", default="artifacts/replication/generated"
    )
    replicate.add_argument(
        "--manifest", default="artifacts/replication/review_manifest.json"
    )
    replicate.add_argument(
        "--approve",
        action="store_true",
        help="Record explicit human approval after automated checks pass",
    )

    versions = subparsers.add_parser(
        "versions",
        help="Inspect and manage validated capability versions",
    )
    version_commands = versions.add_subparsers(
        dest="version_command", required=True
    )
    version_list = version_commands.add_parser("list", help="List model versions")
    version_compare = version_commands.add_parser(
        "compare", help="Compare two model versions"
    )
    version_promote = version_commands.add_parser(
        "promote", help="Activate a validated model version"
    )
    version_rollback = version_commands.add_parser(
        "rollback", help="Restore a previously validated model version"
    )
    for command in [version_list, version_compare, version_promote, version_rollback]:
        command.add_argument(
            "--knowledge", default="artifacts/knowledge/capability_graph.json"
        )
        command.add_argument("--model", required=True)
    version_compare.add_argument("--left", required=True)
    version_compare.add_argument("--right", required=True)
    version_promote.add_argument("--version", required=True)
    version_rollback.add_argument("--version", required=True)

    visualize = subparsers.add_parser(
        "visualize-graph", help="Render the knowledge graph as standalone HTML"
    )
    visualize.add_argument(
        "--knowledge", default="knowledge/base_capability_graph.json"
    )
    visualize.add_argument(
        "--output", default="artifacts/knowledge/capability_graph.html"
    )

    plugins = subparsers.add_parser(
        "plugins",
        help="Inspect built-in and trusted local metric/validation plugins",
    )
    plugins.add_argument(
        "--plugin",
        action="append",
        default=[],
        help="Trusted module:callable or path.py:callable registration plugin",
    )

    web = subparsers.add_parser(
        "web",
        help="Start the local visual dashboard and JSON API",
    )
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    web.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the dashboard in the default browser after startup",
    )
    web.add_argument("--output-root", default="artifacts/runs")
    web.add_argument(
        "--knowledge",
        default="artifacts/knowledge/capability_graph.json",
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
    if args.command == "extract-capability":
        return _extract_capabilities(args, settings)
    if args.command == "replicate-capability":
        return _replicate_capability(args, settings)
    if args.command == "versions":
        return _manage_versions(args)
    if args.command == "visualize-graph":
        return _visualize_graph(args)
    if args.command == "plugins":
        return _inspect_plugins(args)
    if args.command == "web":
        return _serve_web(args, settings)
    raise SystemExit(f"Unknown command: {args.command}")
