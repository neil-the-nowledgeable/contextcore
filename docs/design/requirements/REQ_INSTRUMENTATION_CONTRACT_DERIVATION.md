# Requirements: Instrumentation Contract Derivation — ContextCore

> **Status:** Implemented (2026-03-18)
> **Date:** 2026-03-18
> **Author:** Observability Team
> **Priority Tier:** Tier 1
> **Scope:** ContextCore EXPORT stage (Stage 4) — derive instrumentation hints from observability artifacts and service communication graph for downstream code generation
> **Predecessor:** [TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md](~/Documents/dev/startd8-sdk/docs/design/prime/TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md) (REQ-TCW-000–003, cross-system)
> **Depends on:** Service communication graph extraction (REQ-SIG-100–104, implemented), Generation profiles (REQ-GP-100–501, implemented)
> **Consumed by:** startd8-sdk TODO Scanner (REQ-TCW-100–103), Completion Planner (REQ-TCW-200–203)
> **Implementation plan:** [INSTRUMENTATION_CONTRACT_DERIVATION_PLAN.md](../../plans/INSTRUMENTATION_CONTRACT_DERIVATION_PLAN.md)
> **Revision notes:** Revised after creating the implementation plan — see Section 8 for findings that changed the requirements

---

## 1. Problem Statement

The Capability Delivery Pipeline produces **external observability artifacts** deterministically — dashboards, alerting rules, SLO definitions — all derived from the `.contextcore.yaml` manifest. But the **internal instrumentation** — the code inside the service that emits the metrics and traces those artifacts consume — is left as TODO stubs.

The dashboards declare PromQL queries expecting `rpc_server_duration_seconds{grpc_method="..."}`. The generated services have empty `initStats()` methods. The contract is fulfilled on the dashboard side and broken on the service side.

The missing piece: a **derivation step** in the EXPORT stage that computes what instrumentation each service needs and emits it in `onboarding-metadata.json`.

---

## 2. What Already Exists in ContextCore

| Component | File | What it actually provides |
|-----------|------|--------------------------|
| `SemanticConventionHints.metrics` | `models/artifact_manifest.py:374` | **Dict of metric names by source** — the closest thing to "what metrics does this project expect" |
| `SemanticConventionHints.query_templates` | `models/artifact_manifest.py:378` | Named PromQL/TraceQL/LogQL query templates |
| `service_communication_graph` | `onboarding-metadata.json` | Per-service protocol, RPC calls, imports (implemented 2026-03-16) |
| `service_metadata` | `onboarding-metadata.json` | Transport protocol, healthcheck type per service |
| `derivation_rules` | `onboarding-metadata.json` | How business context maps to artifact **parameters** (criticality → alertSeverity) |
| `ARTIFACT_PARAMETER_SCHEMA` | `utils/onboarding.py:418` | Parameter **keys** per artifact type (dashboard: criticality, datasources; prometheus_rule: thresholds) |
| `design_calibration_hints` | `onboarding-metadata.json` | Per-service transport protocol in calibration context |

---

## 3. Critical Findings from Implementation Planning

### Finding 1: Dashboard artifact parameters do NOT contain PromQL

**Impact on REQ-ICD-100 as originally written: requirement was not implementable.**

The original requirement assumed dashboard artifacts carry PromQL queries in their `parameters` dict. They don't. Actual dashboard parameters are business-level inputs:

```python
# What the artifact manifest actually has for dashboards:
ArtifactType.DASHBOARD: ["criticality", "dashboardPlacement", "datasources", "risks"]

# What the requirement assumed it had:
# PromQL like: rpc_server_duration_seconds{grpc_method="ListProducts"}
```

PromQL lives in the **generated Grafana dashboard JSON files** (`grafana/provisioning/dashboards/json/`), which are produced after or alongside the export stage. They are not in the artifact manifest's parameter schema.

### Finding 2: Convention-based derivation is more reliable than PromQL parsing

OTel semantic conventions define **standard metric names per transport protocol**. A gRPC service with an OTel interceptor will always emit:
- `rpc.server.duration` (histogram)
- `rpc.server.request.size` / `rpc.server.response.size` (histograms)
- `rpc.server.requests_per_rpc` (histogram)

An HTTP service will always emit:
- `http.server.duration` (histogram)
- `http.server.request.body.size` (histogram)

These are deterministic — no parsing needed. The communication graph already tells us the protocol.

### Finding 3: `semantic_conventions.metrics` already has named metrics

`SemanticConventionHints.metrics` is a `Dict[str, List[str]]` — metric names keyed by source. If the artifact manifest populates this field, the instrumentation derivation can read it directly instead of parsing PromQL.

### Finding 4: Target vs service granularity mismatch

Artifact manifest uses `target` (e.g., `"online-boutique"` — one deployment). Communication graph uses service names (e.g., `"emailservice"`, `"frontend"` — per microservice). A manifest may have 1 target with 10 services. The derivation must bridge this gap.

### Finding 5: `logging.trace_context_fields` has no data source at Stage 4

Log configuration (log4j2.xml, Python logging config) exists in generated code, not in the manifest or plan. At export time, ContextCore cannot know what trace context fields the logging framework needs. This section must be explicitly empty — populated by startd8-sdk after code generation.

### Finding 6: Language detection piggybacks on existing file scanning

`_extract_service_communication_graph` already scans `src/{service}/` directory patterns. The target file extension is in the same section text. Language detection is a free addition to the existing scan, not a separate pass.

---

## 4. Requirements (Revised)

### REQ-ICD-100: Protocol-Based Metric Expectations (Quick Win)

**Priority:** P1
**Status:** Implemented — `src/contextcore/utils/instrumentation.py:24-41, 92-113`
**Implements:** REQ-TCW-000 (ContextCore portion)
**Replaces:** Original "Dashboard-to-Metrics Derivation" — revised per Finding 1+2
**File:** `src/contextcore/utils/instrumentation.py`

The EXPORT stage SHALL derive expected metric names from the transport protocol and OTel semantic conventions. This is deterministic and requires no PromQL parsing.

**Derivation logic:**

1. For each service in `service_communication_graph.services`:
   - Map protocol to OTel semantic convention metrics:

   | Protocol | Standard Metrics |
   |----------|-----------------|
   | `grpc` | `rpc.server.duration`, `rpc.server.request.size`, `rpc.server.response.size`, `rpc.server.requests_per_rpc` |
   | `http` | `http.server.duration`, `http.server.request.body.size`, `http.server.response.body.size` |

   - Labels are implicit in the OTel convention (gRPC: `rpc.service`, `rpc.method`, `rpc.grpc.status_code`; HTTP: `http.method`, `http.route`, `http.status_code`)

2. Supplement with `semantic_conventions.metrics` from the artifact manifest (if populated)

3. Supplement with metric names extracted from `semantic_conventions.query_templates` (PromQL templates, if present)

**Acceptance:**
- gRPC service → `metrics.convention_based` contains `rpc.server.duration` etc.
- HTTP service → `metrics.convention_based` contains `http.server.duration` etc.
- Metrics from `semantic_conventions.metrics` are included in `metrics.manifest_declared`
- No observability artifacts → `metrics.convention_based` still populated from protocol (this is the key improvement over the original requirement)

**Why this is better:** The original requirement would fail silently for manifests without PromQL in parameters (which is all of them). This approach produces correct results from data that always exists (the communication graph protocol field).

---

### REQ-ICD-100a: Dashboard Metric Extraction (Deferred Enhancement)

**Priority:** P3
**Status:** Deferred to V2
**Depends on:** Dashboard JSON files available at export time or post-export scan

When generated Grafana dashboard JSON files are available (either from template rendering or from `--scan-existing`), the EXPORT stage MAY parse panel definitions to extract PromQL metric names and add them to `metrics.dashboard_declared`.

**Rationale for deferral:** Dashboard JSON generation happens in the same stage or after export. Implementing this requires either a two-pass export or a post-export enrichment hook. The convention-based approach (REQ-ICD-100) provides the high-value path with zero parsing complexity.

---

### REQ-ICD-101: Communication-Graph-to-Traces Derivation (Quick Win)

**Priority:** P1
**Status:** Implemented — `src/contextcore/utils/instrumentation.py:116-156`
**Implements:** REQ-TCW-001 (ContextCore portion)
**Depends on:** Service communication graph (REQ-SIG-100–104, implemented)

The EXPORT stage SHALL derive required trace spans from the service communication graph.

**Derivation logic:**

1. For each service in `service_communication_graph.services`:
   - Determine transport protocol from `service.protocol` (grpc/http)
   - For gRPC services: server span `{grpc_service}/{grpc_method}` + client spans per `rpc_calls`
   - For HTTP services: server span `{http_method} {http_route}`
   - Required attributes from OTel semantic conventions:
     - gRPC: `rpc.system`, `rpc.service`, `rpc.method`
     - HTTP: `http.method`, `http.route`, `http.status_code`

2. Propagation format: W3C Trace Context (default). Override from `spec.observability` if specified.

**Acceptance:**
- gRPC service with 2 RPC calls → 3 trace entries (1 server + 2 client)
- HTTP service → 1 generic HTTP span entry
- Empty graph → empty traces section
- Traces include source reference to communication graph entry

---

### REQ-ICD-102: Language-Aware SDK Resolution

**Priority:** P2
**Status:** Implemented — `src/contextcore/utils/instrumentation.py:48-89, 159-187`
**Implements:** REQ-TCW-002 (ContextCore portion)
**Depends on:** REQ-ICD-104 (language detection, implemented)

The EXPORT stage SHALL resolve OTel SDK dependency coordinates for each service's detected language.

**Data source (priority order):**
1. `service_communication_graph.services.{name}.language` (from REQ-ICD-104)
2. Default: omit SDK section (downstream resolves from code inspection)

**SDK mapping table:**

| Language | SDK Package | gRPC Interceptor | HTTP Instrumentation | Exporter |
|----------|------------|-------------------|---------------------|----------|
| java | `io.opentelemetry:opentelemetry-sdk` | `io.grpc:grpc-opentelemetry` | `io.opentelemetry.instrumentation:opentelemetry-spring-boot-starter` | `io.opentelemetry:opentelemetry-exporter-otlp` |
| go | `go.opentelemetry.io/otel` | `go.opentelemetry.io/contrib/.../otelgrpc` | `go.opentelemetry.io/contrib/.../otelhttp` | `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` |
| python | `opentelemetry-sdk` | `opentelemetry-instrumentation-grpc` | `opentelemetry-instrumentation-flask` | `opentelemetry-exporter-otlp` |
| nodejs | `@opentelemetry/sdk-node` | `@opentelemetry/instrumentation-grpc` | `@opentelemetry/instrumentation-http` | `@opentelemetry/exporter-trace-otlp-grpc` |
| dotnet | `OpenTelemetry` | `OpenTelemetry.Instrumentation.GrpcNetClient` | `OpenTelemetry.Instrumentation.AspNetCore` | `OpenTelemetry.Exporter.OpenTelemetryProtocol` |

**Design note:** The mapping table is a code constant for V1. It could be externalized to YAML for user customization in V2, but the number of supported languages is small and changes are rare.

**Acceptance:**
- Java gRPC service → SDK + gRPC interceptor + OTLP exporter coordinates
- Unknown language → `sdk` section omitted (not an error — downstream resolves)
- Version defaults to `"latest_stable"` (downstream resolves to concrete version)

---

### REQ-ICD-103: Instrumentation Hints Emission

**Priority:** P1
**Status:** Implemented — `src/contextcore/utils/instrumentation.py:190-273` + wiring in `onboarding.py:1059-1068`
**Implements:** REQ-TCW-003 (ContextCore portion)
**File:** `src/contextcore/utils/onboarding.py :: build_onboarding_metadata()`

The EXPORT stage SHALL emit instrumentation hints as a section of `onboarding-metadata.json`.

**Revised schema (simplified from original "contract" to "hints"):**

```json
{
  "instrumentation_hints": {
    "emailservice": {
      "service_id": "emailservice",
      "language": "python",
      "transport": "grpc",
      "metrics": {
        "convention_based": [
          {"name": "rpc.server.duration", "type": "histogram", "source": "otel_semconv:grpc"},
          {"name": "rpc.server.request.size", "type": "histogram", "source": "otel_semconv:grpc"}
        ],
        "manifest_declared": [
          {"name": "custom_metric_from_semconv", "source": "semantic_conventions.metrics"}
        ],
        "sdk": {
          "package": "opentelemetry-sdk",
          "interceptor": "opentelemetry-instrumentation-grpc",
          "exporter": "opentelemetry-exporter-otlp"
        }
      },
      "traces": {
        "required": [
          {"span_name": "{grpc_service}/{grpc_method}", "attributes": ["rpc.system", "rpc.service", "rpc.method"], "source": "service_communication_graph:emailservice"}
        ],
        "propagation": "W3C",
        "sdk": {
          "package": "opentelemetry-sdk",
          "interceptor": "opentelemetry-instrumentation-grpc"
        }
      },
      "logging": {
        "trace_context_fields": [],
        "_note": "Populated by startd8-sdk after code generation (Stage 6), not by ContextCore"
      },
      "dependencies": {
        "add": [
          {"package": "opentelemetry-sdk", "version": "latest_stable"},
          {"package": "opentelemetry-instrumentation-grpc", "version": "latest_stable"},
          {"package": "opentelemetry-exporter-otlp", "version": "latest_stable"}
        ]
      }
    }
  }
}
```

**Key schema changes from original:**
1. **Renamed `instrumentation_contracts` → `instrumentation_hints`** — "contract" implies enforcement; these are hints for downstream code generation. The downstream TODO Scanner enforces.
2. **Split `metrics.required` into `convention_based` + `manifest_declared`** — makes provenance explicit. Convention-based metrics come from protocol → OTel semconv mapping (always available). Manifest-declared come from `semantic_conventions.metrics` (available when populated).
3. **`logging.trace_context_fields` explicitly empty with `_note`** — per Finding 5, ContextCore cannot populate this at export time.

**Acceptance:**
1. `onboarding-metadata.json` includes `instrumentation_hints` keyed by service ID
2. Each hint includes: `service_id`, `transport`, `metrics` (with `convention_based`, `manifest_declared`, `sdk`), `traces`, `logging`, `dependencies`
3. `language` present only when detected (per REQ-ICD-104)
4. `attachment_points` NOT emitted — computed by startd8-sdk after code generation
5. Empty communication graph → empty `instrumentation_hints` dict (no services known)
6. Profile-agnostic: emitted for all `--profile` values

---

### REQ-ICD-104: Language Detection from Plan Text (Quick Win)

**Priority:** P1 (upgraded from P2 — Finding 6 shows this is trivially simple and blocks SDK resolution)
**Status:** Implemented — `src/contextcore/cli/init_from_plan_ops.py:56-81, 166-174`
**File:** `src/contextcore/cli/init_from_plan_ops.py`

The INIT-FROM-PLAN stage SHALL detect the primary language per service from plan text signals, piggybacking on the existing `_extract_service_communication_graph()` file scanning.

**Detection approach:** The existing `_TARGET_DIR_PATTERN` already matches `src/{service}/`. The file extension in the same section text reveals the language:

| Signal | Language |
|--------|----------|
| `.py`, `python`, `flask`, `django`, `fastapi`, `gunicorn` | python |
| `.java`, `gradle`, `maven`, `spring`, `jvm` | java |
| `.go`, `go.mod`, `go.sum` | go |
| `.ts`, `.js`, `package.json`, `npm`, `express` | nodejs |
| `.cs`, `.csproj`, `dotnet`, `nuget` | dotnet |

**Storage:** Add `language` field to `service_communication_graph.services.{name}`:
```json
{
  "services": {
    "emailservice": {
      "imports": ["demo_pb2", "demo_pb2_grpc"],
      "rpc_calls": [],
      "protocol": "grpc",
      "language": "python"
    }
  }
}
```

**Acceptance:**
- Plan with `src/emailservice/main.py` → `language: "python"`
- Plan with `src/adservice/build.gradle` → `language: "java"`
- No language signals → `language` key absent (not `null`)
- Existing communication graph tests continue to pass (backward compatible)

---

## 5. Target Granularity Bridging (Finding 4)

The artifact manifest and communication graph operate at different granularities:

| Source | Keying | Example |
|--------|--------|---------|
| Artifact manifest `target` | Deployment name | `"online-boutique"` |
| Communication graph `services` | Microservice name | `"emailservice"`, `"frontend"` |

**Resolution:** Instrumentation hints are keyed by **service name** (from the communication graph). When an artifact's `target` matches a service name, that artifact's metrics are attributed to that service. When an artifact's `target` is a project-level name (not matching any service), its metrics are attributed to all services in the graph.

This bridging happens in `derive_instrumentation_hints()` and does not require schema changes.

---

## 6. Estimated Scope

| Requirement | New Lines | Files Modified | Files Created | Quick Win? |
|-------------|-----------|----------------|---------------|------------|
| REQ-ICD-104 (language detection) | ~30 | 1 (`init_from_plan_ops.py`) | 0 | Yes |
| REQ-ICD-100 (protocol→metrics) | ~60 | 0 | 1 (`instrumentation.py`) | Yes |
| REQ-ICD-101 (graph→traces) | ~50 | 0 | (same file) | Yes |
| REQ-ICD-102 (SDK resolution) | ~65 | 0 | (same file) | No (depends on 104) |
| REQ-ICD-103 (emission) | ~15 | 1 (`onboarding.py`) | 0 | Yes (after 100+101) |
| REQ-ICD-100a (dashboard PromQL) | deferred | — | — | No |
| Tests | ~180 | 0 | 1 (`test_instrumentation.py`) | — |
| **Total V1** | **~400** | **2** | **2** | |

---

## 7. Verification

```bash
# Unit tests
python3 -m pytest tests/unit/contextcore/utils/test_instrumentation.py -v

# Language detection tests (extend existing)
python3 -m pytest tests/unit/contextcore/cli/test_service_graph_extraction.py -v -k language

# Integration: export with service communication graph
contextcore manifest export -p .contextcore.yaml -o ./out/export --profile source
jq '.instrumentation_hints | keys' ./out/export/onboarding-metadata.json

# Verify convention-based metrics populated from protocol
jq '.instrumentation_hints.emailservice.metrics.convention_based[].name' ./out/export/onboarding-metadata.json

# Full regression
python3 -m pytest tests/ -x
```

---

## 8. Planning-Derived Revision Log

| Finding | Original Requirement | What Changed | Impact |
|---------|---------------------|-------------|--------|
| Dashboard params have no PromQL | REQ-ICD-100 assumed PromQL in artifact parameters | Replaced with convention-based derivation (protocol → OTel metrics) | P1 requirement became implementable; PromQL deferred to P3 |
| `semantic_conventions.metrics` exists | REQ-ICD-100 proposed PromQL parsing as only source | Added `manifest_declared` metric source from existing field | Reduced scope; leverages existing data |
| Target vs service granularity | Not addressed | Added Section 5 with explicit bridging strategy | Prevents silent data loss |
| `logging.trace_context_fields` has no data source | REQ-ICD-103 schema included it | Explicitly empty with `_note`; populated by downstream | Prevents false expectations |
| Language detection is trivial | REQ-ICD-104 was P2 | Upgraded to P1; piggybacks on existing file scanning | Unblocks REQ-ICD-102 with minimal effort |
| "Contract" implies enforcement | Schema used `instrumentation_contracts` | Renamed to `instrumentation_hints` | Clearer responsibility boundary — ContextCore hints, startd8-sdk enforces |

---

## 9. Security Contract Support (REQ-ICD-105, REQ-ICD-106)

### REQ-ICD-105: Graph-Derived Database Detection (Tier 2, Zero-Config)

**Priority:** P1 | **Status:** Implemented (2026-03-20) | **Depends on:** REQ-ICD-104

The EXPORT stage detects database client libraries from `service_communication_graph.services.{name}.imports` and emits `detected_databases` per service in `instrumentation_hints`.

**Three-tier fidelity model:**

| Tier | Source | Fidelity | User effort |
|------|--------|----------|-------------|
| **1** | `spec.security.data_stores` in manifest | Full — client_library, sensitivity, credential_source, access_policy | User declares |
| **2** | Communication graph imports | Medium — database type auto-detected | Zero (piggybacks on existing scan) |
| **3** | Plan/feature text keyword matching | Low — generic database type (startd8-sdk fallback) | Zero |

**Detection table:**

| Import keyword | Database type |
|----------------|--------------|
| `Npgsql`, `psycopg2`, `asyncpg`, `pg`, `postgres` | `postgresql` |
| `Spanner`, `SpannerConnection` | `spanner` |
| `MySql`, `mysql`, `pymysql` | `mysql` |
| `Redis`, `StackExchange.Redis`, `redis` | `redis` |
| `Sqlite`, `sqlite3`, `System.Data.SQLite` | `sqlite` |
| `AlloyDB` | `postgresql` (AlloyDB uses pg wire protocol) |

**Output** (added to each service's instrumentation hints):
```json
{
  "cartservice": {
    "detected_databases": ["spanner", "postgresql"],
    ...
  },
  "emailservice": {
    "detected_databases": [],
    ...
  }
}
```

### REQ-ICD-106: Manifest-Declared Security Contract with RBAC Access Policy (Tier 1)

**Priority:** P2 | **Status:** Implemented (2026-03-20) | **Depends on:** REQ-ICD-105

When `spec.security.data_stores` is present in `.contextcore.yaml`, the EXPORT stage emits a `security_contract` section in `onboarding-metadata.json`, including RBAC-derived access policy hints.

**Schema** (matches startd8-sdk `security_prime/contract.py:98-126`):

```yaml
spec:
  security:
    sensitivity: high
    data_stores:
      - id: cartdb
        type: spanner
        client_library: Google.Cloud.Spanner.Data
        credential_source: workload_identity
        sensitivity: high
        access_policy:
          allowed_principals: [service_account]
          required_role: security-reader
          audit_access: true
```

**Emitted contract:**
```json
{
  "security_contract": {
    "databases": {
      "cartdb": {
        "type": "spanner",
        "client_library": "Google.Cloud.Spanner.Data",
        "credential_source": "workload_identity",
        "sensitivity": "high",
        "access_policy": {
          "allowed_principals": ["service_account"],
          "required_role": "security-reader",
          "audit_access": true
        }
      }
    },
    "sensitivity": "high",
    "source": "manifest"
  }
}
```

**RBAC integration:** `ResourceType.DATA_STORE` added to RBAC models.

**Acceptance:**
- `spec.security.data_stores` present → `security_contract` emitted with `"source": "manifest"`
- `spec.security` absent → `security_contract` not emitted (Tier 2 `detected_databases` still available)
- `access_policy` optional — omitted when not declared
- Missing optional fields default: `sensitivity: "medium"`, `client_library: ""`, `credential_source: ""`

---

## 10. Cross-References

| Document | Relationship |
|----------|-------------|
| [TODO Completion Workflow Requirements](~/Documents/dev/startd8-sdk/docs/design/prime/TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md) | Cross-system parent — REQ-TCW-000–003; this doc is the ContextCore-specific elaboration |
| [Implementation Plan](../../plans/INSTRUMENTATION_CONTRACT_DERIVATION_PLAN.md) | Step-by-step implementation with code sketches |
| [Service Interconnectedness Requirements](../SERVICE_INTERCONNECTEDNESS_REQUIREMENTS.md) | REQ-SIG-100–104 — communication graph extraction that feeds REQ-ICD-101 |
| [Generation Profiles](REQ_GENERATION_PROFILES.md) | REQ-GP-100–501 — profile scoping for onboarding metadata sections |
| [Contracts Gap Analysis](REQ_CONTRACTS_GAP_ANALYSIS.md) | Context on what's essential vs dormant in `contextcore.contracts` |
| [Pipeline-Innate Requirements](~/Documents/dev/cap-dev-pipe/design/pipeline-requirements.md) | REQ-CDP-OBS-001–007 — the external observability artifacts this bridges to internal code |
| [Cross-Cutting Context Loss Analysis](~/Documents/dev/startd8-sdk/docs/design/kaizen/CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | Root cause analysis — proto import hallucination is one instance; instrumentation gaps are another |
| [OTel Semantic Conventions for RPC](https://opentelemetry.io/docs/specs/semconv/rpc/rpc-metrics/) | Authoritative source for gRPC/HTTP metric names used in REQ-ICD-100 |
| startd8-sdk `security_prime/contract.py` | Consumer schema for security contract — REQ-ICD-106 matches its field expectations |
