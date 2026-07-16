# Capability knowledge graph schema

The graph captures reusable forecasting capabilities and validation experience. It is stored
as JSON node-link data, GraphML, and a standalone HTML/SVG visualization. JSON supports the
runtime, GraphML supports Gephi and other graph tools, and HTML can be opened directly without
an external JavaScript dependency.

## Node types

| Type | Purpose | Key properties |
|---|---|---|
| `Algorithm` | Extracted and executable forecast capability | name, version, description, template_name, parameters, dependencies, input_contract, output_contract, source_ref, source_hash |
| `SourceArtifact` | Document, JSON, or Python origin | name, source_type, source_ref, source_hash, extracted_by |
| `CapabilityVersion` | Concrete generated implementation | capability_version, generation_mode, spec_hash, source_hash, generated_path, lifecycle_status |
| `DemandProfile` | Data condition suited to an algorithm | name |
| `Metric` | Validation or business objective | name |
| `ValidationRun` | Historical execution evidence | item_id, store_code, status, metrics, validation_checks, timestamp |
| `RepairStrategy` | Reusable response to a validation failure | description |
| `FailureCase` | Normalized cross-run failure experience | category, fingerprint, normalized_error, retryable, occurrence_count |
| `VersionEvent` | Auditable promotion or rollback action | action, model, previous_active, selected_version, timestamp |

## Edge types

| Relation | From -> To | Meaning |
|---|---|---|
| `SUITABLE_FOR` | Algorithm -> DemandProfile | Applicability knowledge |
| `EVALUATED_BY` | Algorithm -> Metric | Required validation metric |
| `EXTRACTED_FROM` | Algorithm -> SourceArtifact | Auditable source provenance |
| `VALIDATED` | ValidationRun -> Algorithm | Model exercised by a run |
| `VERSION_OF` | CapabilityVersion -> Algorithm | Generated source version of a capability |
| `VALIDATED_VERSION` | ValidationRun -> CapabilityVersion | Exact generated source checked by a run |
| `REPAIRED_BY` | ValidationRun -> RepairStrategy | Repair used before success or final failure |
| `OBSERVED_FAILURE` | ValidationRun -> FailureCase | Normalized failure observed in a run |
| `FAILURE_OF` | FailureCase -> Algorithm | Capability affected by the failure |
| `ADDRESSES` | RepairStrategy -> FailureCase | Strategy applied to a failure category |
| `ACTIVATED_VERSION` | VersionEvent -> CapabilityVersion | Version selected by promotion or rollback |

Runtime validation runs are written under `artifacts/knowledge/`, which is ignored by Git.
The repository's `knowledge/base_capability_graph.*` files are deterministic bootstrap artifacts.

The `inventory_cost` metric node is scenario-specific knowledge for inventory forecasting. It
records the horizon-total formula and the semantic mapping `A=understock`, `B=overstock`.
`ValidationRun` and `RepairStrategy` nodes are runtime extensions; they are not present in a
freshly bootstrapped base graph. During retrieval, suitable algorithms remain the first filter;
within each suitability group, historical validation count, mean inventory cost, and success
rate provide reusable ranking evidence. Records without history remain available as fallbacks.

Schema version `1.3` adds reusable failure cases and auditable version lifecycle events. Version
`1.2` added source provenance and content-addressed generated capability versions; version `1.1`
added history-aware retrieval and standalone HTML output. Generate a view
with:

```bash
python -m inventory_agent visualize-graph \
  --knowledge knowledge/base_capability_graph.json \
  --output artifacts/knowledge/capability_graph.html
```
