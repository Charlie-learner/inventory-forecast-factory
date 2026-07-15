# Capability knowledge graph schema

The graph captures reusable forecasting capabilities and validation experience. It is stored
as JSON node-link data, GraphML, and a standalone HTML/SVG visualization. JSON supports the
runtime, GraphML supports Gephi and other graph tools, and HTML can be opened directly without
an external JavaScript dependency.

## Node types

| Type | Purpose | Key properties |
|---|---|---|
| `Algorithm` | Executable forecast capability | name, description, min_history, dependencies, input_contract, output_contract, locations |
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
| `REPAIRED_BY` | ValidationRun -> RepairStrategy | Repair used before success or final failure |

Runtime validation runs are written under `artifacts/knowledge/`, which is ignored by Git.
The repository's `knowledge/base_capability_graph.*` files are deterministic bootstrap artifacts.

The `inventory_cost` metric node is scenario-specific knowledge for inventory forecasting. It
records the horizon-total formula and the semantic mapping `A=understock`, `B=overstock`.
`ValidationRun` and `RepairStrategy` nodes are runtime extensions; they are not present in a
freshly bootstrapped base graph. During retrieval, suitable algorithms remain the first filter;
within each suitability group, historical validation count, mean inventory cost, and success
rate provide reusable ranking evidence. Records without history remain available as fallbacks.

Schema version `1.1` adds history-aware retrieval and standalone HTML output. Generate a view
with:

```bash
python -m inventory_agent visualize-graph \
  --knowledge knowledge/base_capability_graph.json \
  --output artifacts/knowledge/capability_graph.html
```
