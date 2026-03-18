# Requirements: Cross-Cutting Context Loss Prevention

**Status:** Draft
**Date:** 2026-03-15
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline quality)
**Origin:** [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md)
**Companion:** [Service Interconnectedness Requirements](../SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md)
**Principle:** [Mottainai](~/Documents/dev/startd8-sdk/docs/design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) — every artifact produced by an earlier stage carries invested computation; discarding it is waste

---

## Problem Statement

End-to-end artifact inspection of Run 051 (17/17 PASS, $0.53) revealed that ContextCore's export pipeline produces metadata optimized for observability artifact generation but structurally inadequate for source-code generation projects. Two of 17 generated files consistently produce wrong proto import paths because the information — present in 5 locations in the pipeline — never reaches the generating LLM's prompt.

The root cause is not a single bug but a **class of context loss** spanning four areas:

1. **Domain mismatch:** ContextCore models observability artifacts (dashboards, SLOs, rules) but not source code structure (services, imports, RPCs). A 10-service microservice project is represented as a single target.

2. **Transport protocol misdetection:** `_derive_service_metadata_from_manifest()` infers `transport_protocol: "http"` from the artifact manifest. For gRPC-dominant projects, this is wrong — the plan document says gRPC, but the manifest only has observability artifacts.

3. **Onboarding metadata bloat:** 21 of 32 onboarding keys are observability-domain metadata irrelevant to source-code generation. No `project_type` discriminator suppresses them. Downstream receives ~200KB of noise alongside ~30KB of signal.

4. **Empty architectural context:** The `architectural_context` section (9 keys, 7 empty) and `_infer_dependencies()` stub in `graph/builder.py` are structurally present but data-absent — they were designed for a future that never arrived.

### Why this is a ContextCore concern

ContextCore's purpose is to make observability deterministic. Correct observability requires understanding service interconnectedness. A service serving ads is as important as the service submitting orders — equally important irrespective of revenue attribution. The service communication graph is a prerequisite for correct alert routing, SLO blast radius, and trace context propagation. That the same graph also fixes code generation context loss is a downstream benefit, not the primary motivation.

### Scope

This document covers ContextCore-owned fixes. Downstream fixes in startd8-sdk (context resolution, token budget floors) and cap-dev-pipe (plan ingestion EMIT phase enrichment) are tracked separately.

---

## Requirements

### Area 1: Service Communication Graph Extraction

> These requirements are elaborated in the companion [SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md](../SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md) (REQ-SIG-100 through REQ-SIG-301). Summarized here for completeness.

#### REQ-CCL-100: Service Name Extraction from Plan Text

`init_from_plan_ops.py` SHALL extract service names from plan/requirements text using structural signals (section headings, target file directories, explicit declarations).

**Acceptance:** Given a plan with `### F-002a: Email Service — gRPC Server` and target files under `src/emailservice/`, the system extracts `emailservice` as a service name.

#### REQ-CCL-101: Import Dependency Extraction from Plan Text

`init_from_plan_ops.py` SHALL extract per-service module imports from `Imports:` lists in implementation contracts.

**Acceptance:** Given plan text `Imports: demo_pb2, demo_pb2_grpc`, the system produces `{service: "emailservice", imports: ["demo_pb2", "demo_pb2_grpc"]}`.

#### REQ-CCL-102: RPC Dependency Extraction from Plan Text

`init_from_plan_ops.py` SHALL extract service-to-service RPC calls from `Calls` or `stub.Method()` patterns.

**Acceptance:** Given plan text `Calls product_catalog_stub.ListProducts(demo_pb2.Empty())`, the system produces `{caller: "recommendationservice", callee: "productcatalogservice", method: "ListProducts"}`.

#### REQ-CCL-103: Shared Module Detection

`init_from_plan_ops.py` SHALL identify modules shared across multiple services, including proto stubs listed in "Pre-Provided Artifacts" that appear in multiple service import lists.

**Acceptance:** `demo_pb2` appearing in both emailservice and recommendationservice import lists produces `{module: "demo_pb2", type: "proto_stub", used_by: ["emailservice", "recommendationservice"]}`.

#### REQ-CCL-104: Service Communication Graph in Onboarding Metadata

`build_onboarding_metadata()` SHALL include a `service_communication_graph` section containing services (with imports, rpc_calls, protocol), shared_modules, and proto_schemas.

**Acceptance:** The exported `onboarding-metadata.json` contains a `service_communication_graph` key with the structure defined in REQ-SIG-104.

---

### Area 2: Transport Protocol Detection from Plan Text

#### REQ-CCL-200: Plan-Aware Transport Protocol Inference

`_derive_service_metadata_from_manifest()` (or its replacement) SHALL infer `transport_protocol` from plan text signals when available, rather than solely from the artifact manifest.

Plan text signals for gRPC:
- `gRPC` in service description headings
- `proto` or `.proto` file references
- `_pb2` or `_pb2_grpc` in import lists
- `grpc_health_probe` in healthcheck references
- `stub.Method()` call patterns

**Current behavior:** Defaults to `http` because artifact manifest contains only observability artifacts.

**Required behavior:** If plan text contains gRPC signals for a service, set `transport_protocol: "grpc"` regardless of artifact manifest content.

**Acceptance:** For a project with `### F-002a: Email Service — gRPC Server` in the plan, `service_metadata["emailservice"].transport_protocol` is `"grpc"`, not `"http"`.

#### REQ-CCL-201: Transport Protocol Source Attribution

When `transport_protocol` is inferred from plan text (rather than artifact manifest), the inference record SHALL include `source: "plan:grpc_signal_detection"` with a confidence score of 0.85 or higher.

**Rationale:** Downstream consumers need to know whether transport protocol came from the manifest (artifact-level) or the plan (service-level) to assess reliability.

---

### Area 3: Generation Profiles (Output Scoping)

> **SUPERSEDED:** The original project type discriminator (REQ-CCL-300–302) has been replaced by **generation profiles** — see [REQ_GENERATION_PROFILES.md](REQ_GENERATION_PROFILES.md).
>
> The key distinction: project type classifies the *input* ("what kind of project is this?"), but the real need is to control the *output* ("what artifacts should this run produce?"). Context should always be rich; output should be selectively scoped.
>
> Generation profiles (`--profile source|observability|full`) solve the same problems — onboarding metadata bloat, domain mismatch, transport protocol misdetection — but with an explicit, user-controlled mechanism rather than implicit inference.
>
> Requirements REQ-GP-100 through REQ-GP-501 in the companion document cover:
> - Artifact manifest filtering by profile using existing `ArtifactType` frozen sets
> - Onboarding metadata scoping (source profile: <50KB vs ~200KB full)
> - Plan-text-based service metadata derivation under source profile
> - Profile sequencing (source first → observability enriched by prior source output)
> - Backward compatibility (default `full` profile = current behavior)

---

### Area 4: Knowledge Graph Integration

#### REQ-CCL-400: Implement `_infer_dependencies()` from Communication Graph

`graph/builder.py` `_infer_dependencies()` SHALL be implemented to populate the knowledge graph from `service_communication_graph` data when available.

**Current state:** Stub with `pass` (line 217).

**Required behavior:** When a `service_communication_graph` is available (from onboarding metadata or direct plan extraction), create edges in the knowledge graph:
- Service → Service edges from `rpc_calls`
- Service → Module edges from `imports`
- Module → Service edges from `shared_modules.used_by`

**Acceptance:** After processing a project with 3 services sharing `demo_pb2`, the knowledge graph contains 6 edges (3 service→module, 3 module→service) plus any RPC dependency edges.

#### REQ-CCL-401: Communication Graph Persistence to Tempo

The `service_communication_graph` SHALL be emittable as spans to Tempo for querying via TraceQL, consistent with ContextCore's "everything is a span" pattern.

Span structure:
```
span_name: "contextcore.service_dependency"
attributes:
  service.source: "emailservice"
  service.target: "productcatalogservice"
  dependency.type: "rpc"       # or "import", "shared_module"
  dependency.method: "ListProducts"  # for RPC type
  dependency.module: "demo_pb2"      # for import/shared_module type
```

**Rationale:** Enables TraceQL queries like `{ span.service.source = "emailservice" && span.dependency.type = "rpc" }` for blast radius analysis.

**Acceptance:** After export, `contextcore.service_dependency` spans are queryable in Tempo with correct attributes.

---

### Area 5: ServiceMetadataEntry Schema Extension

#### REQ-CCL-500: Add Import and RPC Fields to ServiceMetadataEntry

`models/service_metadata.py` `ServiceMetadataEntry` SHALL be extended with:

```python
imports: Optional[List[str]] = Field(
    None,
    description="Module imports for this service, extracted from plan text."
)
rpc_dependencies: Optional[List[RPCDependency]] = Field(
    None,
    description="Services this service calls via RPC."
)
exposes_rpcs: Optional[List[str]] = Field(
    None,
    description="RPC method names this service serves."
)
```

Where `RPCDependency` is:
```python
class RPCDependency(BaseModel):
    target_service: str
    method: str
    proto_module: Optional[str] = None
```

**Acceptance:** `ServiceMetadataEntry` validates with new fields. Existing entries without these fields remain valid (all new fields are Optional).

---

## Phasing

### Phase 1: Graph Extraction + Schema Extension (ContextCore-only)

| Requirement | File | Estimated Lines |
|-------------|------|----------------|
| REQ-CCL-100–103 | `init_from_plan_ops.py` | ~100 (regex extraction) |
| REQ-CCL-104 | `onboarding.py` | ~30 (wiring) |
| REQ-CCL-200–201 | `onboarding.py` or `init_from_plan_ops.py` | ~40 (plan-aware protocol detection) |
| REQ-CCL-500 | `models/service_metadata.py` | ~25 (schema extension) |

**Total:** ~195 lines. No new modules. No new dependencies.

### Phase 2: Project Type Discriminator

| Requirement | File | Estimated Lines |
|-------------|------|----------------|
| REQ-CCL-300 | `init_from_plan_ops.py` | ~30 (classification logic) |
| REQ-CCL-301 | `onboarding.py` | ~40 (conditional section emission) |
| REQ-CCL-302 | `onboarding.py` | ~5 (default fallback) |

**Total:** ~75 lines.

### Phase 3: Knowledge Graph + Observability

| Requirement | File | Estimated Lines |
|-------------|------|----------------|
| REQ-CCL-400 | `graph/builder.py` | ~50 (graph population) |
| REQ-CCL-401 | New: `graph/emitter.py` or extend `tracker.py` | ~40 (span emission) |

**Total:** ~90 lines.

---

## Success Criteria

1. **Proto import correctness:** PI-004 and PI-007 generate correct `import demo_pb2` / `import demo_pb2_grpc` when ContextCore onboarding metadata includes `service_communication_graph`
2. **Transport protocol accuracy:** gRPC-dominant projects produce `transport_protocol: "grpc"` for gRPC services
3. **Onboarding efficiency:** Source-code projects produce <50KB onboarding metadata (vs ~200KB current)
4. **Zero regression:** Projects without plan text or interconnectedness signals produce identical output to current behavior
5. **Observability benefit:** Service dependency spans queryable in Tempo for blast radius analysis

---

## Non-Goals

- Runtime trace-based dependency inference (requires deployed code)
- Source code AST analysis (would couple ContextCore to language-specific tooling)
- Full service mesh modeling (Kubernetes service discovery, ingress routing)
- Proto file parsing (derivable from plan text; proto parsing is a future enhancement)
- Fixing startd8-sdk `context_resolution.py` (downstream, tracked separately)
- Fixing cap-dev-pipe plan ingestion EMIT phase (downstream, tracked separately)

---

## Relationship to Existing Work

| Document | Relationship |
|----------|-------------|
| [Service Interconnectedness Requirements](../SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md) | Companion — elaborates REQ-SIG-100 through REQ-SIG-301 (graph extraction + downstream consumption) |
| [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | Origin — traces information loss end-to-end across ContextCore, cap-dev-pipe, and startd8-sdk |
| [Mottainai Design Principle](~/Documents/dev/startd8-sdk/docs/design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Gaps 10, 11 — onboarding metadata not injected, no architectural context for prime |
| [Knowledge Graph Builder](~/Documents/dev/ContextCore/src/contextcore/graph/builder.py) | `_infer_dependencies()` stub — REQ-CCL-400 implements this |
| [Plan-Target Coherence](REQ_PLAN_TARGET_COHERENCE.md) | Related pipeline integrity concern — validates plan-to-project alignment |
| [Kaizen Quality Phase Requirements](~/Documents/dev/startd8-sdk/docs/design/kaizen/KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md) | Kaizen data collection that surfaced the quality gap |
