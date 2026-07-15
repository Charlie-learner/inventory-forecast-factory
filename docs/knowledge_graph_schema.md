# Capability knowledge graph schema

The graph captures reusable forecasting capabilities and validation experience. It is stored
as both JSON node-link data and GraphML so it can be inspected programmatically or opened in
Gephi and other graph tools.

## Node types

| Type | Purpose | Key properties |
|---|---|---|
| `Algorithm` | Executable forecast capability | name, description, min_history, dependencies |
| `DemandProfile` | Data condition suited to an algorithm | name |
| `Metric` | Validation or business objective | name |
| `ValidationRun` | Historical execution evidence | item_id, store_code, status, metrics, timestamp |
| `RepairStrategy` | Reusable response to a validation failure | description |

## Edge types

| Relation | From -> To | Meaning |
|---|---|---|
| `SUITABLE_FOR` | Algorithm -> DemandProfile | Applicability knowledge |
| `EVALUATED_BY` | Algorithm -> Metric | Required validation metric |
| `VALIDATED` | ValidationRun -> Algorithm | Model exercised by a run |
| `REPAIRED_BY` | ValidationRun -> RepairStrategy | Repair used before success |

Runtime validation runs are written under `artifacts/knowledge/`, which is ignored by Git.
The repository's `knowledge/base_capability_graph.*` files are deterministic bootstrap artifacts.

