# Data Lineage and Provenance Contracts — Layer 7 Design

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.75
**Implementation:** `src/contextcore/contracts/lineage/` (planned)
**Related:**
- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation
- [Context Propagation Contracts (Layer 1)](CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — base layer this extends
- [ADR-001: Tasks as Spans](../adr/001-tasks-as-spans.md) — foundational architecture
- [A2A Contracts Design](A2A_CONTRACTS_DESIGN.md) — contract-first agent coordination
- [Semantic Conventions](../semantic-conventions.md) — attribute naming standards

---

## 1. Problem

Layer 1 (Context Propagation) answers the question: **"Did the field arrive?"**
It checks presence, applies defaults when fields are absent, and reports INTACT,
DEGRADED, or BROKEN status. This is necessary but insufficient.

Layer 1 does not answer: **"Where did the field come from, what happened to it
along the way, and can we prove it?"** When a downstream output is wrong, Layer 1
tells you the field was present at the destination. It does not tell you whether
the value was correct — whether it was set by the right phase, whether it was
transformed intentionally or corrupted accidentally, or whether the intermediate
values form a coherent chain of custody.

Three concrete failure modes that Layer 1 cannot diagnose:

### 1.1 LLM Code Generation Debugging

An LLM generates code. The code has a bug. The bug could originate from:

- The **prompt** (wrong constraints passed to the model)
- The **training data** (model hallucination)
- The **post-processing** (a code formatter mangled the output)
- The **context pipeline** (domain classification was stale or wrong)

Without lineage, debugging is forensic archaeology. The engineer opens the
generated code, reads the prompt, checks the model version, and manually
traces backward through five phases to find where the bad input entered. This
takes hours per incident. With lineage, every transformation is stamped: the
prompt's `domain_constraints` field has a hash chain showing it was derived
from `domain_summary.domain`, which was classified in the plan phase at
timestamp T with value hash H. If the classification was wrong, the hash chain
points directly to the origin.

### 1.2 Multi-Phase Report Corruption

A workflow produces a report. The report contains incorrect data. The data
passed through five transformation phases:

1. **Plan** — raw project metrics collected
2. **Aggregate** — metrics grouped by team
3. **Normalize** — percentages calculated
4. **Enrich** — team names resolved from IDs
5. **Render** — final report generated

The rendered report shows Team Alpha at 120% completion — an impossible value.
Which transformation introduced the error? The normalization formula? The
aggregation grouping? A data type mismatch during enrichment? Without lineage,
an engineer must reproduce the pipeline step by step. With lineage, the hash
chain for the `completion_pct` field shows: the value was `0.85` after
normalize (hash `a1b2c3d4`), but `1.20` after enrich (hash `e5f6g7h8`). The
enrichment phase mutated a field it should have passed through unchanged.

### 1.3 Silent Value Mutation Between Phases

A domain classification was set to `"web_application"` in Phase 1 (plan). By
Phase 5 (implement), it arrives as `"unknown"`. Layer 1 detects the degradation
— `ChainStatus.DEGRADED` — because the destination value is in the sentinel
set (`None, "", "unknown", [], {}`). But Layer 1 cannot answer:

- **Which phase** changed the value?
- **What were the intermediate values?**
- Was the change **intentional** (a transform operation) or **accidental**
  (an overwrite, a re-initialization, a merge conflict)?

Layer 1's `FieldProvenance` records `origin_phase` and `value_hash` — a
single snapshot. Layer 7 records the full transformation history: every phase
that touched the field, what operation it performed, what the input and output
hashes were, and whether the hash chain is intact.

---

## 2. Solution Overview

A `LineageContract` system that extends Layer 1's provenance tracking with
full transformation history. Where Layer 1 stamps a single `FieldProvenance`
(origin, timestamp, hash), Layer 7 maintains an ordered list of
`TransformationRecord` entries — one per phase that touched the field — and
validates that the sequence matches a declared `LineageChainSpec`.

```
                    YAML Contract
              (artisan-lineage.contract.yaml)
                         |
                   ContractLoader
                 (parse + cache — reuses Layer 1)
                         |
              +----------+-----------+
              v                      v
     LineageChainSpec          TransformationRecord
     (declared pipeline)       (actual history)
              |                      |
              v                      v
        ProvenanceAuditor      LineageGraph
        (spec vs actual)       (DAG of transforms)
              |                      |
              +----------+-----------+
                         |
                         v
                LineageAuditResult
                (chain_intact, broken_links,
                 unstamped_mutations, forensic_path)
                         |
                         v
               OTel Span Event Emission
               (lineage.stage.recorded,
                lineage.chain.verified,
                lineage.chain.broken,
                lineage.audit.complete)
```

### Split Placement

Follows the same split as Layer 1: framework in ContextCore, concrete
contracts in consuming repos.

| Component | Repo | Path |
|---|---|---|
| Schema models | ContextCore | `src/contextcore/contracts/lineage/schema.py` |
| Transformation tracker | ContextCore | `src/contextcore/contracts/lineage/tracker.py` |
| Lineage graph | ContextCore | `src/contextcore/contracts/lineage/graph.py` |
| Provenance auditor | ContextCore | `src/contextcore/contracts/lineage/auditor.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/lineage/otel.py` |
| Artisan lineage contract | startd8-sdk | `src/startd8/contractors/contracts/artisan-lineage.contract.yaml` |
| Auditor wiring | startd8-sdk | `src/startd8/contractors/artisan_contractor.py` |

### Relationship to Layer 1

Layer 7 **wraps** Layer 1. It does not replace it. Concretely:

- Layer 1's `PropagationTracker.stamp()` records a single `FieldProvenance`
  per field. Layer 7's `LineageTracker.record_transformation()` appends a
  `TransformationRecord` to an ordered list per field.
- Layer 1's `_cc_propagation` metadata key is preserved. Layer 7 adds a
  sibling key `_cc_lineage`.
- Layer 1's `ChainStatus` (INTACT/DEGRADED/BROKEN) remains the primary
  signal. Layer 7 adds `LineageStatus` (VERIFIED/MUTATION_DETECTED/CHAIN_BROKEN)
  as a secondary signal with richer diagnostic information.
- A pipeline can use Layer 1 without Layer 7. Layer 7 requires Layer 1 to be
  active (it reads `_cc_propagation` data).

---

## 3. Contract Format

Lineage contracts are YAML files validated against Pydantic v2 models
(`LineageContract`). All models use `extra="forbid"` to reject unknown keys
at parse time, following the same pattern as Layer 1's `ContextContract` and
the A2A contract models.

### 3.1 Top-Level Structure

```yaml
schema_version: "0.1.0"
contract_type: data_lineage
pipeline_id: artisan
description: >
  Lineage contracts for the Artisan pipeline. Declares expected
  transformations at each stage for critical context fields.

lineage_chains:
  - chain_id: domain_classification_lineage
    # ... (see below)
  - chain_id: task_list_lineage
    # ...
```

### 3.2 Full Contract Example

```yaml
schema_version: "0.1.0"
contract_type: data_lineage
pipeline_id: artisan

lineage_chains:
  - chain_id: domain_classification_lineage
    description: >
      Track domain classification from raw input through to code generation
      constraints. The domain is classified once in plan, passes unchanged
      through scaffold and design, then is transformed into generation
      constraints in implement.
    field: domain_summary.domain
    stages:
      - phase: plan
        operation: classify
        input: project_root
        output: domain_summary.domain
        expected_type: str
        description: "Preflight analysis classifies project domain"
      - phase: scaffold
        operation: passthrough
        input: domain_summary.domain
        output: domain_summary.domain
        description: "Domain passes through scaffold unchanged"
      - phase: design
        operation: passthrough
        input: domain_summary.domain
        output: domain_summary.domain
        description: "Domain passes through design unchanged"
      - phase: implement
        operation: transform
        input: domain_summary.domain
        output: domain_constraints
        expected_type: dict
        description: "Domain classification transformed into generation constraints"
    audit_requirements:
      every_stage_stamped: true
      no_unstamped_mutations: true
      hash_chain_intact: true

  - chain_id: task_decomposition_lineage
    description: >
      Track task list from plan decomposition through implementation.
      Plan creates the task list, scaffold and design may add subtasks
      (derive operations), implement consumes the final list.
    field: tasks
    stages:
      - phase: plan
        operation: classify
        input: enriched_seed_path
        output: tasks
        expected_type: list
        description: "Plan decomposes project into task list"
      - phase: scaffold
        operation: derive
        input: tasks
        output: tasks
        expected_type: list
        description: "Scaffold may add infrastructure subtasks"
      - phase: design
        operation: derive
        input: tasks
        output: tasks
        expected_type: list
        description: "Design may refine task specifications"
      - phase: implement
        operation: passthrough
        input: tasks
        output: tasks
        expected_type: list
        description: "Implement consumes task list as-is"
    audit_requirements:
      every_stage_stamped: true
      no_unstamped_mutations: true
      hash_chain_intact: false  # derive operations change the hash

  - chain_id: validation_rules_lineage
    description: >
      Track post-generation validators from plan through test phase.
      Validators are determined by domain classification in plan,
      consumed by implement for inline checks, and consumed again
      by test for comprehensive validation.
    field: domain_summary.post_generation_validators
    stages:
      - phase: plan
        operation: derive
        input: domain_summary.domain
        output: domain_summary.post_generation_validators
        expected_type: list
        description: "Validators derived from domain classification"
      - phase: implement
        operation: passthrough
        input: domain_summary.post_generation_validators
        output: domain_summary.post_generation_validators
        description: "Validators pass through implement for inline use"
      - phase: test
        operation: passthrough
        input: domain_summary.post_generation_validators
        output: domain_summary.post_generation_validators
        description: "Validators consumed by test phase"
    audit_requirements:
      every_stage_stamped: true
      no_unstamped_mutations: true
      hash_chain_intact: true
```

### 3.3 Lineage Chain Specifications

Each chain in `lineage_chains` is a `LineageChainSpec`:

| Property | Type | Required | Description |
|---|---|---|---|
| `chain_id` | str | Yes | Unique identifier (used in OTel events, dashboards) |
| `description` | str | No | Human-readable description of what this chain tracks |
| `field` | str | Yes | The primary field being tracked (dot-path) |
| `stages` | list[StageSpec] | Yes | Ordered list of expected transformations |
| `audit_requirements` | AuditRequirements | No | What the auditor should enforce |

### 3.4 Stage Specifications

Each stage in a chain is a `StageSpec`:

| Property | Type | Required | Description |
|---|---|---|---|
| `phase` | str | Yes | Pipeline phase where this transformation occurs |
| `operation` | TransformOp | Yes | Type of transformation (see Section 4) |
| `input` | str | Yes | Dot-path of the input field(s) |
| `output` | str | Yes | Dot-path of the output field |
| `expected_type` | str | No | Expected Python type of the output |
| `description` | str | No | Human-readable description |

### 3.5 Audit Requirements

| Property | Type | Default | Description |
|---|---|---|---|
| `every_stage_stamped` | bool | true | Every declared stage must have a transformation record |
| `no_unstamped_mutations` | bool | true | No value changes between stages without a record |
| `hash_chain_intact` | bool | true | Output hash of stage N must match input hash of stage N+1 (for passthrough/filter) |

---

## 4. Transformation Types

The `operation` field in a `StageSpec` uses the `TransformOp` enum, which
classifies what a phase does to a field. The classification determines how
the auditor validates hash chain integrity.

### 4.1 Operation Definitions

| Operation | Hash Behavior | Description |
|---|---|---|
| `passthrough` | `output_hash == input_hash` | Value passes unchanged. Any hash difference indicates an unstamped mutation. |
| `classify` | No input hash (origin) | New value created from raw input. This is always the first stage in a chain. |
| `transform` | `output_hash != input_hash` (expected) | Value is intentionally changed. Both input and output hashes are recorded. |
| `derive` | New field from existing | A new field is created from one or more existing fields. The input field(s) are not consumed. |
| `aggregate` | Multiple inputs, one output | Multiple field values are combined into a single output. |
| `filter` | `len(output) <= len(input)` | Value is reduced (elements removed, scope narrowed). Hash changes expected. |

### 4.2 Hash Chain Rules by Operation

```
classify:    [no input] --> output_hash
                              |
passthrough: input_hash == output_hash  (MUST match)
                              |
passthrough: input_hash == output_hash  (MUST match)
                              |
transform:   input_hash --> output_hash  (MUST differ, both recorded)
                              |
passthrough: input_hash == output_hash  (MUST match — uses transform's output)
```

The key invariant: **for `passthrough` operations, the output hash of the
preceding stage must equal the input hash of the current stage.** If they
differ, the value was mutated between stages without a transformation record
— an unstamped mutation.

For `transform`, `derive`, `aggregate`, and `filter` operations, hashes are
expected to differ. The auditor records both the input and output hashes but
does not flag the difference as an error.

### 4.3 Pydantic Model

```python
class TransformOp(str, Enum):
    """Classification of transformation operations in a lineage chain."""

    PASSTHROUGH = "passthrough"
    CLASSIFY = "classify"
    TRANSFORM = "transform"
    DERIVE = "derive"
    AGGREGATE = "aggregate"
    FILTER = "filter"

    @classmethod
    def hash_must_match(cls) -> list["TransformOp"]:
        """Operations where input_hash must equal output_hash."""
        return [cls.PASSTHROUGH]

    @classmethod
    def hash_must_differ(cls) -> list["TransformOp"]:
        """Operations where input_hash should differ from output_hash."""
        return [cls.TRANSFORM, cls.DERIVE, cls.AGGREGATE, cls.FILTER]

    @classmethod
    def origin_operations(cls) -> list["TransformOp"]:
        """Operations that create a field from raw input (no input hash)."""
        return [cls.CLASSIFY]
```

---

## 5. Lineage Tracking

### 5.1 Data Model

The `LineageTracker` records transformation history into the context dict
under the reserved key `_cc_lineage`. This is a sibling to Layer 1's
`_cc_propagation` key — both travel with the context through the pipeline.

```python
@dataclass
class TransformationRecord:
    """A single transformation applied to a field at a pipeline stage."""

    phase: str              # Which phase performed this transformation
    operation: str          # TransformOp value (passthrough, transform, etc.)
    input_hash: str | None  # sha256[:8] of the input value (None for classify)
    output_hash: str        # sha256[:8] of the output value
    timestamp: str          # ISO 8601 timestamp
    input_field: str        # Dot-path of the input field
    output_field: str       # Dot-path of the output field

    def to_dict(self) -> dict[str, str | None]:
        return {
            "phase": self.phase,
            "operation": self.operation,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "timestamp": self.timestamp,
            "input_field": self.input_field,
            "output_field": self.output_field,
        }
```

### 5.2 Context Storage

The `_cc_lineage` key maps field dot-paths to ordered lists of
`TransformationRecord` entries:

```python
context = {
    "domain_summary": {"domain": "web_application"},
    "tasks": [...],
    # Layer 1 provenance (single snapshot per field)
    "_cc_propagation": {
        "domain_summary.domain": FieldProvenance(
            origin_phase="plan",
            set_at="2026-02-15T10:30:00Z",
            value_hash="a1b2c3d4",
        ),
    },
    # Layer 7 lineage (full transformation history per field)
    "_cc_lineage": {
        "domain_summary.domain": [
            TransformationRecord(
                phase="plan",
                operation="classify",
                input_hash=None,
                output_hash="a1b2c3d4",
                timestamp="2026-02-15T10:30:00Z",
                input_field="project_root",
                output_field="domain_summary.domain",
            ),
            TransformationRecord(
                phase="scaffold",
                operation="passthrough",
                input_hash="a1b2c3d4",
                output_hash="a1b2c3d4",
                timestamp="2026-02-15T10:30:12Z",
                input_field="domain_summary.domain",
                output_field="domain_summary.domain",
            ),
            TransformationRecord(
                phase="design",
                operation="passthrough",
                input_hash="a1b2c3d4",
                output_hash="a1b2c3d4",
                timestamp="2026-02-15T10:30:25Z",
                input_field="domain_summary.domain",
                output_field="domain_summary.domain",
            ),
            TransformationRecord(
                phase="implement",
                operation="transform",
                input_hash="a1b2c3d4",
                output_hash="e5f6g7h8",
                timestamp="2026-02-15T10:31:03Z",
                input_field="domain_summary.domain",
                output_field="domain_constraints",
            ),
        ],
    },
}
```

**Why store lineage in the context dict?** For the same reason Layer 1 stores
provenance there: the lineage must travel with the data it describes. If
lineage were stored externally (a sidecar database, a separate API), it would
itself be subject to propagation failures. Storing it in the context dict
guarantees co-location — if the context arrives, its lineage arrives with it.

**Size concern:** Lineage data grows linearly with the number of phases. For
a 7-phase pipeline tracking 5 fields, this is ~35 `TransformationRecord`
entries, each ~100 bytes. Total overhead: ~3.5 KB per pipeline run. This is
negligible relative to the context dict's typical size (10-100 KB for task
lists and generation results).

### 5.3 LineageTracker API

```python
class LineageTracker:
    """Records transformation history as context flows through phases."""

    LINEAGE_KEY = "_cc_lineage"

    def record_transformation(
        self,
        context: dict[str, Any],
        phase: str,
        operation: TransformOp,
        input_field: str,
        output_field: str,
        input_value: Any | None,
        output_value: Any,
    ) -> TransformationRecord:
        """Record a transformation at a pipeline stage.

        Also calls Layer 1's PropagationTracker.stamp() to maintain
        backward compatibility with Layer 1 provenance.

        Args:
            context: The shared mutable workflow context dict.
            phase: Phase performing the transformation.
            operation: Type of transformation.
            input_field: Dot-path of the input field.
            output_field: Dot-path of the output field.
            input_value: The input value (None for classify operations).
            output_value: The output value.

        Returns:
            The TransformationRecord that was recorded.
        """

    def get_lineage(
        self,
        context: dict[str, Any],
        field_path: str,
    ) -> list[TransformationRecord]:
        """Retrieve the full transformation history for a field."""

    def get_last_record(
        self,
        context: dict[str, Any],
        field_path: str,
    ) -> TransformationRecord | None:
        """Retrieve the most recent transformation record for a field."""
```

### 5.4 Integration with Layer 1

When `LineageTracker.record_transformation()` is called, it also invokes
Layer 1's `PropagationTracker.stamp()` to update the `_cc_propagation`
metadata. This ensures:

1. Layer 1 validation continues to work (it reads `_cc_propagation`)
2. Layer 7 is additive — activating it does not break Layer 1
3. The `_cc_propagation` snapshot always reflects the latest transformation

```python
def record_transformation(self, context, phase, operation, ...):
    # 1. Record Layer 7 lineage
    record = TransformationRecord(
        phase=phase,
        operation=operation.value,
        input_hash=_value_hash(input_value) if input_value is not None else None,
        output_hash=_value_hash(output_value),
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_field=input_field,
        output_field=output_field,
    )
    lineage = context.setdefault(self.LINEAGE_KEY, {})
    lineage.setdefault(output_field, []).append(record)

    # 2. Also stamp Layer 1 provenance (backward compat)
    self._propagation_tracker.stamp(context, phase, output_field, output_value)

    return record
```

---

## 6. Hash Chain Integrity

### 6.1 The Hash Chain

Transformation records form a hash chain analogous to a blockchain's block
chain or Git's commit chain. Each record's `output_hash` becomes the next
record's expected `input_hash`:

```
Stage 0 (classify):
    input_hash: None
    output_hash: a1b2c3d4
           |
           v
Stage 1 (passthrough):
    input_hash: a1b2c3d4  <-- must equal Stage 0 output_hash
    output_hash: a1b2c3d4  <-- must equal input_hash (passthrough)
           |
           v
Stage 2 (passthrough):
    input_hash: a1b2c3d4  <-- must equal Stage 1 output_hash
    output_hash: a1b2c3d4
           |
           v
Stage 3 (transform):
    input_hash: a1b2c3d4  <-- must equal Stage 2 output_hash
    output_hash: e5f6g7h8  <-- intentionally different (transform)
```

### 6.2 Verification Algorithm

```
verify_hash_chain(chain_spec, actual_records):
    For each consecutive pair (record_N, record_N+1):

        1. Link check: record_N.output_hash == record_N+1.input_hash
           If not: CHAIN_BROKEN at stage N+1
           ("Value was mutated between phases without a transformation record")

        2. Operation check (for passthrough/filter):
           record_N+1.input_hash == record_N+1.output_hash
           If not: MUTATION_DETECTED at stage N+1
           ("Passthrough stage modified the value")

        3. Operation check (for transform/derive/aggregate):
           record_N+1.input_hash != record_N+1.output_hash
           If equal: WARNING (transform declared but value unchanged)
```

### 6.3 Detecting Unstamped Mutations

An unstamped mutation occurs when a value changes between two recorded
transformation stages without a `TransformationRecord` explaining the change.
This is the Layer 7 analog of Layer 1's `DEGRADED` status, but with more
diagnostic power.

Detection:

```python
def _check_link(
    self,
    prev_record: TransformationRecord,
    curr_record: TransformationRecord,
) -> LinkCheckResult:
    """Check the link between two consecutive transformation records."""
    if prev_record.output_hash != curr_record.input_hash:
        return LinkCheckResult(
            intact=False,
            prev_phase=prev_record.phase,
            curr_phase=curr_record.phase,
            expected_hash=prev_record.output_hash,
            actual_hash=curr_record.input_hash,
            message=(
                f"Unstamped mutation between '{prev_record.phase}' "
                f"and '{curr_record.phase}': expected hash "
                f"'{prev_record.output_hash}', got '{curr_record.input_hash}'"
            ),
        )
    return LinkCheckResult(intact=True, ...)
```

When an unstamped mutation is detected, the auditor can narrow the window:
the mutation occurred after `prev_record.timestamp` and before
`curr_record.timestamp`, between phases `prev_record.phase` and
`curr_record.phase`. This is the forensic value — instead of "somewhere in
the pipeline," the engineer knows exactly which phase boundary to investigate.

### 6.4 Hash Function

Layer 7 reuses Layer 1's `_value_hash()` function:

```python
def _value_hash(value: Any) -> str:
    """Compute a short hash of a value for provenance tracking."""
    return hashlib.sha256(repr(value).encode()).hexdigest()[:8]
```

The 8-character truncation is intentional: it provides collision resistance
sufficient for diagnostic purposes (4 billion possible values) while keeping
the lineage metadata compact. This is not a cryptographic commitment — it is
a change-detection mechanism. If two hashes match, the values are
overwhelmingly likely to be identical. If they differ, the values definitely
differ.

---

## 7. Provenance Auditor

### 7.1 Audit Process

The `ProvenanceAuditor` compares declared lineage chains (from the YAML
contract) against actual transformation records (from `_cc_lineage` in the
context dict).

```python
class ProvenanceAuditor:
    """Validates actual transformation history against declared lineage contracts."""

    def audit_chain(
        self,
        chain_spec: LineageChainSpec,
        context: dict[str, Any],
    ) -> LineageAuditResult:
        """Audit a single lineage chain.

        Steps:
        1. Retrieve actual transformation records from _cc_lineage
        2. Compare against declared stages in chain_spec
        3. Verify hash chain integrity
        4. Check audit requirements
        5. Return LineageAuditResult with findings
        """

    def audit_all_chains(
        self,
        contract: LineageContract,
        context: dict[str, Any],
    ) -> list[LineageAuditResult]:
        """Audit all lineage chains in a contract."""
```

### 7.2 Audit Result

```python
@dataclass
class LineageAuditResult:
    """Result of auditing a single lineage chain."""

    chain_id: str
    status: LineageStatus
    total_stages: int
    stamped_stages: int
    unstamped_mutations: list[UnstampedMutation]
    broken_links: list[BrokenLink]
    missing_stages: list[str]     # Phase names declared but not recorded
    extra_stages: list[str]       # Phase names recorded but not declared
    forensic_path: list[TransformationRecord]  # Full actual history
    message: str

    @property
    def coverage_pct(self) -> float:
        """Percentage of declared stages that have transformation records."""
        return round(self.stamped_stages / max(self.total_stages, 1) * 100, 1)
```

### 7.3 Lineage Status

Added to `contracts/types.py`:

```python
class LineageStatus(str, Enum):
    """Lineage chain audit status."""

    VERIFIED = "verified"              # All stages stamped, hash chain intact
    MUTATION_DETECTED = "mutation_detected"  # Unstamped value change detected
    CHAIN_BROKEN = "chain_broken"      # Hash chain has broken links
    INCOMPLETE = "incomplete"          # Missing transformation records for declared stages
```

### 7.4 Audit Algorithm

```
audit_chain(chain_spec, context):
    actual_records = context.get("_cc_lineage", {}).get(chain_spec.field, [])

    For each stage in chain_spec.stages:
        Find matching record in actual_records (by phase name)
        If not found:
            Add to missing_stages

    For each consecutive pair in actual_records:
        Check link integrity (output_hash_N == input_hash_N+1)
        If broken:
            Add to broken_links

        For passthrough operations:
            Check input_hash == output_hash
            If different:
                Add to unstamped_mutations

    Check audit_requirements:
        If every_stage_stamped and len(missing_stages) > 0:
            status = INCOMPLETE
        If no_unstamped_mutations and len(unstamped_mutations) > 0:
            status = MUTATION_DETECTED
        If hash_chain_intact and len(broken_links) > 0:
            status = CHAIN_BROKEN
        Else:
            status = VERIFIED
```

---

## 8. Lineage Graph

### 8.1 Purpose

The `LineageGraph` provides a DAG (Directed Acyclic Graph) view of field
transformations across the entire pipeline. While `LineageChainSpec` tracks
a single field through its stages, the graph shows how fields relate to each
other — how `domain_summary.domain` feeds into `domain_constraints`, how
`tasks` and `design_results` both feed into `generation_results`.

This is the structure that enables forensic debugging: when a downstream
output is wrong, traverse the graph backward to find every field that
contributed to it, then check each contributing field's hash chain.

### 8.2 Graph Construction

```python
class LineageGraph:
    """DAG of field transformations through a pipeline."""

    def __init__(self):
        self._edges: list[LineageEdge] = []
        self._nodes: dict[str, LineageNode] = {}

    def add_transformation(self, record: TransformationRecord) -> None:
        """Add a transformation record as an edge in the graph."""

    def ancestors(self, field_path: str) -> list[str]:
        """Return all fields that contributed to this field (transitively)."""

    def descendants(self, field_path: str) -> list[str]:
        """Return all fields derived from this field (transitively)."""

    def path_between(
        self, source_field: str, dest_field: str
    ) -> list[TransformationRecord] | None:
        """Find the transformation path between two fields, or None."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph for OTel event attributes or JSON export."""
```

### 8.3 Graph Nodes and Edges

```python
@dataclass
class LineageNode:
    """A field in the lineage graph."""
    field_path: str
    phases_present: list[str]   # Phases where this field exists
    current_hash: str | None    # Latest value hash

@dataclass
class LineageEdge:
    """A transformation relationship between two fields."""
    source_field: str
    dest_field: str
    phase: str
    operation: str  # TransformOp value
    timestamp: str
```

### 8.4 Example Graph

For the Artisan pipeline, the lineage graph might look like:

```
project_root
    |
    +--[plan/classify]--> domain_summary.domain
    |                          |
    |                          +--[scaffold/passthrough]--> domain_summary.domain
    |                          |
    |                          +--[design/passthrough]--> domain_summary.domain
    |                          |
    |                          +--[implement/transform]--> domain_constraints
    |                          |
    |                          +--[plan/derive]--> domain_summary.post_generation_validators
    |                                                  |
    |                                                  +--[implement/passthrough]--> ...
    |                                                  |
    |                                                  +--[test/passthrough]--> ...
    |
    +--[plan/classify]--> tasks
    |                       |
    |                       +--[scaffold/derive]--> tasks
    |                       |
    |                       +--[design/derive]--> tasks
    |                       |
    |                       +--[implement/passthrough]--> tasks
    |
    +--[plan/classify]--> enriched_seed_path
```

---

## 9. OTel Event Semantics

All events follow ContextCore telemetry conventions and are emitted as OTel
span events on the current active span. If OTel is not installed, events are
logged only (no crash). The emission helpers follow the `_HAS_OTEL` guard
pattern from Layer 1's `otel.py`.

### 9.1 Stage Recorded Event

**Event name:** `lineage.stage.recorded`

Emitted each time `LineageTracker.record_transformation()` is called.

| Attribute | Type | Description |
|---|---|---|
| `lineage.chain_id` | str | Chain this stage belongs to (if known) |
| `lineage.phase` | str | Phase performing the transformation |
| `lineage.operation` | str | `passthrough` / `classify` / `transform` / `derive` / `aggregate` / `filter` |
| `lineage.input_field` | str | Dot-path of the input field |
| `lineage.output_field` | str | Dot-path of the output field |
| `lineage.input_hash` | str | Hash of the input value (empty for classify) |
| `lineage.output_hash` | str | Hash of the output value |

**TraceQL query — find all transformations for a field:**
```traceql
{ name = "lineage.stage.recorded" && span.lineage.output_field = "domain_summary.domain" }
```

### 9.2 Chain Verified Event

**Event name:** `lineage.chain.verified`

Emitted when the `ProvenanceAuditor` confirms a lineage chain is intact.

| Attribute | Type | Description |
|---|---|---|
| `lineage.chain_id` | str | Chain identifier |
| `lineage.status` | str | `verified` |
| `lineage.total_stages` | int | Number of declared stages |
| `lineage.stamped_stages` | int | Number of stages with transformation records |
| `lineage.coverage_pct` | float | `stamped_stages / total_stages * 100` |

**TraceQL query — find verified lineage chains:**
```traceql
{ name = "lineage.chain.verified" }
```

### 9.3 Chain Broken Event

**Event name:** `lineage.chain.broken`

Emitted when the auditor detects a broken hash chain or unstamped mutation.

| Attribute | Type | Description |
|---|---|---|
| `lineage.chain_id` | str | Chain identifier |
| `lineage.status` | str | `mutation_detected` / `chain_broken` / `incomplete` |
| `lineage.broken_link_count` | int | Number of broken links in the hash chain |
| `lineage.unstamped_mutation_count` | int | Number of unstamped mutations |
| `lineage.missing_stage_count` | int | Number of declared stages without records |
| `lineage.first_broken_phase` | str | Phase where the first break was detected |
| `lineage.message` | str | Human-readable explanation |

**TraceQL query — find broken lineage chains:**
```traceql
{ name = "lineage.chain.broken" }
```

**TraceQL query — find unstamped mutations in a specific chain:**
```traceql
{ name = "lineage.chain.broken"
  && span.lineage.chain_id = "domain_classification_lineage"
  && span.lineage.unstamped_mutation_count > 0 }
```

### 9.4 Audit Complete Event

**Event name:** `lineage.audit.complete`

Emitted once per pipeline run (typically at finalize), summarizing all
lineage chain audits.

| Attribute | Type | Description |
|---|---|---|
| `lineage.total_chains` | int | Total number of lineage chains audited |
| `lineage.verified` | int | Count of VERIFIED chains |
| `lineage.mutation_detected` | int | Count of MUTATION_DETECTED chains |
| `lineage.chain_broken` | int | Count of CHAIN_BROKEN chains |
| `lineage.incomplete` | int | Count of INCOMPLETE chains |
| `lineage.integrity_pct` | float | `verified / total * 100` |

**TraceQL query — find runs with lineage integrity below threshold:**
```traceql
{ name = "lineage.audit.complete" && span.lineage.integrity_pct < 100 }
```

### 9.5 Relationship to Layer 1 Events

Layer 7 events are **complementary** to Layer 1 events, not replacements.
A single pipeline run may emit both:

| Layer 1 Event | Layer 7 Event | Relationship |
|---|---|---|
| `context.boundary.enrichment` | `lineage.stage.recorded` | Layer 1 checks presence; Layer 7 records transformation |
| `context.chain.validated` | `lineage.chain.verified` | Layer 1 confirms field arrived; Layer 7 confirms hash chain intact |
| `context.chain.broken` | `lineage.chain.broken` | Layer 1 says field is absent; Layer 7 says where it was lost |
| `context.propagation_summary` | `lineage.audit.complete` | Layer 1 summarizes presence; Layer 7 summarizes integrity |

The key diagnostic improvement: when Layer 1 reports `DEGRADED` on a chain,
Layer 7 can tell you *which phase* introduced the degradation and *what the
value was before and after*.

---

## 10. Relationship to Layer 1

### 10.1 Structural Relationship

Layer 7 extends Layer 1 in the same way that a Git commit history extends a
file's current content. Layer 1 is the snapshot — "the field is here, it was
set by plan phase, its current hash is `a1b2c3d4`." Layer 7 is the history —
"here is every transformation the field underwent, in order, with hashes at
each step."

```
Layer 1 (snapshot):
    _cc_propagation["domain_summary.domain"] = FieldProvenance(
        origin_phase="plan",
        set_at="2026-02-15T10:30:00Z",
        value_hash="a1b2c3d4",
    )

Layer 7 (history):
    _cc_lineage["domain_summary.domain"] = [
        TransformationRecord(phase="plan", operation="classify", ...),
        TransformationRecord(phase="scaffold", operation="passthrough", ...),
        TransformationRecord(phase="design", operation="passthrough", ...),
        TransformationRecord(phase="implement", operation="transform", ...),
    ]
```

### 10.2 Dependency

Layer 7 depends on Layer 1 being active. Specifically:

- `LineageTracker.record_transformation()` calls
  `PropagationTracker.stamp()` to update `_cc_propagation`
- `ProvenanceAuditor` reads `_cc_propagation` to cross-check the latest
  provenance snapshot against the lineage history
- Layer 1's `ChainStatus` is used as a pre-filter: if Layer 1 reports
  `INTACT`, Layer 7 runs full lineage verification; if Layer 1 reports
  `BROKEN`, Layer 7 runs diagnostic analysis to identify the break point

### 10.3 Activation

Layer 7 is opt-in, independent of Layer 1. A pipeline can use:

| Configuration | Behavior |
|---|---|
| Layer 1 only | Presence checking, provenance snapshots, chain status |
| Layer 1 + Layer 7 | Full transformation history, hash chain integrity, forensic debugging |
| Layer 7 only | Not supported — Layer 7 requires Layer 1 |

---

## 11. Relationship to OpenLineage

### 11.1 What OpenLineage Does

[OpenLineage](https://openlineage.io/) is the emerging open standard for data
pipeline lineage. It defines a JSON event model with three core entities:

- **Job** — a unit of work (an Airflow task, a Spark job, a dbt model)
- **Dataset** — input or output data (a table, a file, a topic)
- **Run** — an instance of a Job execution
- **Facets** — extensible metadata attached to any entity

OpenLineage tracks which Datasets a Job reads from and writes to, forming a
graph of data flow across the entire data platform.

### 11.2 How ContextCore Relates

ContextCore's lineage model maps to OpenLineage concepts but operates at a
different granularity:

| OpenLineage | ContextCore Layer 7 | Scope |
|---|---|---|
| **Job** | Pipeline phase | A stage in the pipeline |
| **Dataset** | Context field (dot-path) | A field in the shared context dict |
| **Run** | Pipeline execution | A single workflow run |
| **Input/Output Facets** | `TransformationRecord` | How a field was transformed |
| **Lineage Graph** | `LineageGraph` | DAG of field transformations |

The key difference is granularity. OpenLineage operates at the **dataset
level** — it tracks which tables a job reads and writes. ContextCore operates
at the **field level** — it tracks which individual fields within a shared
context dict are read, written, and transformed by each phase.

This is because ContextCore's domain (workflow context propagation) deals
with a single mutable dictionary passed through sequential phases, not
independent datasets consumed by independent jobs. The "dataset" is the
context dict itself; the interesting lineage is *inside* it.

### 11.3 Future Integration Path

ContextCore's lineage events can be translated to OpenLineage format for
interoperability with the broader data lineage ecosystem:

```python
# Potential future integration
def to_openlineage_event(record: TransformationRecord) -> dict:
    return {
        "eventType": "COMPLETE",
        "job": {"name": f"contextcore.{record.phase}", "namespace": "artisan"},
        "inputs": [{"name": record.input_field, "namespace": "context"}],
        "outputs": [{"name": record.output_field, "namespace": "context"}],
        "run": {"runId": pipeline_run_id},
    }
```

This translation is not in scope for the initial implementation but is a
natural extension point.

---

## 12. Forensic Debugging

### 12.1 The Forensic Use Case

When a downstream output is wrong, the engineer needs to answer: **"Where did
the bad value come from?"** Layer 7 provides the tools to answer this
systematically rather than through ad-hoc investigation.

### 12.2 Backward Trace Algorithm

```
forensic_trace(field_path, context):
    1. Get lineage history: records = context["_cc_lineage"][field_path]
    2. Walk backward from the last record
    3. At each record, check:
       a. Is the output_hash what we expect?
       b. Does the input_hash match the previous record's output_hash?
       c. If not: THIS IS THE BREAK POINT
    4. If the break point is a transform operation:
       a. The transform's logic is suspect — check the phase's code
    5. If the break point is a passthrough operation:
       a. The value was mutated without a record — find what modified it
    6. If the input_field differs from the output_field (derive/transform):
       a. Recurse: forensic_trace(input_field, context)
```

### 12.3 Example: Tracing a Bad Domain Classification

```
Problem: implement phase received domain_constraints = {} (empty dict)

Step 1: Get lineage for "domain_constraints"
    -> Last record: phase=implement, operation=transform,
       input_hash="a1b2c3d4", output_hash="deadbeef"
    -> input_field: domain_summary.domain

Step 2: Get lineage for "domain_summary.domain"
    -> Records:
       [0] plan/classify:    output_hash="a1b2c3d4"
       [1] scaffold/passthrough: input_hash="a1b2c3d4", output_hash="a1b2c3d4"  OK
       [2] design/passthrough: input_hash="a1b2c3d4", output_hash="a1b2c3d4"  OK

Step 3: Hash chain intact for domain_summary.domain
    -> The input to implement's transform was correct ("a1b2c3d4")
    -> The transform produced "deadbeef" (empty dict)
    -> The bug is in implement's domain-to-constraints transformation logic,
       not in the upstream propagation

Diagnosis: The implement phase's _build_domain_constraints() function has a
bug — it receives "web_application" but returns {} instead of the expected
constraint dict.
```

Without Layer 7, the engineer would need to reproduce the entire pipeline,
add print statements at each phase, and manually check values. With Layer 7,
the hash chain immediately narrows the search to a single phase and a single
function.

### 12.4 Forensic Report

The `ProvenanceAuditor` can generate a structured forensic report:

```python
@dataclass
class ForensicReport:
    """Structured report for root cause analysis of lineage failures."""

    chain_id: str
    field_path: str
    break_point: TransformationRecord | None  # Where the chain broke
    suspect_phase: str | None                  # Phase to investigate
    suspect_operation: str | None              # Operation type at break point
    expected_hash: str | None                  # What the hash should have been
    actual_hash: str | None                    # What the hash actually was
    full_history: list[TransformationRecord]   # Complete transformation history
    contributing_fields: list[str]             # Upstream fields (from graph)
    recommendation: str                        # Human-readable next step
```

---

## 13. Dashboard Integration

### 13.1 Recommended Panels

**Lineage Integrity (Stat panel)**
```traceql
{ name = "lineage.audit.complete" }
| select(span.lineage.integrity_pct)
```

**Broken Lineage Chains Over Time (Time series)**
```traceql
{ name = "lineage.chain.broken" }
| rate()
```

**Lineage Coverage by Chain (Table)**
```traceql
{ name =~ "lineage.chain.*" }
| select(
    span.lineage.chain_id,
    span.lineage.status,
    span.lineage.total_stages,
    span.lineage.stamped_stages,
    span.lineage.coverage_pct
  )
```

**Unstamped Mutations (Logs panel)**
```traceql
{ name = "lineage.chain.broken" && span.lineage.unstamped_mutation_count > 0 }
| select(
    span.lineage.chain_id,
    span.lineage.first_broken_phase,
    span.lineage.message
  )
```

**Transformation Operations Distribution (Pie chart)**
```traceql
{ name = "lineage.stage.recorded" }
| select(span.lineage.operation)
```

### 13.2 Combined Layer 1 + Layer 7 Dashboard

The most useful operational dashboard combines Layer 1 and Layer 7 signals:

| Panel | Data Source | Purpose |
|---|---|---|
| Propagation Completeness | Layer 1: `context.propagation_summary` | Are fields arriving? |
| Lineage Integrity | Layer 7: `lineage.audit.complete` | Is the transformation history intact? |
| Broken Chains | Layer 1: `context.chain.broken` | Which fields are missing? |
| Mutation Details | Layer 7: `lineage.chain.broken` | Where were fields corrupted? |
| Field Lineage Graph | Layer 7: `lineage.stage.recorded` | Visual transformation DAG |

### 13.3 Alerting Rules

**Alert: Lineage integrity below threshold**
```yaml
- alert: LineageIntegrityDegraded
  expr: |
    sum(rate({job="artisan"} | json | event="lineage.audit.complete"
      | integrity_pct < 100 [5m])) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Lineage chains are not fully verified — transformation history has gaps"
```

**Alert: Unstamped mutation detected**
```yaml
- alert: UnstampedMutationDetected
  expr: |
    count_over_time({job="artisan"} | json | event="lineage.chain.broken"
      | unstamped_mutation_count > 0 [15m]) > 0
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: "A context field was mutated without a transformation record"
```

---

## 14. Adoption Path

### 14.1 For Existing Pipelines with Layer 1

If your pipeline already uses Layer 1 propagation contracts, adding Layer 7
is incremental:

1. **Write a lineage contract.** For each `propagation_chain` in your Layer 1
   contract, create a corresponding `lineage_chain` that declares the expected
   transformations at each stage. This is a documentation exercise — you are
   making explicit what you already know about how fields are transformed.

2. **Add `LineageTracker` calls.** At each phase boundary where context fields
   are set or transformed, call `lineage_tracker.record_transformation()`.
   For phases that simply pass context through, record a `passthrough`
   operation. For phases that transform fields, record the appropriate
   operation type.

3. **Add the auditor.** At the finalize phase (or wherever you run
   `validate_all_chains()`), also run `auditor.audit_all_chains()`. The
   auditor emits OTel events for dashboard visibility.

4. **Monitor.** Watch the `lineage.integrity_pct` metric. Initially it may
   be below 100% if some phases are not yet instrumented. As you add
   `record_transformation()` calls, coverage increases.

5. **Tighten.** Once coverage is at 100%, enable `hash_chain_intact: true`
   in `audit_requirements` to make broken hash chains a CHAIN_BROKEN status
   instead of a warning.

### 14.2 For New Pipelines

Write the lineage contract alongside the Layer 1 propagation contract and the
pipeline definition. Review all three in the same PR. The lineage contract is
the "data flow specification" — it declares how fields are created, transformed,
and consumed, before any code runs.

### 14.3 For Pipelines Without Layer 1

Not supported. Layer 7 depends on Layer 1's `PropagationTracker` for backward
compatibility and on `_cc_propagation` for cross-checking. Adopt Layer 1 first.

### 14.4 Incremental Instrumentation

You do not need to instrument every phase on day one. The auditor's
`INCOMPLETE` status indicates which stages lack transformation records. This
makes incremental adoption visible and trackable:

```
Week 1: 3/7 stages instrumented (43% coverage)
Week 2: 5/7 stages instrumented (71% coverage)
Week 3: 7/7 stages instrumented (100% coverage)
Week 4: Enable hash_chain_intact: true
```

---

## 15. Consequences

### Positive

1. **Root cause analysis becomes systematic.** When a downstream output is
   wrong, follow the hash chain backward instead of reproducing the pipeline
   and adding print statements. The forensic trace narrows the search to a
   specific phase and operation.

2. **Unstamped mutations become detectable.** If a phase modifies a context
   field without calling `record_transformation()`, the hash chain breaks.
   This catches bugs that Layer 1 cannot — where the field is present but has
   the wrong value.

3. **Transformation intent is declared.** The lineage contract makes explicit
   what each phase does to each field (passthrough, transform, derive). This
   is reviewable in PRs and serves as living documentation of the data flow.

4. **Layer 1 compatibility preserved.** Layer 7 calls Layer 1's `stamp()`
   internally. Existing Layer 1 dashboards, queries, and alerts continue to
   work unchanged.

5. **Composable with other layers.** Layer 7's hash chain can be combined
   with Layer 6's budget tracking (did the transformation complete within its
   time budget?) or Layer 5's capability checking (did the phase have
   permission to perform this transformation?).

### Neutral

1. **Lineage metadata increases context size.** ~100 bytes per
   `TransformationRecord`, ~3.5 KB for a 7-phase pipeline tracking 5 fields.
   Negligible relative to typical context sizes but non-zero.

2. **Requires instrumentation discipline.** Every phase that touches a
   tracked field must call `record_transformation()`. Forgetting a call
   creates a gap that the auditor will report as `INCOMPLETE`.

3. **Two metadata keys in context.** `_cc_propagation` (Layer 1) and
   `_cc_lineage` (Layer 7) both live in the context dict. Handlers must not
   overwrite either. Both use the `_cc_` prefix to signal "internal."

### Negative

1. **Hash-based detection has limits.** The `_value_hash()` function uses
   `repr()`, which is not stable across Python versions for all types. If a
   value's `repr()` changes between Python 3.9 and 3.12, the hash chain
   breaks spuriously. Mitigation: test hash stability for tracked field types;
   consider canonical serialization (JSON) for complex types.

2. **Lineage does not capture *why*.** The `TransformationRecord` records
   *what* happened (operation, hashes) but not *why* the transformation was
   performed. The `description` field in the contract provides static
   documentation, but runtime reasons (e.g., "domain was reclassified because
   the project structure changed") are not captured.

3. **Graph traversal cost.** The `LineageGraph.ancestors()` and
   `descendants()` methods perform transitive traversal. For deeply nested
   pipelines with many fields, this could become expensive. Mitigation: cache
   the graph; limit traversal depth.

4. **Passthrough recording overhead.** Recording `passthrough` operations for
   fields that genuinely do not change adds records that carry no new
   information. However, these records are necessary for hash chain integrity
   — without them, the auditor cannot distinguish "unchanged" from
   "not instrumented."

---

## 16. Future Work

1. **OpenLineage event emission.** Translate `TransformationRecord` entries
   to OpenLineage JSON events for interoperability with Marquez, Atlan, and
   other lineage tools. This would allow ContextCore pipeline lineage to
   appear in the same lineage graph as ETL pipelines and ML model training.

2. **Lineage-aware rollback.** When a transformation introduces a bad value,
   automatically rollback the field to its last known-good value (the previous
   stage's output). This requires storing actual values, not just hashes —
   a significant design change with storage implications.

3. **Visual lineage graph in Grafana.** Build a Grafana panel (potentially
   via contextcore-owl) that renders the `LineageGraph` as an interactive
   DAG, with nodes colored by hash chain status (green for intact, red for
   broken, yellow for mutation detected). Clicking a node would show the
   `TransformationRecord` details.

4. **Cross-pipeline lineage.** Extend lineage chains to span multiple
   pipeline contracts. When pipeline A produces a field that pipeline B
   consumes, the lineage graph should show the cross-pipeline edge. This
   requires a lineage registry that multiple pipelines contribute to.

5. **Canonical serialization.** Replace `repr()` in `_value_hash()` with a
   canonical JSON serialization for complex types (dicts, lists). This would
   make hash chains stable across Python versions and implementation details
   of `__repr__`.

6. **Lineage-driven testing.** Use the lineage contract to generate test
   cases automatically: for each `transform` operation, generate a test that
   verifies the transformation logic produces the expected output hash from
   the expected input hash. This is property-based testing derived from the
   lineage declaration.

7. **Differential lineage.** Compare lineage histories between two pipeline
   runs to identify what changed. If run N produced correct output and run
   N+1 produced incorrect output, the differential lineage shows exactly
   which transformation records differ. This is the ContextCore analog of
   McSherry et al.'s differential dataflow.

---

## Appendix A: Planned File Inventory

| File | Purpose | Estimated Lines |
|---|---|---|
| `contracts/lineage/__init__.py` | Package exports | ~40 |
| `contracts/lineage/schema.py` | Pydantic models (LineageContract, LineageChainSpec, StageSpec) | ~180 |
| `contracts/lineage/tracker.py` | LineageTracker (record + retrieve transformations) | ~200 |
| `contracts/lineage/graph.py` | LineageGraph (DAG construction + traversal) | ~250 |
| `contracts/lineage/auditor.py` | ProvenanceAuditor (spec vs actual comparison) | ~300 |
| `contracts/lineage/otel.py` | OTel span event emission helpers | ~150 |
| `contracts/types.py` (modified) | +LineageStatus, +TransformOp enums | ~30 |
| `contracts/__init__.py` (modified) | +lineage exports | ~5 |
| **Total** | | **~1,155** |

Plus contract YAML and orchestrator wiring in startd8-sdk.

## Appendix B: Type Hierarchy

```
LineageContract
+-- schema_version: str
+-- contract_type: str                    ("data_lineage")
+-- pipeline_id: str
+-- description: str?
+-- lineage_chains: list[LineageChainSpec]
    +-- LineageChainSpec
        +-- chain_id: str
        +-- description: str?
        +-- field: str                    (dot-path of the tracked field)
        +-- stages: list[StageSpec]
        |   +-- StageSpec
        |       +-- phase: str
        |       +-- operation: TransformOp
        |       +-- input: str            (dot-path of input field)
        |       +-- output: str           (dot-path of output field)
        |       +-- expected_type: str?
        |       +-- description: str?
        +-- audit_requirements: AuditRequirements?
            +-- AuditRequirements
                +-- every_stage_stamped: bool     (default: true)
                +-- no_unstamped_mutations: bool  (default: true)
                +-- hash_chain_intact: bool       (default: true)

TransformationRecord (dataclass)
+-- phase: str
+-- operation: str                        (TransformOp value)
+-- input_hash: str | None
+-- output_hash: str
+-- timestamp: str                        (ISO 8601)
+-- input_field: str
+-- output_field: str

LineageAuditResult (dataclass)
+-- chain_id: str
+-- status: LineageStatus                 (verified/mutation_detected/chain_broken/incomplete)
+-- total_stages: int
+-- stamped_stages: int
+-- unstamped_mutations: list[UnstampedMutation]
+-- broken_links: list[BrokenLink]
+-- missing_stages: list[str]
+-- extra_stages: list[str]
+-- forensic_path: list[TransformationRecord]
+-- message: str
+-- coverage_pct: float                   (property: stamped/total * 100)

LineageGraph
+-- _nodes: dict[str, LineageNode]
+-- _edges: list[LineageEdge]
+-- ancestors(field_path) -> list[str]
+-- descendants(field_path) -> list[str]
+-- path_between(source, dest) -> list[TransformationRecord]?

ForensicReport (dataclass)
+-- chain_id: str
+-- field_path: str
+-- break_point: TransformationRecord?
+-- suspect_phase: str?
+-- suspect_operation: str?
+-- expected_hash: str?
+-- actual_hash: str?
+-- full_history: list[TransformationRecord]
+-- contributing_fields: list[str]
+-- recommendation: str
```

## Appendix C: Enum Additions to contracts/types.py

```python
class TransformOp(str, Enum):
    """Classification of transformation operations in a lineage chain."""

    PASSTHROUGH = "passthrough"
    CLASSIFY = "classify"
    TRANSFORM = "transform"
    DERIVE = "derive"
    AGGREGATE = "aggregate"
    FILTER = "filter"


class LineageStatus(str, Enum):
    """Lineage chain audit status."""

    VERIFIED = "verified"
    MUTATION_DETECTED = "mutation_detected"
    CHAIN_BROKEN = "chain_broken"
    INCOMPLETE = "incomplete"


# Convenience lists
TRANSFORM_OP_VALUES = [t.value for t in TransformOp]
LINEAGE_STATUS_VALUES = [s.value for s in LineageStatus]
```
