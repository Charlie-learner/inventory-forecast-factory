import pytest

from inventory_agent.execution import RuntimeLimits, get_execution_profile


def test_runtime_limits_are_validated_and_injectable():
    limits = RuntimeLimits(
        max_http_body_bytes=2048,
        max_upload_file_bytes=1024,
        max_job_history=3,
        max_concurrent_jobs=2,
        default_keep_runs=4,
        archive_member_preview=5,
        identifier_preview=6,
    )

    assert limits.max_upload_file_bytes == 1024
    assert limits.max_concurrent_jobs == 2


def test_runtime_limits_reject_invalid_policies():
    with pytest.raises(ValueError, match="must be positive"):
        RuntimeLimits(max_job_history=0)
    with pytest.raises(ValueError, match="cannot exceed"):
        RuntimeLimits(max_http_body_bytes=10, max_upload_file_bytes=11)


def test_execution_profile_rejects_unknown_name():
    with pytest.raises(ValueError, match="execution_mode"):
        get_execution_profile("unknown")
