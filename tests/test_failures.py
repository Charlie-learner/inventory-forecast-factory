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
