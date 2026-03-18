# Service Interconnectedness Requirements

> **Date:** 2026-03-15
> **Status:** Draft
> **Origin:** [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md)
> **Principle:** ContextCore makes observability deterministic. Correct observability requires understanding service interconnectedness. That same interconnectedness graph enables downstream code generation quality.

---

## 1. Problem Statement

ContextCore models projects at the observability artifact level (dashboards, SLOs, prometheus rules) but not at the service communication level. A 10-service microservice project is represented as a single target. Services that communicate via shared proto contracts (`demo_pb2_grpc`) are invisible to the system.

This causes two classes of failures:

1. **Observability failures:** Alert routing, SLO blast radius, and trace context propagation cannot be derived correctly without knowing which services depend on which. An emailservice failure may cascade from a productcatalogservice failure — but ContextCore has no model of that dependency.

2. **Code generation failures:** When the pipeline generates source code (via startd8 Prime Contractor), tasks for dependent services (e.g., a gRPC test client) lack the import context of their dependencies (e.g., which proto module to import from). The LLM hallucinates import paths because the cross-service module relationship is not in the generation context. This is a direct consequence of ContextCore not modeling interconnectedness — the information exists in requirements/plan documents but is never extracted into a structured graph.

---

## 2. Design Principle

**Service interconnectedness is an observability concern, not a source-code concern.**

A service serving ads is as important as the service submitting orders — equally important irrespective of revenue attribution. Understanding the interconnected nature of services is essential for:

- **Blast radius modeling:** If service A depends on service B, B's degradation affects A's SLOs
- **Alert correlation:** Related service alerts should be grouped, not treated independently
- **Trace context propagation:** Services sharing proto contracts share trace boundaries
- **Dependency-aware generation:** Downstream code generation inherits correct import conventions from the interconnectedness graph

The graph should be derived from requirements documents and plan text — the same sources ContextCore already parses — not from runtime traces (which require deployed code that doesn't yet exist during generation).

---

## 3. Requirements

### Layer 1: Service Communication Graph Extraction

#### REQ-SIG-100: Extract Service Names from Plan Text

The INIT-FROM-PLAN stage (`init_from_plan_ops.py`) SHALL extract service names from plan/requirements documents using structural signals:

- Section headings containing "Service" (e.g., "### F-002a: Email Service — gRPC Server")
- Target file directory names (e.g., `src/emailservice/` → service "emailservice")
- Explicit service declarations in plan metadata

Output: `service_names: List[str]` in onboarding metadata.

#### REQ-SIG-101: Extract Import Dependencies from Plan Text

INIT-FROM-PLAN SHALL extract module import dependencies per service by parsing `Imports:` lists in implementation contracts:

```
Plan text: "Imports: `demo_pb2`, `demo_pb2_grpc`, `grpc_health.v1`"
Extracts: {service: "emailservice", imports: ["demo_pb2", "demo_pb2_grpc", "grpc_health.v1"]}
```

Parsing approach: regex on `Imports:` followed by backtick-delimited or comma-separated module names within the same feature/task section.

#### REQ-SIG-102: Extract RPC Dependencies from Plan Text

INIT-FROM-PLAN SHALL extract service-to-service RPC calls from plan text:

```
Plan text: "Calls `product_catalog_stub.ListProducts(demo_pb2.Empty())`"
Extracts: {caller: "recommendationservice", callee: "productcatalogservice", method: "ListProducts"}
```

Parsing approach: regex on `Calls` or `stub.Method()` patterns within feature/task sections.

#### REQ-SIG-103: Extract Shared Module Declarations

INIT-FROM-PLAN SHALL identify modules shared across services:

```
Plan text: "Shared JSON Logger Utility — emailservice" + "Shared JSON Logger Utility — recommendationservice"
Extracts: {module: "logger", shared_by: ["emailservice", "recommendationservice"]}
```

Also: proto files listed in "Pre-Provided Artifacts" that appear in multiple service import lists.

#### REQ-SIG-104: Produce `service_communication_graph` in Onboarding Metadata

`build_onboarding_metadata()` SHALL include a `service_communication_graph` section:

```json
{
  "service_communication_graph": {
    "services": {
      "emailservice": {
        "imports": ["demo_pb2", "demo_pb2_grpc", "logger", "jinja2"],
        "rpc_calls": [],
        "protocol": "grpc"
      },
      "recommendationservice": {
        "imports": ["demo_pb2", "demo_pb2_grpc", "logger"],
        "rpc_calls": [{"target": "productcatalogservice", "method": "ListProducts"}],
        "protocol": "grpc"
      }
    },
    "shared_modules": {
      "demo_pb2": {"type": "proto_stub", "used_by": ["emailservice", "recommendationservice"]},
      "demo_pb2_grpc": {"type": "proto_stub", "used_by": ["emailservice", "recommendationservice"]},
      "logger": {"type": "utility", "used_by": ["emailservice", "recommendationservice"]}
    },
    "proto_schemas": ["protos/demo.proto"]
  }
}
```

### Layer 2: Downstream Consumption

#### REQ-SIG-200: Plan Ingestion Reads `service_communication_graph`

Plan ingestion's EMIT phase SHALL read `service_communication_graph` from onboarding metadata and:

1. Populate `architectural_context.shared_modules` from `shared_modules`
2. Thread per-service `imports` into each task's context based on target file directory
3. Forward the graph into the seed for downstream consumers

#### REQ-SIG-201: Context Resolution Injects Dependency Imports

`PipelineContextStrategy.resolve_task_context()` SHALL, when a task has `depends_on` entries:

1. Look up dependency tasks' target file directories
2. Find matching services in `service_communication_graph`
3. Inject `imports` from those services as `inherited_imports` in gen_context

This is the essential fix for the proto import hallucination problem.

### Layer 3: Observability Benefits

#### REQ-SIG-300: Blast Radius Derivation from Communication Graph

The `service_communication_graph` SHALL be consumable by SLO definition and alert routing artifact generators. A service's SLO should account for its upstream dependencies' availability.

#### REQ-SIG-301: Alert Correlation Grouping

Services connected via RPC calls in the graph SHOULD be grouped for alert correlation. An emailservice alert concurrent with a productcatalogservice alert should be correlated.

---

## 4. Plan

### Phase 1: Graph Extraction (ContextCore) — IMPLEMENTED

> **Status:** IMPLEMENTED (2026-03-16, commit `da85e34`)
> **Actual scope:** ~150 lines of regex extraction + ~50 lines of onboarding/graph wiring + ~30 lines of service metadata schema + 27 tests

**Scope:** Add `service_communication_graph` extraction to INIT-FROM-PLAN.

**What was implemented:**

1. `init_from_plan_ops.py`: 7 regex patterns + `_extract_service_communication_graph()` function extracts service names, imports, RPC calls, shared modules, proto schemas from plan text (REQ-SIG-100–103). Wired into `infer_init_from_plan()`.

2. `onboarding.py`: `build_onboarding_metadata()` accepts and includes `service_communication_graph` in output (REQ-SIG-104). New `_derive_service_metadata_from_graph()` for source profile (REQ-GP-301).

3. `models/service_metadata.py`: Added `RPCDependency` model and optional `imports`, `rpc_dependencies`, `exposes_rpcs` fields to `ServiceMetadataEntry` (REQ-CCL-500).

4. `graph/schema.py`: Added `SERVICE`/`MODULE` node types, `IMPORTS`/`CALLS_RPC`/`SHARED_BY` edge types (REQ-CCL-400).

5. `graph/builder.py`: `populate_from_communication_graph()` creates nodes and edges from communication graph (REQ-CCL-400).

6. `graph/emitter.py`: `emit_service_dependency_spans()` emits OTel spans for service dependencies (REQ-CCL-401).

7. `manifest.py`: Export command reads `service_communication_graph` from loaded manifest and passes to onboarding builder.

### Phase 2: Downstream Consumption (startd8-sdk + cap-dev-pipe) — TODO

> **Status:** TODO — requirements documented in [SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md](~/Documents/dev/startd8-sdk/docs/design/kaizen/SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md)

**Scope:** Wire `service_communication_graph` through plan ingestion into gen_context.

**Implementation:**

1. Plan ingestion EMIT: read `service_communication_graph` from onboarding, populate `architectural_context.shared_modules`, thread per-task imports (REQ-SIG-200)

2. Context resolution: inject dependency imports from graph, register enrichment field (REQ-SIG-201)

3. Spec builder: include `inherited_imports` in LLM prompt (REQ-SIG-201 §4.3)

**Integration points:**
- `plan_ingestion_emitter.py` (seed construction)
- `context_strategy.py` `PipelineContextStrategy.resolve_context()`
- `spec_builder.py` (prompt construction)

**Estimated scope:** ~70 lines across 3 files

### Phase 3: Observability Derivation (Future)

**Scope:** Use `service_communication_graph` for blast radius and alert correlation.

**Implementation:** Extend artifact generators for SLO and notification policy artifacts to read the communication graph and derive cross-service dependencies.

**Estimated scope:** Not estimated — depends on artifact generator architecture.

---

## 5. Success Criteria

1. **Proto import correctness:** PI-004 and PI-007 consistently generate `import demo_pb2` / `import demo_pb2_grpc` instead of hallucinated module names
2. **Shared module visibility:** Every task knows what modules its sibling services import
3. **Zero manual enrichment:** The graph is derived automatically from plan text — no human annotation required
4. **Backward compatible:** Projects without interconnectedness signals in their plans produce an empty graph (no failure)

---

## 6. Non-Goals

- Runtime trace-based dependency inference (requires deployed code)
- Source code AST analysis (would couple ContextCore to language-specific tooling)
- Full service mesh modeling (Kubernetes service discovery, ingress routing)
- Proto file parsing (service definitions are derivable from plan text; proto parsing is a future enhancement)

---

## 7. Relationship to Existing Work

| Document | Relationship |
|----------|-------------|
| [Mottainai Design Principle](~/Documents/dev/startd8-sdk/docs/design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Gaps 10, 11 — onboarding metadata not injected, no architectural context for prime |
| [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | Primary investigation document — traces information loss end-to-end |
| [Knowledge Graph Builder](~/Documents/dev/ContextCore/src/contextcore/graph/builder.py) | `populate_from_communication_graph()` — Phase 1 implemented |
| [Kaizen Quality Phase Requirements](~/Documents/dev/startd8-sdk/docs/design/kaizen/KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md) | Kaizen data collection that surfaced the quality gap |
| [Service Communication Graph Consumption Requirements](~/Documents/dev/startd8-sdk/docs/design/kaizen/SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md) | Phase 2 downstream requirements (REQ-SIG-200, REQ-SIG-201) |
