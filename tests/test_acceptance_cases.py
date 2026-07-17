from scripts.run_acceptance_cases import run_acceptance_cases


def test_submission_acceptance_cases_all_pass():
    result = run_acceptance_cases()

    assert result["summary"]["passed"] is True
    assert result["summary"]["benchmark_cases"] == 6
    assert result["summary"]["cross_component_cases"] == 4
    assert all(
        case["status"] == "passed"
        for case in result["benchmark_cases"]
    )
