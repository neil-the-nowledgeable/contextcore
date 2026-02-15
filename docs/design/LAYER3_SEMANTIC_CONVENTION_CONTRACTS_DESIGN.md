# Semantic Convention Contracts — Layer 3 Design

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.85
**Implementation:** `src/contextcore/contracts/semconv/` (planned)
**Related:**
- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation
- [Context Propagation Contracts (Layer 1)](CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — field flow enforcement
- [Weaver Cross-Repo Alignment Plan](../plans/WEAVER_CROSS_REPO_ALIGNMENT_PLAN.md) — implementation phases
- [Weaver Cross-Repo Alignment Requirements](../plans/WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md) — REQ-1 through REQ-8
- [Semantic Conventions](../agent-semantic-conventions.md) — existing attribute reference
- [OTel GenAI Migration Guide](../OTEL_GENAI_MIGRATION_GUIDE.md) — dual-emit migration

---

## 1. Problem

Three repositories — ContextCore, StartD8 SDK, and Wayfinder — independently
emit telemetry attributes that describe the same concepts. Each repository is
internally consistent. The inconsistency only appears when you try to correlate
across repositories — and the failure is silent.

### 1.1 Naming Drift in Practice

**Attribute naming for the same concept:**

| Concept | ContextCore | StartD8 Emitter | Wayfinder Scripts | OTel Standard |
|---|---|---|---|---|
| Task identifier | `task.id` | `task.id` | `task_id` | `task.id` |
| Task lifecycle | `task.status` | `task.status` | `status` | `task.status` |
| Task lifecycle (deprecated) | `status` (LabelName.STATUS) | — | `state` | — |
| User identity | `user.id` | `user_id` | `userId` | `enduser.id` |
| LLM provider | `gen_ai.system` | `agent.model` | `llm.provider` | `gen_ai.system` |
| Model name | `gen_ai.request.model` | `agent.model` | `model.name` | `gen_ai.request.model` |

Each service is internally consistent. Each service passes its own tests. The
problem appears only when a dashboard, alert rule, or TraceQL query tries to
join data from multiple sources.

### 1.2 How This Breaks Dashboards

A Grafana dashboard panel queries:

```traceql
{ span.task.status = "in_progress" }
```

This finds spans from ContextCore. It misses spans from a Wayfinder script
that wrote `status = "in_progress"` (no `task.` prefix). It misses spans from
another service that wrote `state = "running"` (different name, different
value). The panel shows 1/3 of the data. No error. No warning. The operator
sees fewer tasks than exist and draws incorrect conclusions.

A Loki recording rule derives a metric:

```yaml
- record: project:contextcore_task_count:count_by_status
  expr: |
    count by (task_status) (
      {job="contextcore"} | json | task_status != ""
    )
```

This rule counts tasks by `task_status`. Services that emit `status` or
`task.status` or `state` produce log lines that don't match the JSON key. The
metric undercounts. Alerts based on the metric don't fire when they should.

A PromQL alert checks:

```promql
sum(rate(gen_ai_client_token_usage_total{gen_ai_system="openai"}[5m])) > 100
```

But the StartD8 SDK emits `agent.model` instead of `gen_ai.system`. The
Prometheus exporter transforms the attribute name to `agent_model`. The alert
never fires because it queries a label that doesn't exist in the metric.

### 1.3 Enum Value Drift

Beyond attribute names, the *values* within those attributes drift:

| Enum | `contracts/types.py` | Handoff module (runtime) | Docs (prose) | Weaver Registry Plan |
|---|---|---|---|---|
| HandoffStatus | 6 members | 9 members (+input_required, cancelled, rejected) | 9 members | 6 members |
| TaskStatus | 7 members | 7 members | 7 members | 7 members |

A dashboard that filters `handoff.status = "input_required"` works against
spans from the handoff module but would fail validation against `types.py`.
A CI check using `types.py` as the source of truth would reject valid
runtime data. The cardinality mismatch creates a gap where runtime reality
and declared schema disagree.

### 1.4 Why Voluntary Adoption Fails

OpenTelemetry created semantic conventions precisely to solve this problem.
The conventions define canonical attribute names (`gen_ai.system`, not
`llm.provider`), canonical enum values (`in_progress`, not `running`), and
canonical structures (dot-separated namespaces, not camelCase).

But enforcement is voluntary. OTel provides recommendation; it does not
provide validation. No tool in the OTel ecosystem says:

> "Your `user_id` attribute violates the convention. Dashboards querying
> `user.id` will not find your data."

The result is that every organization re-discovers this problem independently,
after dashboards go blank, after alerts fail to fire, after hours of debugging
reveal that the root cause is a spelling difference.

ContextCore needs a structural answer — a `ConventionSpec` contract system
that declares canonical names and enforces them at CI time, runtime, and
dashboard-build time.

---

## 2. Solution Overview

A convention contract system that treats attribute naming like a type system
for telemetry. Conventions declare the canonical names for attributes, their
types, requirement levels, and known aliases. Validators enforce conventions
at emission time. CI checks enforce them across repositories. OTel events
make violations observable.

```
              convention-registry.contract.yaml
              (canonical attribute definitions)
                         |
                    ContractLoader
                     (parse + cache)
                         |
              +----------+-----------+
              v                      v
     ConventionValidator      AliasResolver
     (check emitted attrs)    (map aliases -> canonical)
              |                      |
              v                      v
     ConventionValidationResult   AliasResolutionResult
     (compliant, violations,      (resolved_name,
      warnings, aliases_used)      original_name, mode)
              |                      |
              +----------+-----------+
                         v
               OTel Span Event Emission
               (convention.validated,
                convention.alias_detected,
                convention.violation)
```

### Four Primitives (Shared with Layer 1)

| Primitive | Layer 1 (Propagation) | Layer 3 (Convention) |
|---|---|---|
| **Declare** | `PropagationChainSpec` — field flow paths | `ConventionSpec` — canonical attribute names |
| **Validate** | `BoundaryValidator` — field presence at boundaries | `ConventionValidator` — attribute name compliance |
| **Track** | `PropagationTracker` — provenance stamps | `AliasResolver` — alias resolution history |
| **Emit** | `emit_boundary_result()` — OTel events | `emit_convention_result()` — OTel events |

### Split Placement

The framework (schema models, loader, validator, alias resolver, OTel helpers)
lives in **ContextCore**. The convention registry YAML lives in
**ContextCore** (as the canonical source). Consumer repos (StartD8 SDK,
Wayfinder) reference the registry via CI checks or pinned allowlists.

| Component | Repo | Path |
|---|---|---|
| Schema models | ContextCore | `src/contextcore/contracts/semconv/schema.py` |
| YAML loader | ContextCore | `src/contextcore/contracts/semconv/loader.py` |
| Convention validator | ContextCore | `src/contextcore/contracts/semconv/validator.py` |
| Alias resolver | ContextCore | `src/contextcore/contracts/semconv/resolver.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/semconv/otel.py` |
| Convention registry | ContextCore | `semconv/registry/` (Weaver YAML format) |
| Enum consistency script | ContextCore | `scripts/validate_enum_consistency.py` |
| Emitter validation tests | StartD8 SDK | `tests/unit/test_emitter_semconv.py` |

---

## 3. Contract Format

Contracts are YAML files validated against Pydantic v2 models
(`ConventionContract`). All models use `extra="forbid"` to reject unknown keys
at parse time, following the same pattern as `contracts/a2a/models.py` and
`contracts/propagation/schema.py`.

### 3.1 Top-Level Structure

```yaml
schema_version: "0.1.0"        # SemVer, starts at 0.1.0 per Weaver convention
contract_type: semantic_convention
domain: agent_telemetry         # Scoping domain for this convention set
description: >
  Semantic conventions for agent telemetry attributes across
  ContextCore, StartD8 SDK, and Wayfinder.

conventions:                    # List of canonical attribute definitions
  - canonical: gen_ai.system
    type: str
    requirement: required
    aliases: [llm.provider, ai.system, model.provider]
    description: "The LLM provider system"

  - canonical: gen_ai.request.model
    type: str
    requirement: required
    aliases: [model.name, llm.model, ai.model, agent.model]
    description: "The model requested for generation"

enum_conventions:               # Enum value registries
  - attribute: task.status
    values: [backlog, todo, in_progress, in_review, blocked, done, cancelled]
    source: contracts/types.py::TaskStatus
    description: "Task lifecycle status values"

  - attribute: handoff.status
    values: [pending, accepted, in_progress, completed, failed, timeout,
             input_required, cancelled, rejected]
    source: contracts/types.py::HandoffStatus
    description: "Agent handoff lifecycle status values"
```

### 3.2 Attribute Convention Specification

Each attribute in a contract is an `AttributeConvention`:

| Property | Type | Required | Description |
|---|---|---|---|
| `canonical` | str | Yes | The canonical attribute name (e.g. `gen_ai.system`) |
| `type` | str | No | Expected value type. Default: `"str"` |
| `requirement` | enum | No | `required` / `recommended` / `opt_in`. Default: `required` |
| `aliases` | list[str] | No | Known non-canonical names for this attribute |
| `description` | str | No | Human-readable description |
| `namespace` | str | No | Attribute namespace (e.g. `gen_ai`, `task`). Derived from `canonical` if not set |
| `deprecated` | bool | No | Whether this canonical name is itself deprecated |
| `deprecated_by` | str | No | The replacing canonical name, if deprecated |
| `stability` | str | No | `experimental` / `stable` / `deprecated`. Default: `stable` |

**Namespace derivation:** If `namespace` is not explicitly set, it is derived
from `canonical` by taking everything before the last dot. For `gen_ai.system`,
namespace is `gen_ai`. For `task.status`, namespace is `task`. For
`gen_ai.request.model`, namespace is `gen_ai.request`.

### 3.3 Enum Convention Specification

Each enum convention is an `EnumConvention`:

| Property | Type | Required | Description |
|---|---|---|---|
| `attribute` | str | Yes | The attribute this enum applies to |
| `values` | list[str] | Yes | Canonical enum values |
| `source` | str | No | Source of truth reference (e.g. `contracts/types.py::TaskStatus`) |
| `description` | str | No | Human-readable description |
| `extensible` | bool | No | Whether unknown values are allowed. Default: `false` |

When `extensible` is `false`, the validator rejects attribute values not in the
`values` list. When `extensible` is `true`, the validator logs unknown values
at ADVISORY severity but does not reject them.

### 3.4 Domain Scoping

Conventions are scoped by domain to support independent evolution. The
ContextCore ecosystem currently has these domains:

| Domain | Namespaces | Owner |
|---|---|---|
| `task_telemetry` | `task.*`, `project.*`, `sprint.*` | ContextCore |
| `agent_telemetry` | `gen_ai.*`, `agent.*` (deprecated) | ContextCore |
| `handoff_telemetry` | `handoff.*`, `gen_ai.tool.*` | ContextCore |
| `insight_telemetry` | `insight.*`, `gen_ai.insight.*` | ContextCore |
| `skill_telemetry` | `skill.*`, `capability.*` | Wayfinder (local) |
| `messaging_telemetry` | `messaging.*` | ContextCore (Fox/Rabbit) |
| `cicd_telemetry` | `cicd.pipeline.*` | ContextCore |

Domains can be validated independently. A Wayfinder CI check validates only
`skill_telemetry` conventions locally, while referencing the canonical
`task_telemetry` conventions from ContextCore's registry.

---

## 4. Requirement Levels

The requirement levels align with OTel semantic convention levels and the
Weaver cross-repo alignment plan. They also map to `ConstraintSeverity`
from `contracts/types.py` for consistency with Layer 1.

### 4.1 Level Definitions

| Requirement Level | ConstraintSeverity | On Violation | Producer Contract | Consumer Contract |
|---|---|---|---|---|
| `required` | `BLOCKING` | CI fails, runtime error event | MUST emit with canonical name | MUST expect this attribute |
| `recommended` | `WARNING` | CI warns, runtime warning event, alias accepted | SHOULD emit with canonical name | SHOULD query canonical name |
| `opt_in` | `ADVISORY` | CI logs, runtime info event | MAY emit | MUST tolerate absence |

### 4.2 Behavioral Contracts

**`required`** attributes are load-bearing. If a span omits `task.id`, the
span cannot be correlated with any task. If a metric omits `gen_ai.system`,
cost attribution is impossible. Required attributes using non-canonical names
(aliases) produce BLOCKING violations.

**`recommended`** attributes enhance correlation quality. `task.priority` is
recommended — its absence doesn't break task tracking, but its presence
enables priority-based dashboard filtering. Aliases for recommended attributes
produce WARNING violations with automatic resolution.

**`opt_in`** attributes are contextually useful. `task.estimated_loc` is
opt_in — only code generation tasks have meaningful line count estimates.
Producers MAY emit these attributes. Consumers MUST NOT require their
presence. Consumers MUST NOT fail if an opt_in attribute is absent.

### 4.3 Mapping to Weaver Plan

| Layer 3 Requirement | Weaver Requirement Level | ConstraintSeverity |
|---|---|---|
| `required` | `required` | `BLOCKING` |
| `recommended` | `recommended` | `WARNING` |
| `opt_in` | `opt_in` | `ADVISORY` |

This three-way alignment — Layer 3 levels, Weaver levels, and
ConstraintSeverity enum — ensures that the convention system, the Weaver
registry, and the Layer 1 propagation system all speak the same severity
language.

---

## 5. Validation Modes

Convention validation operates at three different times in the development
lifecycle, each with different trade-offs between strictness and latency.

### 5.1 CI-Time Validation

At CI time, the `validate_enum_consistency.py` script (Weaver Plan Phase 6.3)
and `weaver registry check` enforce convention compliance across repositories.

```
PR opened in StartD8 SDK
       |
       v
+----------------------------+
| validate_emitter_attrs.py   |  <- Checks emitter output against allowlist
| Checks: attribute names     |     derived from ContextCore registry
| match canonical convention  |     Fails on unknown attributes
+----------------------------+
       |
       v
+----------------------------+
| validate_enum_consistency   |  <- Checks enum values in code against
| Checks: TaskStatus, Priority|     registry YAML enum definitions
| HandoffStatus cardinality   |     Fails on cardinality mismatch
+----------------------------+
       |
       v
   PR approved (or blocked)
```

**CI checks run in each repository:**

| Repository | Check | Script | Fails On |
|---|---|---|---|
| ContextCore | `weaver registry check` | Weaver binary | Invalid registry YAML |
| ContextCore | Enum consistency | `validate_enum_consistency.py` | Enum drift between `types.py` and registry |
| StartD8 SDK | Emitter attribute names | `validate_emitter_attrs.py` | Unknown attributes not in registry |
| StartD8 SDK | SpanState round-trip | `test_task_tracking_emitter.py` | State file incompatibility |
| Wayfinder | Convention reference | (future) | Conflicting attribute definitions |

### 5.2 Runtime Validation

At runtime, the `ConventionValidator` checks emitted span attributes against
the loaded convention registry. This runs inline during telemetry emission,
similar to how `BoundaryValidator` runs at phase boundaries in Layer 1.

```python
class ConventionValidator:
    def __init__(self, contract: ConventionContract):
        self._contract = contract
        self._resolver = AliasResolver(contract)
        self._canonical_names: dict[str, AttributeConvention] = {
            c.canonical: c for c in contract.conventions
        }
        self._enum_conventions: dict[str, EnumConvention] = {
            e.attribute: e for e in contract.enum_conventions
        }

    def validate_attributes(
        self,
        attributes: dict[str, Any],
        *,
        resolve_aliases: bool = True,
    ) -> ConventionValidationResult:
        """Validate a set of attributes against conventions.

        Args:
            attributes: Dict of attribute name -> value to validate.
            resolve_aliases: If True, attempt alias resolution for
                non-canonical names.

        Returns:
            ConventionValidationResult with compliance status.
        """
```

**Runtime validation flow:**

```
Span attributes emitted
       |
       v
+--------------------------+
| ConventionValidator       |
| For each attribute:       |
|  1. Is name canonical?    |
|     -> Yes: check type/value compliance
|     -> No: is name a known alias?
|        -> Yes: resolve + warn
|        -> No: unknown attribute (may be valid extension)
+--------------------------+
       |
       v
ConventionValidationResult
  .compliant: bool
  .violations: list[ConventionViolation]
  .aliases_resolved: list[AliasResolution]
  .unknown_attributes: list[str]
       |
       v
emit_convention_result()  (OTel span event)
```

**Performance considerations:** Runtime validation adds latency to every span
emission. To mitigate:

1. The convention registry is loaded once and cached (same pattern as
   `ContractLoader._cache` in Layer 1).
2. Canonical name lookup is O(1) via `dict`.
3. Alias lookup uses a pre-built reverse index: `alias_name -> canonical_name`.
4. Validation can be disabled via `CONTEXTCORE_SEMCONV_VALIDATE=false`.

### 5.3 Dashboard-Time Validation

When building Grafana dashboards or writing queries, the convention registry
serves as a reference for correct attribute names. Dashboard-time validation
is advisory — it helps authors write correct queries but does not block
dashboard provisioning.

**Query builder integration:**

```python
# ConventionQueryHelper uses the registry to suggest canonical names
helper = ConventionQueryHelper(contract)

# Warns: "task_status" is not canonical; use "task.status"
helper.validate_traceql('{ span.task_status = "in_progress" }')
# -> ConventionViolation(
#        attribute="task_status",
#        canonical="task.status",
#        severity=WARNING,
#        message="Use canonical name 'task.status' instead of 'task_status'"
#    )

# Warns: "running" is not a canonical value for task.status
helper.validate_traceql('{ span.task.status = "running" }')
# -> ConventionViolation(
#        attribute="task.status",
#        value="running",
#        canonical_values=["backlog", "todo", "in_progress", ...],
#        severity=WARNING,
#        message="'running' is not a canonical value for task.status"
#    )
```

**Dashboard-as-code validation (REQ-8):**

The Weaver plan's REQ-8 specifies that Grafana dashboard JSON should be
validated against the producer's telemetry schema. This Layer 3 design
provides the validation engine:

```bash
# Scan dashboard JSON for attribute references and validate
python3 scripts/validate_dashboard_conventions.py \
    --registry semconv/ \
    --dashboards grafana/provisioning/dashboards/json/*.json
```

The script parses dashboard JSON for TraceQL, PromQL, and LogQL queries,
extracts attribute names from those queries, and validates each against the
convention registry.

---

## 6. Alias Resolution

Alias resolution is the process of mapping non-canonical attribute names to
their canonical equivalents. It supports the migration path from legacy
attributes (`agent.model`) to canonical attributes (`gen_ai.request.model`)
without breaking existing telemetry.

### 6.1 Resolution Modes

The alias resolver operates in three modes, controlled by configuration:

| Mode | Behavior | Use Case |
|---|---|---|
| `resolve` | Replace alias with canonical name, emit warning event | Migration period — existing code uses old names |
| `warn` | Keep alias name, emit warning event | Audit period — see what would change without breaking anything |
| `reject` | Fail validation, emit violation event | Enforcement period — only canonical names accepted |

**Mode progression during migration:**

```
Phase 1: resolve  (old code works, but warnings appear in dashboards)
Phase 2: warn     (old code works, migration tickets filed from warnings)
Phase 3: reject   (old code breaks CI, must use canonical names)
```

This mirrors the `CONTEXTCORE_EMIT_MODE` migration for OTel GenAI attributes:
`dual` -> `otel` is the same progression as `resolve` -> `reject`.

### 6.2 Resolution Algorithm

```
resolve_attribute(name, value):
    1. Check canonical_names[name]
       -> Found: return (name, value, CANONICAL)

    2. Check alias_index[name]
       -> Found: canonical = alias_index[name]
          if mode == "resolve":
              return (canonical, value, RESOLVED)
          if mode == "warn":
              return (name, value, WARNED)
          if mode == "reject":
              return (name, value, REJECTED)

    3. Check namespace conventions
       -> If name starts with known namespace (task., gen_ai., etc.)
          but doesn't match any canonical or alias:
          return (name, value, UNKNOWN_IN_NAMESPACE)

    4. Not in any known namespace:
       return (name, value, EXTENSION)
```

**Status values:**

| Status | Meaning |
|---|---|
| `CANONICAL` | Name is the canonical name. No action needed. |
| `RESOLVED` | Name was an alias. Resolved to canonical. Warning emitted. |
| `WARNED` | Name was an alias. Kept as-is. Warning emitted. |
| `REJECTED` | Name was an alias. Resolution rejected. Violation emitted. |
| `UNKNOWN_IN_NAMESPACE` | Name is in a known namespace but not registered. Possible typo or missing convention. |
| `EXTENSION` | Name is not in any known namespace. Treated as a valid extension attribute. |

### 6.3 ATTRIBUTE_MAPPINGS Integration

The existing `ATTRIBUTE_MAPPINGS` dict in `otel_genai.py` is a hardcoded
alias resolver for the `agent.*` -> `gen_ai.*` migration. The convention
contract system subsumes this:

```python
# Current (hardcoded in otel_genai.py)
ATTRIBUTE_MAPPINGS = {
    "agent.id": "gen_ai.agent.id",
    "agent.model": "gen_ai.request.model",
    # ...
}

# Future (derived from convention registry)
contract = load_convention_contract("semconv/registry/agent.yaml")
resolver = AliasResolver(contract, mode="resolve")

# The resolver handles the same mapping, but from YAML not code
result = resolver.resolve("agent.model", "gpt-4")
# -> AliasResolution(
#        original="agent.model",
#        canonical="gen_ai.request.model",
#        status=RESOLVED,
#    )
```

**Migration path for ATTRIBUTE_MAPPINGS:** The Weaver Plan Phase 2
consolidates the fragmented dicts. Layer 3 replaces the consolidated dict
with a registry-driven resolver. The progression:

1. **Phase 2 (Weaver Plan):** Consolidate to one `ATTRIBUTE_MAPPINGS` dict
2. **Layer 3 initial:** `AliasResolver` wraps `ATTRIBUTE_MAPPINGS` for
   backward compatibility. Convention YAML is the source of truth.
3. **Layer 3 mature:** `ATTRIBUTE_MAPPINGS` is removed. `AliasResolver`
   reads directly from convention YAML. Tests validate that registry `aliases`
   fields cover all legacy mappings.

### 6.4 Data Model

```python
class AliasResolution(BaseModel):
    """Result of resolving a single attribute name."""

    model_config = ConfigDict(extra="forbid")

    original: str = Field(..., description="The attribute name as emitted")
    canonical: str = Field(..., description="The canonical attribute name")
    status: AliasStatus = Field(
        ..., description="Resolution status"
    )
    convention: Optional[str] = Field(
        None, description="Convention domain this alias belongs to"
    )
    message: Optional[str] = Field(
        None, description="Human-readable explanation"
    )
```

---

## 7. OTel Event Semantics

All events follow the ContextCore telemetry conventions and are emitted as
OTel span events on the current active span. If OTel is not installed, events
are logged only (no crash). This follows the `_HAS_OTEL` guard pattern from
`contracts/propagation/otel.py`.

### 7.1 Convention Validated

**Event name:** `convention.validated`

Emitted when all attributes in a span comply with conventions.

| Attribute | Type | Description |
|---|---|---|
| `convention.domain` | str | Convention domain (e.g. `"agent_telemetry"`) |
| `convention.compliant` | bool | Always `true` for this event |
| `convention.total_attributes` | int | Number of attributes checked |
| `convention.canonical_count` | int | Attributes using canonical names |
| `convention.alias_count` | int | Attributes resolved from aliases |
| `convention.compliance_pct` | float | `canonical_count / total * 100` |

**TraceQL query — find fully compliant spans:**
```traceql
{ name = "convention.validated" && span.convention.compliance_pct = 100 }
```

### 7.2 Alias Detected

**Event name:** `convention.alias_detected`

Emitted when an attribute uses a known alias instead of the canonical name.

| Attribute | Type | Description |
|---|---|---|
| `convention.original_name` | str | The alias name used (e.g. `"agent.model"`) |
| `convention.canonical_name` | str | The canonical name (e.g. `"gen_ai.request.model"`) |
| `convention.domain` | str | Convention domain |
| `convention.resolution_mode` | str | `resolve` / `warn` / `reject` |
| `convention.requirement` | str | `required` / `recommended` / `opt_in` |

**TraceQL query — find alias usage:**
```traceql
{ name = "convention.alias_detected" }
```

**TraceQL query — find aliases for a specific canonical name:**
```traceql
{ name = "convention.alias_detected" && span.convention.canonical_name = "gen_ai.system" }
```

### 7.3 Convention Violation

**Event name:** `convention.violation`

Emitted when an attribute name is in a known namespace but not registered as
either a canonical name or an alias. Also emitted for enum value violations.

| Attribute | Type | Description |
|---|---|---|
| `convention.attribute_name` | str | The violating attribute name |
| `convention.violation_type` | str | `unknown_name` / `unknown_value` / `type_mismatch` / `alias_rejected` |
| `convention.domain` | str | Convention domain |
| `convention.namespace` | str | The namespace the attribute appears to belong to |
| `convention.severity` | str | `blocking` / `warning` / `advisory` |
| `convention.suggestion` | str | Suggested canonical name (if similar match found) |
| `convention.message` | str | Human-readable explanation |

**TraceQL query — find all violations:**
```traceql
{ name = "convention.violation" }
```

**TraceQL query — find blocking violations only:**
```traceql
{ name = "convention.violation" && span.convention.severity = "blocking" }
```

### 7.4 Convention Summary

**Event name:** `convention.summary`

Emitted once per batch of attribute validations (e.g. per span export),
aggregating all convention check results.

| Attribute | Type | Description |
|---|---|---|
| `convention.total_checked` | int | Total attributes checked |
| `convention.canonical_count` | int | Using canonical names |
| `convention.alias_count` | int | Using aliases (resolved or warned) |
| `convention.violation_count` | int | Violating conventions |
| `convention.unknown_count` | int | Not in any known namespace |
| `convention.compliance_pct` | float | `canonical / total * 100` |

**TraceQL query — find low compliance:**
```traceql
{ name = "convention.summary" && span.convention.compliance_pct < 80 }
```

### 7.5 Relationship to Layer 1 Events

| Layer 1 Event | Layer 3 Event | Composition |
|---|---|---|
| `context.boundary.entry` | `convention.validated` | Layer 1 checks "is the field present?" Layer 3 checks "is it named correctly?" |
| `context.chain.degraded` | `convention.alias_detected` | Chain degraded because field is present under alias, not canonical name |
| `context.chain.broken` | `convention.violation` | Chain broken because field is missing — but is it missing or just misspelled? |

---

## 8. Relationship to Weaver Plan

This design document formalizes the validation framework that the Weaver
cross-repo alignment plan implements in phases. The relationship is:

**Weaver Plan** defines *what* to do (phases, deliverables, acceptance criteria).
**Layer 3 Design** defines *how* to do it (data models, algorithms, OTel events).

### 8.1 Requirement Mapping

| Weaver REQ | Layer 3 Component | How Layer 3 Satisfies It |
|---|---|---|
| **REQ-1**: Registry covers cross-repo attributes | `ConventionContract.conventions` | Every attribute from every producer is declared with canonical name, aliases, and requirement level |
| **REQ-2**: Emitter alignment | `ConventionValidator.validate_attributes()` | Emitter output is validated against convention registry; violations fail CI |
| **REQ-3**: ATTRIBUTE_MAPPINGS consolidation | `AliasResolver` | Alias resolver replaces hardcoded ATTRIBUTE_MAPPINGS dict with registry-driven resolution |
| **REQ-4**: HandoffStatus reconciliation | `ConventionContract.enum_conventions` | Enum conventions declare canonical cardinality; `validate_enum_consistency.py` enforces it |
| **REQ-5**: Wayfinder references registry | Domain scoping (`skill_telemetry` local, `task_telemetry` referenced) | Convention contracts support domain-scoped validation with cross-domain references |
| **REQ-6**: Cross-repo schema validation | CI-time validation mode (Section 5.1) | CI checks in each repo validate against convention registry |
| **REQ-7**: Emitter/StateManager format parity | Runtime validation mode (Section 5.2) | Both producers validated against same convention contract |
| **REQ-8**: Schema change notification | `convention.violation` events + dashboard validation | Schema changes that break convention compliance are detected and surfaced as ContextCore tasks |

### 8.2 Phase Mapping

| Weaver Phase | Layer 3 Status | Dependency |
|---|---|---|
| Phase 1: Bootstrap Registry | Provides the YAML that `ConventionContract` parses | Layer 3 schema models must parse Weaver YAML format |
| Phase 2: Consolidate ATTRIBUTE_MAPPINGS | `AliasResolver` replaces consolidated dict | Resolver aliases field must cover all ATTRIBUTE_MAPPINGS entries |
| Phase 3: Align StartD8 Emitter | CI-time validation for emitter attributes | `validate_emitter_attrs.py` uses `ConventionValidator` |
| Phase 4: Reconcile HandoffStatus | Enum conventions enforce single cardinality | `EnumConvention.values` is the source of truth |
| Phase 5: Wayfinder Registry Reference | Domain scoping handles cross-repo references | Wayfinder validates `skill.*` locally, references `task.*` from ContextCore |
| Phase 6: Cross-Repo CI | All three validation modes operational | Full Layer 3 implementation required |
| Phase 7: Documentation | Design doc (this document) + CLAUDE.md updates | Layer 3 design precedes implementation |

### 8.3 Registry Format Alignment

The Weaver plan creates registry YAML files in `semconv/registry/`. The Layer 3
`ConventionContract` must be able to parse either:

1. **Native convention contract YAML** (Section 3.1 format) — for standalone
   convention validation
2. **Weaver registry YAML** — for integration with the OTel Weaver toolchain

The `ContractLoader` detects the format by checking for the presence of
`contract_type: semantic_convention` (native) vs. `groups:` (Weaver format)
and normalizes both into the internal `ConventionContract` model.

---

## 9. Relationship to Layer 1

Layer 1 asks: **"Did the field propagate?"**
Layer 3 asks: **"Is it named correctly?"**

These are independent but composable questions. A field can propagate
correctly but be named incorrectly (alias drift). A field can be named
correctly but fail to propagate (dropped in transit). The most dangerous
case is when a field *appears* to be missing (Layer 1: BROKEN chain) but
is actually present under a different name (Layer 3: alias).

### 9.1 Composing Layer 1 + Layer 3

```
Context arrives at phase boundary
       |
       +---> Layer 1: BoundaryValidator
       |     "Is domain_summary.domain present?"
       |     -> ABSENT (chain status: BROKEN)
       |
       +---> Layer 3: ConventionValidator
       |     "Are attribute names canonical?"
       |     -> domain_summary.classification found (alias for domain)
       |     -> ALIAS_DETECTED: domain_summary.classification -> domain_summary.domain
       |
       +---> Combined insight:
             Field IS present, but under non-canonical name.
             Layer 1 alone would report BROKEN.
             Layer 3 explains WHY: naming drift.
             Resolution: rename classification -> domain, or add alias to contract.
```

### 9.2 Shared Infrastructure

| Component | Layer 1 | Layer 3 |
|---|---|---|
| `ConstraintSeverity` | `BLOCKING` / `WARNING` / `ADVISORY` | Same enum (imported from `contracts/types.py`) |
| `ContractLoader` | Per-path caching | Same caching pattern |
| `_HAS_OTEL` guard | `propagation/otel.py` | `semconv/otel.py` |
| `extra="forbid"` | All Pydantic models | All Pydantic models |
| Event emission pattern | `_add_span_event()` | Same helper function |

---

## 10. Relationship to OTel Semantic Conventions

ContextCore's convention enforcement **complements** OTel semantic conventions.
It does not replace them.

### 10.1 What OTel Provides

OTel semantic conventions define:
- Canonical attribute names (`gen_ai.system`, `http.method`, `db.system`)
- Recommended types (`string`, `int`, `boolean`)
- Requirement levels (`required`, `recommended`, `opt_in`)
- Stability levels (`experimental`, `stable`, `deprecated`)
- Namespace organization (dot-separated, lowercase)

### 10.2 What OTel Does Not Provide

OTel does **not** provide:
- **Runtime validation**: No tool checks emitted spans against conventions
- **CI enforcement**: No CI action validates attribute names in code
- **Alias resolution**: No mechanism maps legacy names to canonical names
- **Cross-service consistency**: No tool verifies that Service A and Service B
  use the same attribute name for the same concept
- **Dashboard validation**: No tool checks that dashboard queries use
  canonical names

### 10.3 What ContextCore Adds

ContextCore provides the **enforcement layer** that OTel's conventions lack:

| OTel | ContextCore Layer 3 |
|---|---|
| Publishes conventions as markdown + YAML | Parses conventions into validatable Pydantic models |
| Recommends `gen_ai.system` | Rejects `llm.provider` with suggestion to use `gen_ai.system` |
| Defines requirement levels (required/recommended/opt_in) | Maps to `ConstraintSeverity` (BLOCKING/WARNING/ADVISORY) |
| Documents stability (experimental/stable/deprecated) | Enforces deprecation lifecycle with removal timelines |
| Provides the Weaver registry tool | Extends Weaver with runtime + CI + dashboard validation |

### 10.4 ContextCore-Specific Conventions

Some conventions are ContextCore-specific (not part of OTel semconv):

| Namespace | Source | Examples |
|---|---|---|
| `task.*` | ContextCore | `task.id`, `task.status`, `task.type`, `task.percent_complete` |
| `project.*` | ContextCore | `project.id`, `project.name`, `project.epic` |
| `sprint.*` | ContextCore | `sprint.id`, `sprint.name`, `sprint.goal` |
| `handoff.*` | ContextCore | `handoff.id`, `handoff.status`, `handoff.capability_id` |
| `insight.*` | ContextCore | `insight.type`, `insight.confidence`, `insight.value` |
| `skill.*` | Wayfinder | `skill.name`, `skill.version`, `skill.token_count` |
| `capability.*` | Wayfinder | `capability.id`, `capability.type` |
| `context.*` | Layer 1 | `context.phase`, `context.chain_status`, `context.completeness_pct` |
| `convention.*` | Layer 3 | `convention.domain`, `convention.compliance_pct` |

These namespaces are registered in the ContextCore convention registry and
validated with the same framework used for OTel standard attributes.

---

## 11. Dashboard Integration

### 11.1 Recommended Panels

**Convention Compliance Rate (Stat panel)**
```traceql
{ name = "convention.summary" }
| select(span.convention.compliance_pct)
```

**Alias Usage Over Time (Time series)**
```traceql
{ name = "convention.alias_detected" }
| rate()
```

**Violations by Namespace (Bar gauge)**
```traceql
{ name = "convention.violation" }
| select(span.convention.namespace)
| rate()
```

**Top Aliases Still In Use (Table)**
```traceql
{ name = "convention.alias_detected" }
| select(
    span.convention.original_name,
    span.convention.canonical_name,
    span.convention.domain
  )
```

**Compliance by Domain (Pie chart)**
```traceql
{ name = "convention.summary" }
| select(
    span.convention.domain,
    span.convention.canonical_count,
    span.convention.alias_count,
    span.convention.violation_count
  )
```

**Unknown Attributes (Logs panel)**
```traceql
{ name = "convention.violation" && span.convention.violation_type = "unknown_name" }
```

### 11.2 Alerting Rules

**Alert: Required attribute using alias (migration regression)**
```yaml
- alert: ConventionAliasOnRequired
  expr: |
    count_over_time(
      {job="contextcore"} | json
      | event = "convention.alias_detected"
      | convention_requirement = "required" [15m]
    ) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Required attributes are being emitted with alias names instead of canonical names"
```

**Alert: Convention violation rate above threshold**
```yaml
- alert: ConventionViolationRate
  expr: |
    sum(rate(
      {job="contextcore"} | json
      | event = "convention.violation" [5m]
    )) / sum(rate(
      {job="contextcore"} | json
      | event =~ "convention.*" [5m]
    )) > 0.05
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Convention violation rate exceeds 5% — attribute naming drift detected"
```

### 11.3 Composition with Layer 1 Panels

The Layer 1 Propagation Completeness panel and the Layer 3 Convention
Compliance panel should be placed on the same dashboard row. Together they
answer: "Are fields propagating correctly (Layer 1) AND named correctly
(Layer 3)?"

```
+----------------------------------+----------------------------------+
| Propagation Completeness         | Convention Compliance            |
| context.propagation_summary      | convention.summary               |
| completeness_pct: 95%            | compliance_pct: 88%              |
+----------------------------------+----------------------------------+
| Broken Chains (time series)      | Alias Usage (time series)        |
| context.chain.broken rate        | convention.alias_detected rate   |
+----------------------------------+----------------------------------+
```

---

## 12. Adoption Path

### 12.1 For Existing Codebases

1. **Audit.** Run `validate_enum_consistency.py` against `types.py` and the
   registry YAML. This produces a report of current drift without changing
   anything.

2. **Declare.** Write convention contract YAML for your domain. Start with
   `required` attributes only — these are the names that dashboards and alerts
   already depend on. This is a documentation exercise that happens to be
   machine-parseable.

3. **Warn.** Enable runtime validation in `warn` mode
   (`CONTEXTCORE_SEMCONV_MODE=warn`). Alias events appear in telemetry but
   nothing breaks. Monitor the Convention Compliance dashboard panel.

4. **Resolve.** Switch to `resolve` mode
   (`CONTEXTCORE_SEMCONV_MODE=resolve`). Aliases are automatically resolved
   to canonical names. Emitter code still uses old names, but downstream
   dashboards see canonical names.

5. **Enforce.** Switch to `reject` mode
   (`CONTEXTCORE_SEMCONV_MODE=reject`). Non-canonical names produce
   BLOCKING violations. Emitter code must be updated to use canonical names.
   Add CI check to block PRs with violations.

6. **Extend.** Add `recommended` and `opt_in` attributes. Add enum
   conventions. Tighten requirement levels as confidence grows.

This mirrors TypeScript's adoption path: start with `any`, add types
incrementally, turn on strict mode when ready. It also mirrors the
`CONTEXTCORE_EMIT_MODE` migration: `dual` -> `legacy` -> `otel`.

### 12.2 For New Code

Write convention contracts alongside the code that emits telemetry. Review
them in the same PR. The convention contract declares "this code emits these
attributes with these names" — a machine-readable version of what would
otherwise be implicit in the span creation code.

### 12.3 For Cross-Repo Teams

1. **Phase 1:** ContextCore publishes the convention registry as the source
   of truth (Weaver Plan Phase 1).
2. **Phase 2:** Consumer repos (StartD8, Wayfinder) add CI checks that
   validate their emitter code against an allowlist derived from the registry.
   The allowlist can be hardcoded initially (Weaver Plan Phase 6, Option A).
3. **Phase 3:** Replace hardcoded allowlists with automated registry fetching
   (Weaver Plan Phase 6, Option B). Version pinning ensures consumer repos
   update deliberately.

### 12.4 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CONTEXTCORE_SEMCONV_VALIDATE` | `true` | Enable/disable runtime convention validation |
| `CONTEXTCORE_SEMCONV_MODE` | `warn` | Resolution mode: `resolve` / `warn` / `reject` |
| `CONTEXTCORE_SEMCONV_REGISTRY` | `semconv/` | Path to convention registry directory |

---

## 13. Consequences

### Positive

1. **Naming drift becomes detectable.** Every non-canonical attribute name
   produces an observable signal — span event, CI failure, or dashboard
   warning. Silent drift is structurally impossible.
2. **Alias resolution enables migration.** Teams can adopt canonical names
   incrementally without breaking existing dashboards. The resolver handles
   the transition.
3. **Enum consistency is enforced.** A single source of truth for enum
   values, validated at CI time across repositories. HandoffStatus cardinality
   mismatch (6 vs 9) cannot recur.
4. **Dashboard correctness is verifiable.** Dashboard JSON can be validated
   against the convention registry before provisioning. Stale attribute
   references are caught at build time, not in production.
5. **Progressive adoption.** Fully opt-in. Existing code unchanged until
   validation is enabled. Start with `warn`, end with `reject`.
6. **Complements OTel.** Adds enforcement where OTel provides only
   recommendation. Does not fork or replace OTel semconv — extends it with
   validation tooling.
7. **Shared primitives.** Uses the same `ConstraintSeverity`, `_HAS_OTEL`,
   `extra="forbid"` patterns as Layer 1. No new frameworks to learn.

### Neutral

1. **Convention YAML must be maintained.** When new attributes are added, the
   convention contract must be updated. This is the same cost as maintaining
   `types.py` enums — and the convention system can validate that both stay
   in sync.
2. **Alias resolution adds a translation layer.** Downstream consumers see
   canonical names even when producers emit aliases. This is intentional but
   requires awareness — debugging a span may show a canonical name that the
   emitter code doesn't use.
3. **Two validation paths.** CI-time validation (static, against code) and
   runtime validation (dynamic, against emitted spans) may produce different
   results if the code path branches. Both are needed — CI catches drift
   before merge, runtime catches drift in production.

### Negative

1. **Runtime validation adds latency.** Every span emission checks attribute
   names against the registry. Mitigated by O(1) dict lookup, caching, and
   opt-out via environment variable.
2. **Convention YAML format may diverge from Weaver.** If OTel Weaver
   changes its YAML schema, the `ContractLoader` must be updated. Mitigated
   by version pinning and format detection.
3. **Alias resolution can mask problems.** In `resolve` mode, aliases are
   silently resolved. A team may not realize their code uses legacy names
   because everything "works." The `convention.alias_detected` events are
   the mitigation — monitor the dashboard panel to track alias usage.
4. **Cross-repo CI adds coupling.** Consumer repos depend on the ContextCore
   registry. A registry change can break consumer CI. Mitigated by version
   pinning — consumer repos pin to a specific registry version and update
   deliberately.

---

## 14. Future Work

1. **Weaver codegen integration.** Generate Python enum classes and attribute
   constants directly from convention YAML. This replaces manual maintenance
   of `contracts/types.py` with generated code — the YAML becomes the single
   source of truth for both validation and code.

2. **Convention diff tool.** A CLI command that shows what changed between
   two convention versions: added attributes, removed attributes, renamed
   attributes, changed requirement levels. Useful for PR reviews and
   migration planning.

3. **Automatic alias discovery.** Analyze historical telemetry data to
   discover attribute names that appear to be aliases (same value
   distribution, different name). Suggest convention entries automatically.

4. **Layer 1 + Layer 3 unified checker.** A combined validator that runs
   both propagation checks (Layer 1) and convention checks (Layer 3) at
   every boundary. When a Layer 1 chain reports BROKEN, the Layer 3 checker
   automatically searches for aliases that might explain the apparent absence.

5. **OpenTelemetry Collector processor.** A custom OTel Collector processor
   that applies convention validation and alias resolution at the collection
   layer. This enables convention enforcement without modifying application
   code — the collector normalizes attribute names before export.

6. **Convention versioning.** Support multiple convention versions
   simultaneously. During migration, old producers emit under version N,
   new producers emit under version N+1. The collector or backend normalizes
   to the latest version.

7. **Semantic similarity matching.** When an unknown attribute name is
   detected, use edit distance or embedding similarity to suggest the
   closest canonical name. "Did you mean `gen_ai.system` instead of
   `genai_system`?"

8. **Cross-layer dashboard.** A single Grafana dashboard that combines
   Layer 1 propagation health, Layer 3 convention compliance, and future
   layer metrics into a unified "Context Correctness Score."

---

## Appendix A: Type Hierarchy

```
ConventionContract
+-- schema_version: str
+-- contract_type: Literal["semantic_convention"]
+-- domain: str
+-- description: str?
+-- conventions: list[AttributeConvention]
|   +-- AttributeConvention
|       +-- canonical: str              (e.g. "gen_ai.system")
|       +-- type: str                   (e.g. "str", "int", "string[]")
|       +-- requirement: RequirementLevel  (required | recommended | opt_in)
|       +-- aliases: list[str]          (e.g. ["llm.provider", "ai.system"])
|       +-- description: str?
|       +-- namespace: str?             (derived from canonical if absent)
|       +-- deprecated: bool
|       +-- deprecated_by: str?
|       +-- stability: StabilityLevel   (experimental | stable | deprecated)
+-- enum_conventions: list[EnumConvention]
    +-- EnumConvention
        +-- attribute: str              (e.g. "task.status")
        +-- values: list[str]           (e.g. ["backlog", "todo", ...])
        +-- source: str?               (e.g. "contracts/types.py::TaskStatus")
        +-- description: str?
        +-- extensible: bool

ConventionValidationResult
+-- compliant: bool
+-- domain: str
+-- total_attributes: int
+-- canonical_count: int
+-- alias_count: int
+-- violation_count: int
+-- unknown_count: int
+-- compliance_pct: float
+-- violations: list[ConventionViolation]
|   +-- ConventionViolation
|       +-- attribute: str
|       +-- violation_type: ViolationType  (unknown_name | unknown_value | type_mismatch | alias_rejected)
|       +-- severity: ConstraintSeverity
|       +-- message: str
|       +-- suggestion: str?
|       +-- canonical_values: list[str]?
+-- aliases_resolved: list[AliasResolution]
|   +-- AliasResolution
|       +-- original: str
|       +-- canonical: str
|       +-- status: AliasStatus          (CANONICAL | RESOLVED | WARNED | REJECTED | UNKNOWN_IN_NAMESPACE | EXTENSION)
|       +-- convention: str?
|       +-- message: str?
+-- unknown_attributes: list[str]

ConventionValidator
+-- _contract: ConventionContract
+-- _resolver: AliasResolver
+-- _canonical_names: dict[str, AttributeConvention]
+-- _enum_conventions: dict[str, EnumConvention]
+-- validate_attributes(attrs, resolve_aliases) -> ConventionValidationResult

AliasResolver
+-- _contract: ConventionContract
+-- _mode: AliasMode                    (resolve | warn | reject)
+-- _alias_index: dict[str, str]        (alias -> canonical, pre-built)
+-- resolve(name, value) -> AliasResolution
```

## Appendix B: Example Convention Contract

```yaml
# semconv/conventions/task-telemetry.contract.yaml
schema_version: "0.1.0"
contract_type: semantic_convention
domain: task_telemetry
description: >
  Semantic conventions for task tracking attributes. These attributes
  are emitted by ContextCore TaskTracker and StartD8 task_tracking_emitter.

conventions:
  # Required — every task span MUST have these
  - canonical: task.id
    type: str
    requirement: required
    description: "Unique task identifier"

  - canonical: task.status
    type: str
    requirement: required
    aliases: [status, task_status, state]
    description: "Task lifecycle status (see enum_conventions below)"

  - canonical: project.id
    type: str
    requirement: required
    aliases: [project, project_id]
    description: "Project this task belongs to"

  # Recommended — should be present for full dashboard functionality
  - canonical: task.type
    type: str
    requirement: recommended
    aliases: [type, task_type]
    description: "Task hierarchy type (see enum_conventions below)"

  - canonical: task.priority
    type: str
    requirement: recommended
    aliases: [priority, task_priority]
    description: "Task priority level (see enum_conventions below)"

  - canonical: task.title
    type: str
    requirement: recommended
    aliases: [title, task_title, summary]
    description: "Human-readable task title"

  - canonical: task.percent_complete
    type: int
    requirement: recommended
    aliases: [percent_complete, progress, completion_pct]
    description: "Task completion percentage (0-100)"

  - canonical: sprint.id
    type: str
    requirement: recommended
    aliases: [sprint, sprint_id]
    description: "Sprint this task is assigned to"

  # Opt-in — contextually useful, not always applicable
  - canonical: task.depends_on
    type: "string[]"
    requirement: opt_in
    description: "Structural dependencies (task IDs this task should start after)"

  - canonical: task.blocked_by
    type: "string[]"
    requirement: recommended
    description: "Runtime blockers (task IDs actively blocking this task)"

  - canonical: task.prompt
    type: str
    requirement: opt_in
    description: "LLM implementation instructions for code generation tasks"

  - canonical: task.feature_id
    type: str
    requirement: opt_in
    description: "Links task to parent feature in plan hierarchy"

  - canonical: task.target_files
    type: "string[]"
    requirement: opt_in
    description: "Expected output file paths for code generation tasks"

  - canonical: task.estimated_loc
    type: int
    requirement: opt_in
    description: "Pre-generation size estimate (lines of code)"

  # Deprecated — use gen_ai.* equivalents
  - canonical: agent.id
    type: str
    requirement: recommended
    deprecated: true
    deprecated_by: gen_ai.agent.id
    stability: deprecated
    description: "Agent identifier (deprecated: use gen_ai.agent.id)"

  - canonical: agent.model
    type: str
    requirement: recommended
    deprecated: true
    deprecated_by: gen_ai.request.model
    stability: deprecated
    description: "Agent model (deprecated: use gen_ai.request.model)"

enum_conventions:
  - attribute: task.status
    values: [backlog, todo, in_progress, in_review, blocked, done, cancelled]
    source: "contracts/types.py::TaskStatus"
    description: "Task lifecycle status values"

  - attribute: task.type
    values: [epic, story, task, subtask, bug, spike, incident]
    source: "contracts/types.py::TaskType"
    description: "Task hierarchy type values"

  - attribute: task.priority
    values: [critical, high, medium, low]
    source: "contracts/types.py::Priority"
    description: "Task priority levels"

  - attribute: handoff.status
    values: [pending, accepted, in_progress, completed, failed, timeout,
             input_required, cancelled, rejected]
    source: "contracts/types.py::HandoffStatus"
    extensible: false
    description: "Agent handoff lifecycle status values"

  - attribute: insight.type
    values: [decision, recommendation, blocker, discovery]
    source: "contracts/types.py::InsightType"
    description: "Agent insight type classification"
```

## Appendix C: Existing Convention Enforcement in ContextCore

ContextCore already enforces conventions in several places. Layer 3
formalizes and unifies these existing mechanisms:

| Existing Mechanism | Location | What It Enforces | Layer 3 Replacement |
|---|---|---|---|
| `MetricName` enum | `contracts/metrics.py` | Canonical metric names | `ConventionContract.conventions` for metrics namespace |
| `LabelName` enum | `contracts/metrics.py` | Canonical label names | `ConventionContract.conventions` for label namespace |
| `EventType` enum | `contracts/metrics.py` | Canonical event names | `ConventionContract.conventions` for event namespace |
| `validate_labels()` | `contracts/metrics.py` | Required labels present | `ConventionValidator.validate_attributes()` |
| `validate_metric_name()` | `contracts/metrics.py` | Metric name format | `ConventionValidator` with `MetricName` conventions |
| `ATTRIBUTE_MAPPINGS` | `compat/otel_genai.py` | Legacy -> canonical mapping | `AliasResolver` with registry-driven aliases |
| `ConstraintSeverity` | `contracts/types.py` | Severity levels | Reused directly (not duplicated) |
| `TaskStatus`, `Priority`, etc. | `contracts/types.py` | Enum values | `EnumConvention.values` validated against enum members |

The unification is the key value of Layer 3: instead of 6 separate
enforcement mechanisms with independent update paths, one convention
registry governs all naming, and one validator checks all compliance.
