# Requirements: Concern 7e — Version Lineage (Enhanced Data Lineage/Provenance)

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Priority Scope:** P1-P3
**Companion doc:** [Context Correctness Extensions](../CONTEXT_CORRECTNESS_EXTENSIONS.md) (Concern 7 enhancement)
**Parent design:** [Context Correctness by Construction](../CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)
**Layer 7 design:** [Data Lineage Contracts — Layer 7](../LAYER7_DATA_LINEAGE_CONTRACTS_DESIGN.md)
**Implementation target:** `src/contextcore/contracts/propagation/` (schema, tracker, otel extensions)

---

## Problem Statement

Layer 1 (`PropagationChainSpec`) tracks whether a field propagated from source
to destination. Layer 7 (`LineageChainSpec`) extends this with full
transformation history — which phases touched a field, what operations were
performed, and whether the hash chain is intact.

Neither layer tracks **which version of the configuration** produced the field's
value. Data lineage records "this field was set by phase A." But framework
comparison reveals that *which version of the configuration was used* matters
equally:

- **LlamaIndex**: The same query against different index snapshots produces
  different retrieval results. Index version is not recorded alongside
  retrieved context, making results non-reproducible.

- **DSPy**: An optimized prompt replaces a previous one, but outputs generated
  by the old prompt are still flowing through the pipeline. Prompt version is
  not tracked alongside outputs, so downstream consumers cannot distinguish
  "generated with prompt v2" from "generated with prompt v3."

- **Guidance/Outlines**: Schema version changes alter output structure. Schema
  V1 outputs consumed by a downstream phase expecting V2 produce silent
  structural mismatches — the data parses, but the semantics are wrong.

The missing piece is `configuration_lineage` — tracking not just "set by
phase A" but "set by phase A using config version V." This enables forensic
queries ("this output was generated using prompt P with retrieval from index I
using model M") and version compatibility contracts (which config versions are
compatible with which consumers).

**Estimated implementation:** ~200 lines of production code + tests.

---

## Requirements

### REQ-7E-001: ConfigurationLineageEntry model

**Priority:** P1
**Description:** Define a `ConfigurationLineageEntry` Pydantic v2 model
representing a single configuration version reference within a provenance
record.

**Acceptance criteria:**
- Model uses `ConfigDict(extra="forbid")` consistent with existing schema models
- Fields:
  - `key: str` — configuration dimension name (e.g., `"index_version"`,
    `"prompt_version"`, `"model_version"`)
  - `source: str` — dot-path to the configuration source (e.g.,
    `"rag.index_snapshot"`, `"prompt.template.hash"`)
  - `version_hash: Optional[str]` — SHA-256 prefix of the configuration value
    at stamp time (computed via `_value_hash()`)
  - `version_label: Optional[str]` — human-readable version string (e.g.,
    `"v3.2.1"`, `"2026-02-15T10:00:00Z"`)
- Model validates `key` and `source` are non-empty strings
- Model is importable from `contextcore.contracts.propagation.schema`

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py`

---

### REQ-7E-002: Extend FieldProvenance with configuration_lineage

**Priority:** P1
**Description:** Add an optional `configuration_lineage` field to the existing
`FieldProvenance` dataclass so that every provenance stamp can carry version
metadata about the configuration that was active when the field was set.

**Acceptance criteria:**
- `FieldProvenance` gains a new field:
  `configuration_lineage: list[ConfigurationLineageEntry]` (default empty list)
- `FieldProvenance.to_dict()` serializes `configuration_lineage` entries
- Backward compatible: existing code that creates `FieldProvenance` without
  `configuration_lineage` continues to work (empty list default)
- Reconstruction from dict: a `from_dict()` classmethod or equivalent
  reconstructs `FieldProvenance` including `configuration_lineage`

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-7E-003: Extend PropagationTracker.stamp() with config versions

**Priority:** P1
**Description:** Extend the `PropagationTracker.stamp()` method to accept
optional configuration lineage entries so that callers can record which
configuration versions were active when a field was set.

**Acceptance criteria:**
- New optional parameter:
  `config_lineage: Optional[list[ConfigurationLineageEntry]] = None`
- When provided, entries are resolved: for each entry, `version_hash` is
  computed from the context value at `entry.source` using `_value_hash()` if
  not explicitly provided
- The resulting `FieldProvenance` includes the resolved
  `configuration_lineage`
- Debug log message includes configuration lineage keys when present
- Existing callers that omit `config_lineage` continue to work unchanged

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-7E-004: ProvenanceChainSpec extension with per-link configuration_lineage

**Priority:** P1
**Description:** Extend `PropagationChainSpec` (or introduce a new
`ProvenanceChainSpec` subclass) so that each link in a propagation chain can
declare expected configuration lineage dimensions.

**Acceptance criteria:**
- `ChainEndpoint` (or a new `ProvenanceChainLink` model) gains an optional
  `configuration_lineage: list[ConfigurationLineageEntry]` field (default
  empty list)
- This declares "at this point in the chain, these configuration dimensions
  should be stamped"
- The contract YAML representation matches the schema from the parent
  design document:
  ```yaml
  propagation_chains:
    - chain_id: "retrieval_to_generation"
      links:
        - phase: "retrieve"
          field: "retrieved_context"
          configuration_lineage:
            - key: "index_version"
              source: "rag.index_snapshot"
            - key: "embedding_model"
              source: "model.embedding.version"
  ```
- Backward compatible: existing chain specs without `configuration_lineage`
  parse and validate unchanged

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py`

---

### REQ-7E-005: Version lineage validation in check_chain()

**Priority:** P1
**Description:** Extend `PropagationTracker.check_chain()` to validate that
when a chain endpoint declares expected configuration lineage dimensions,
the corresponding `FieldProvenance` record includes matching lineage entries.

**Acceptance criteria:**
- For each `ChainEndpoint` with non-empty `configuration_lineage`:
  - Retrieve the `FieldProvenance` for that endpoint's field
  - For each declared lineage entry, verify that a matching `key` exists in the
    provenance's `configuration_lineage`
  - Missing lineage keys produce `ChainStatus.DEGRADED` with a descriptive
    message identifying the missing keys
- If no configuration lineage is declared on the endpoint, behavior is
  unchanged (no validation)
- `PropagationChainResult` message includes details about missing or
  mismatched version lineage

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-7E-006: OTel emission for version lineage stamps

**Priority:** P2
**Description:** Emit OTel span events when configuration lineage is stamped,
enabling TraceQL queries for forensic analysis of which config versions
produced which outputs.

**Acceptance criteria:**
- New span event `context.version_lineage.stamped` emitted when
  `PropagationTracker.stamp()` is called with non-empty `config_lineage`
- Span event attributes include:
  - `context.phase` — the stamping phase
  - `context.field` — the field being stamped
  - `context.lineage.key.{N}` — configuration dimension key (first 5)
  - `context.lineage.source.{N}` — configuration source path (first 5)
  - `context.lineage.hash.{N}` — version hash (first 5)
  - `context.lineage.count` — total number of lineage entries
- Follows existing `_HAS_OTEL` guard and `_add_span_event()` pattern from
  `propagation/otel.py`
- Degrades gracefully when OTel is not installed

**Affected files:**
- `src/contextcore/contracts/propagation/otel.py`
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-7E-007: OTel emission for version lineage validation results

**Priority:** P2
**Description:** Emit OTel span events when version lineage validation
detects missing or mismatched configuration versions, enabling alerting
and dashboard visibility for lineage gaps.

**Acceptance criteria:**
- New span event `context.version_lineage.validated` emitted after chain
  validation that includes configuration lineage checks
- Span event attributes include:
  - `context.chain_id` — the chain being validated
  - `context.lineage.expected_keys` — comma-separated list of expected keys
  - `context.lineage.found_keys` — comma-separated list of found keys
  - `context.lineage.missing_keys` — comma-separated list of missing keys
  - `context.lineage.complete` — boolean, all expected keys present
- New span event `context.version_lineage.mismatch` emitted when a version
  hash differs between declaration and actual stamp (future: version
  compatibility check)
- Both events follow `_HAS_OTEL` guard pattern

**Affected files:**
- `src/contextcore/contracts/propagation/otel.py`

---

### REQ-7E-008: Integration with Layer 5 (PostExecutionValidator)

**Priority:** P2
**Description:** Extend the `PostExecutionValidator` to include a version
consistency check that validates configuration lineage across the full chain
after all phases complete.

**Acceptance criteria:**
- New check in `PostExecutionValidator.validate()`: **version consistency**
  - For each provenance chain with configuration lineage declarations,
    verify that all links in the chain that share a configuration dimension
    key reference the same `version_hash` (or a compatible version per the
    contract)
  - Example: if `retrieve` and `generate` both declare `model_version`,
    verify they recorded the same model version hash
- Version inconsistency produces a new `RuntimeDiscrepancy` with
  `discrepancy_type="version_inconsistency"`
- `PostExecutionReport` gains an optional `version_consistency_issues: int`
  counter (default 0)
- Version inconsistencies are warnings by default, not failures (configurable)

**Affected files:**
- `src/contextcore/contracts/postexec/validator.py`

---

### REQ-7E-009: Integration with Layer 7 (RegressionGate)

**Priority:** P2
**Description:** Extend the `RegressionGate` to detect when configuration
version changes correlate with propagation regressions, enabling the gate
to flag version changes as a potential root cause.

**Acceptance criteria:**
- New gate check `version_change_regression`:
  - Compares baseline and current `PostExecutionReport` provenance chains
  - If a chain degrades from INTACT to DEGRADED/BROKEN AND the
    configuration lineage hashes differ between baseline and current,
    flag the version change as a contributing factor
  - Gate check message includes which configuration keys changed
- Gate check is advisory by default (does not fail the gate alone) but
  can be promoted to blocking via `thresholds`
- New threshold key: `version_change_on_regression: "advisory" | "blocking"`
  (default `"advisory"`)

**Affected files:**
- `src/contextcore/contracts/regression/gate.py`

---

### REQ-7E-010: Forensic query support (TraceQL patterns)

**Priority:** P2
**Description:** Document and validate TraceQL query patterns that enable
forensic investigation using version lineage data, answering "which config
version produced this output."

**Acceptance criteria:**
- Documented TraceQL patterns for:
  - "Find all outputs generated using a specific prompt version":
    `{ span.context.lineage.key.0 = "prompt_version" && span.context.lineage.hash.0 = "abc123" }`
  - "Find chains where index version changed between baseline and current":
    `{ span.context.version_lineage.mismatch = true && span.context.lineage.key.0 = "index_version" }`
  - "Find all phases that used a specific model version":
    `{ name = "context.version_lineage.stamped" && span.context.lineage.key.0 = "model_version" }`
  - "Correlate regression with version change":
    `{ span.context.chain_status = "broken" } && { name = "context.version_lineage.mismatch" }`
- Patterns are validated against the OTel attribute names from REQ-7E-006
  and REQ-7E-007
- Patterns are documented in the requirements doc and referenced from
  `docs/semantic-conventions.md`

**Affected files:**
- `docs/semantic-conventions.md` (reference addition)

---

### REQ-7E-011: Version compatibility contract

**Priority:** P3
**Description:** Define an optional `VersionCompatibilitySpec` that declares
which configuration versions are compatible with which consumers, enabling
proactive detection of version mismatches before they cause silent
degradation.

**Acceptance criteria:**
- New Pydantic v2 model `VersionCompatibilitySpec` with `ConfigDict(extra="forbid")`
- Fields:
  - `config_key: str` — configuration dimension (e.g., `"prompt_version"`)
  - `compatible_versions: list[str]` — version hashes or labels considered
    compatible
  - `breaking_versions: list[str]` — version hashes or labels known to be
    incompatible
  - `on_incompatible: ConstraintSeverity` — severity when incompatible version
    detected (default `WARNING`)
  - `description: Optional[str]` — human-readable explanation
- Contract YAML representation:
  ```yaml
  version_compatibility:
    - config_key: "prompt_version"
      compatible_versions: ["sha256:abc123", "sha256:def456"]
      breaking_versions: ["sha256:old789"]
      on_incompatible: WARNING
      description: "Prompt v2 and v3 are compatible; v1 outputs are not"
  ```
- Compatibility check runs during `check_chain()` when a
  `VersionCompatibilitySpec` is present for a configuration key
- Incompatible version detection produces `ChainStatus.DEGRADED` or
  `ChainStatus.BROKEN` depending on severity

**Affected files:**
- `src/contextcore/contracts/propagation/schema.py`
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-7E-012: Auto-resolve configuration lineage from context

**Priority:** P3
**Description:** Provide a convenience method that automatically resolves
configuration lineage entries from the current context dict, so callers do
not need to manually compute version hashes for common patterns.

**Acceptance criteria:**
- New method `PropagationTracker.resolve_config_lineage()` that:
  - Takes a list of `ConfigurationLineageEntry` and a context dict
  - For each entry, resolves `entry.source` from the context using
    `_resolve_field()`
  - Computes `version_hash` via `_value_hash()` from the resolved value
  - Returns a new list of `ConfigurationLineageEntry` with hashes populated
- If a source path does not resolve, the entry is included with
  `version_hash=None` and a debug log is emitted
- `stamp()` uses this method internally when `config_lineage` is provided
  without explicit hashes

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-7E-013: Provenance chain forensic query helper

**Priority:** P3
**Description:** Provide a programmatic helper that reconstructs the full
configuration lineage trail for a field, answering "this output was generated
using prompt P with retrieval from index I using model M."

**Acceptance criteria:**
- New method `PropagationTracker.get_lineage_trail()` that:
  - Takes a context dict and a field path
  - Returns a `LineageTrail` dataclass containing:
    - `field: str` — the queried field
    - `origin_phase: str` — from `FieldProvenance`
    - `set_at: str` — from `FieldProvenance`
    - `value_hash: str` — from `FieldProvenance`
    - `configuration_versions: dict[str, str]` — mapping of config key to
      version hash (e.g., `{"prompt_version": "abc123", "model_version": "def456"}`)
  - Returns `None` if the field has no provenance stamp
- `LineageTrail` has a `summary()` method that produces a human-readable
  string: `"field 'generated_output' set by phase 'generate' at
  2026-02-15T10:00:00Z using prompt_version=abc123, model_version=def456"`

**Affected files:**
- `src/contextcore/contracts/propagation/tracker.py`

---

### REQ-7E-014: Layer 7 LineageTracker integration

**Priority:** P3
**Description:** When Layer 7 (`LineageTracker`) is implemented, version
lineage from Layer 1's `FieldProvenance` should propagate into Layer 7's
`TransformationRecord`, ensuring that the full transformation history
includes configuration version metadata at each stage.

**Acceptance criteria:**
- `TransformationRecord` (Layer 7, when implemented) gains an optional
  `configuration_lineage: list[ConfigurationLineageEntry]` field
- `LineageTracker.record_transformation()` accepts optional
  `config_lineage` parameter, forwarding to the transformation record
- The `ProvenanceAuditor` (Layer 7) can compare configuration versions
  across transformation stages, detecting "prompt version changed mid-chain"
- This requirement is forward-looking: implementation deferred until Layer 7
  build-out, but the `ConfigurationLineageEntry` model is designed for reuse

**Affected files:**
- `src/contextcore/contracts/lineage/tracker.py` (future)
- `src/contextcore/contracts/lineage/auditor.py` (future)

---

## Contract Schema

The version lineage contract extends existing propagation chain YAML with
`configuration_lineage` at each chain endpoint:

```yaml
schema_version: "0.2.0"
pipeline_id: "retrieval_augmented_generation"
description: "RAG pipeline with version lineage tracking"

phases:
  retrieve:
    description: "Retrieve context from vector index"
    entry:
      required:
        - name: user_query
          severity: blocking
    exit:
      required:
        - name: retrieved_context
          severity: blocking

  generate:
    description: "Generate output using retrieved context"
    entry:
      required:
        - name: retrieved_context
          severity: blocking
    exit:
      required:
        - name: generated_output
          severity: blocking

propagation_chains:
  - chain_id: "retrieval_to_generation"
    description: "Track context from retrieval through generation with config versions"
    source:
      phase: "retrieve"
      field: "retrieved_context"
      configuration_lineage:
        - key: "index_version"
          source: "rag.index_snapshot"
        - key: "embedding_model"
          source: "model.embedding.version"
    destination:
      phase: "generate"
      field: "generated_output"
      configuration_lineage:
        - key: "prompt_version"
          source: "prompt.template.hash"
        - key: "model_version"
          source: "model.generation.version"
    severity: warning

# Optional: version compatibility declarations
version_compatibility:
  - config_key: "prompt_version"
    compatible_versions: ["sha256:abc123de", "sha256:def456ab"]
    breaking_versions: ["sha256:old789cd"]
    on_incompatible: warning
    description: "Prompt v2 and v3 produce compatible outputs; v1 outputs lack required fields"

  - config_key: "index_version"
    compatible_versions: []  # Any version is acceptable
    breaking_versions: []
    on_incompatible: advisory
    description: "Index version changes are expected; track for forensics only"
```

---

## Integration Points

Version lineage plugs into the existing 7-layer defense-in-depth architecture
without adding new layers. It extends existing primitives at multiple layers:

### Layer 1: Context Contracts (Declarations)

- `ConfigurationLineageEntry` model added to `propagation/schema.py`
- `ChainEndpoint` extended with optional `configuration_lineage`
- `FieldProvenance` extended with `configuration_lineage` list
- `PropagationTracker.stamp()` extended with `config_lineage` parameter

### Layer 4: Runtime Boundary Checks

- `RuntimeBoundaryGuard` (existing) can leverage version lineage stamps
  to detect mid-pipeline configuration changes at runtime
- No structural changes required; the guard already delegates to
  `BoundaryValidator` which reads `FieldProvenance`

### Layer 5: Post-Execution Validation

- `PostExecutionValidator` gains a version consistency check (REQ-7E-008)
- Validates that shared configuration dimensions reference the same version
  hash across chain links
- New `RuntimeDiscrepancy.discrepancy_type="version_inconsistency"`

### Layer 6: Observability and Alerting

- OTel span events (REQ-7E-006, REQ-7E-007) enable Grafana alerting on
  version lineage gaps and mismatches
- Alert rule pattern: `count_over_time({} | json | lineage_complete="false" [5m]) > 0`

### Layer 7: Regression Prevention

- `RegressionGate` gains version change correlation check (REQ-7E-009)
- Detects when propagation regressions coincide with configuration version
  changes, providing root-cause attribution

### Relationship to Concern 11 (Prompt and Configuration Evolution)

Concern 7e (Version Lineage) and Concern 11 (Configuration Evolution) are
complementary:

- **Concern 11** manages the *lifecycle* of configurations: version history,
  promotion policies, evolution rules, and gated deployment.
- **Concern 7e** tracks *which version was active* when a specific field was
  produced, enabling forensic reconstruction after the fact.

Concern 11 answers: "Is it safe to promote prompt v4?" Concern 7e answers:
"This output was generated with prompt v3 — is that still the current version?"

---

## Test Requirements

### Unit tests (~30 tests estimated)

1. **ConfigurationLineageEntry model validation** (3 tests)
   - Valid entry with all fields
   - Rejection of empty `key` or `source`
   - Rejection of extra fields (`extra="forbid"`)

2. **FieldProvenance with configuration_lineage** (4 tests)
   - Default empty list when not provided (backward compat)
   - Serialization via `to_dict()` includes lineage entries
   - Reconstruction from dict preserves lineage
   - Multiple lineage entries with different keys

3. **PropagationTracker.stamp() with config lineage** (5 tests)
   - Stamp without config lineage (backward compat, no regression)
   - Stamp with explicit config lineage entries
   - Auto-resolution of `version_hash` from context
   - Source path not found in context produces `version_hash=None`
   - Multiple config lineage entries on single stamp

4. **check_chain() with configuration lineage validation** (5 tests)
   - Chain with no lineage declarations passes unchanged
   - Chain with lineage declarations, all keys present: INTACT
   - Chain with lineage declarations, missing keys: DEGRADED
   - Chain with lineage declarations, field has no provenance: DEGRADED
   - Message includes names of missing lineage keys

5. **OTel emission** (4 tests)
   - `context.version_lineage.stamped` event emitted with correct attributes
   - `context.version_lineage.validated` event emitted after chain check
   - No OTel emission when `_HAS_OTEL` is False
   - Attribute count matches lineage entry count (capped at 5)

6. **PostExecutionValidator version consistency** (4 tests)
   - No version compatibility issues when all hashes match
   - Version inconsistency detected when hashes differ
   - `RuntimeDiscrepancy` with `discrepancy_type="version_inconsistency"`
   - Report `version_consistency_issues` counter incremented

7. **RegressionGate version change correlation** (3 tests)
   - No flag when chain status unchanged
   - Advisory flag when chain degrades and config version changed
   - Blocking flag when threshold set to `"blocking"`

8. **get_lineage_trail() forensic helper** (2 tests)
   - Returns populated `LineageTrail` with configuration versions
   - Returns `None` for field without provenance

### Integration tests

- End-to-end: stamp with lineage, validate chain, run post-exec, run
  regression gate — verify version lineage flows through all layers
- YAML contract with `configuration_lineage`: parse, validate, stamp,
  check chain — verify round-trip

---

## Non-Requirements

The following are explicitly **out of scope** for this concern:

1. **Configuration storage or management** — Version lineage tracks which
   version was used, not where configurations are stored or how they are
   deployed. Configuration management is the responsibility of the runtime
   framework (DSPy's optimizer, LlamaIndex's index manager, etc.).

2. **Prompt optimization or evaluation** — Version lineage records prompt
   version hashes for forensics. It does not evaluate prompt quality, run
   A/B tests, or decide which prompt version is better. See Concern 13
   (Evaluation-Gated Propagation) for evaluation contracts.

3. **Model registry integration** — Version lineage records `model_version`
   hashes but does not integrate with model registries (MLflow, Weights &
   Biases, etc.). A future adapter could bridge registry metadata into
   `ConfigurationLineageEntry.version_label`.

4. **Automatic rollback** — Detecting that a version change caused a
   regression does not trigger automatic rollback. The `RegressionGate`
   reports the correlation; a human or orchestrator decides whether to
   roll back.

5. **Cross-pipeline version coordination** — This concern tracks version
   lineage within a single pipeline. Cross-pipeline version coordination
   (e.g., "pipeline A's output was generated with model v2, pipeline B
   expects model v3 outputs") requires Concern 11 (Configuration Evolution)
   contracts.

6. **Runtime version rotation detection** — Detecting that a model version
   rotated mid-pipeline (e.g., a cloud provider updated the model between
   two API calls) is a Concern 10 (Checkpoint Recovery Integrity) problem
   combined with Concern 4e (Temporal Staleness). Version lineage records
   what was used, not whether it changed during use.

7. **Backward-incompatible changes to FieldProvenance** — The extended
   `FieldProvenance` must remain backward compatible. Code that creates
   `FieldProvenance` without `configuration_lineage` must continue to work.
   The new field uses a default empty list, not a required parameter.
