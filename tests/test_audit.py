import json
from pathlib import Path

from inventory_agent.cli import main
from inventory_agent.config import Settings
from inventory_agent.services.audit import (
    audit_as_markdown,
    audit_as_text,
    build_submission_audit,
)
from inventory_agent.web.app import WebApplication


ROOT = Path(__file__).resolve().parents[1]


def test_submission_audit_maps_required_items_to_existing_evidence():
    audit = build_submission_audit(ROOT)

    assert audit["summary"]["required_total"] >= 15
    assert audit["summary"]["missing"] == 0
    assert audit["summary"]["partial"] == 0
    assert audit["summary"]["completion_rate"] == 100.0
    assert {item["item_id"] for item in audit["items"]} >= {
        "core_closed_loop",
        "advanced_repair",
        "bonus_multi_agent",
        "boundary_sandbox",
    }
    assert all(
        (ROOT / evidence).exists()
        for item in audit["items"]
        if item["status"] == "passed"
        for evidence in item["evidence"]
    )


def test_audit_formats_are_plain_language_and_boundary_aware():
    audit = build_submission_audit(ROOT)
    text = audit_as_text(audit)
    markdown = audit_as_markdown(audit)

    assert "能力抽取 → 代码复刻" not in text
    assert "需求理解 → 能力抽取 → 方案规划 → 代码复刻" in text
    assert "证据：" in text
    assert "不纳入本次目标" in markdown
    assert "外部 API 是否验收取决于运行环境" in markdown
    assert "评分边界说明" in markdown


def test_cli_audit_writes_markdown_and_honors_strict_mode(
    tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("LLM_MODE", "mock")
    output = tmp_path / "evaluation_acceptance_matrix.md"

    assert (
        main(
            [
                "audit",
                "--format",
                "markdown",
                "--output",
                str(output),
                "--strict",
            ]
        )
        == 0
    )
    content = output.read_text(encoding="utf-8")
    assert "# 笔试要求评分验收中心" in content
    assert "必需项 **19/19** 已完成" in content


def test_web_application_exposes_the_same_audit_payload():
    application = WebApplication(workspace=ROOT, settings=Settings(llm_mode="mock"))

    payload = application.audit()

    assert payload["summary"] == build_submission_audit(ROOT)["summary"]
    assert json.dumps(payload, ensure_ascii=False)


def test_cli_audit_strict_mode_fails_when_repository_evidence_is_missing(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_MODE", "mock")

    assert main(["audit", "--strict"]) == 2
    output = capsys.readouterr().out
    assert "未完成" in output
