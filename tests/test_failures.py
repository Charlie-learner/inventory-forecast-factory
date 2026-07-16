from inventory_agent.validation.failures import FailureAnalyzer


def test_failure_fingerprint_ignores_paths_and_run_specific_numbers():
    analyzer = FailureAnalyzer()
    first = analyzer.analyze(("syntax: F:\\runs\\one.py line 12",))
    second = analyzer.analyze(("syntax: C:\\temp\\two.py line 99",))

    assert first.category == "syntax"
    assert first.fingerprint == second.fingerprint
    assert "<path>.py" in first.normalized_error


def test_safety_failure_is_not_automatically_retryable():
    analysis = FailureAnalyzer().analyze(
        ("unsafe constructs: attribute call read_csv",),
        {"syntax": True, "imports": False},
    )

    assert analysis.category == "safety"
    assert not analysis.retryable
    assert analysis.severity == "critical"
    assert analysis.likely_stage == "security_validation"
    assert "危险调用" in analysis.root_cause
    assert "停止自动执行" in analysis.recommended_actions
