from inventory_agent.services.versioning import next_capability_version


def test_semantic_version_is_allocated_without_hardcoded_model_rules():
    assert next_capability_version("1.0.0", []) == "1.0.0"
    assert next_capability_version("2.0.0", ["1.4.2"]) == "2.0.0"
    assert next_capability_version("1.0.0", ["1.0.0", "1.0.2"]) == "1.0.3"
    assert next_capability_version("research", ["1.0.0"]) == "research"
