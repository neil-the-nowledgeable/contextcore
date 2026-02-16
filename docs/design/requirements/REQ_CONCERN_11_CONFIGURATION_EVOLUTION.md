# Requirements: Concern 11 -- Prompt and Configuration Evolution

**Status:** Draft
**Date:** 2026-02-15
**Priority:** Tier 2 (medium value, medium complexity)
**Companion doc:** [Context Correctness Extensions](../CONTEXT_CORRECTNESS_EXTENSIONS.md) -- Concern 11
**Estimated implementation:** ~200 lines + tests (reuses EvolutionTracker pattern from Layer 2)

---

## Problem Statement

Schema Evolution (Concern 2) covers data schema drift between services. Agent
pipelines have a parallel problem on the *control plane*: prompts,
configurations, model parameters, and system instructions evolve over time.

A prompt version change can silently degrade output quality. A model parameter
change alters behavior. A system instruction edit shifts decision-making. The
output parses correctly (schema is fine) but is semantically worse (prompt
degraded).

None of this is tracked as schema evolution. The prompt is not a "schema" in the
traditional sense -- it is a *behavior specification* that affects output quality
without affecting output structure.

**CS parallel:** Behavioral subtyping (Liskov Substitution Principle) -- a new
prompt version is a behavioral subtype of the old if it produces outputs that
satisfy all downstream expectations. The contract declares what "all downstream
expectations" means.

**Framework evidence:**
- **DSPy**: Signature versioning + optimization loops track before/after metrics,
  but optimized prompts are promoted without formal governance gates.
- **Guidance/Outlines**: Schema versions constrain output structure, but schema
  version changes are not tracked as evolution events with compatibility analysis.
- **LangGraph**: State schemas can evolve between graph versions, but no contract
  declares which schema versions are compatible with which graph versions.

---

## Requirements

### Pydantic Models

#### REQ-11-001: ConfigurationVersion model

| Field | Value |
|-------|-------|
| **ID** | REQ-11-001 |
| **Priority** | P1 |
| **Description** | Create a `ConfigurationVersion` Pydantic model representing a single versioned snapshot of a configuration artifact (prompt template, model config, system instruction). |
| **Acceptance Criteria** | 1. Model has fields: `version` (str, semver format, required), `hash` (str, sha256 content hash, required), `deployed_at` (str, ISO 8601 timestamp, required), `change_description` (Optional[str]), `author` (Optional[str]). 2. Uses `ConfigDict(extra="forbid")`. 3. `version` has `min_length=1` constraint. 4. `hash` validates sha256 prefix format (starts with `sha256:`). 5. Model serializes to/from YAML via `model_validate()`. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py` (new) |

#### REQ-11-002: ConfigurationType enum

| Field | Value |
|-------|-------|
| **ID** | REQ-11-002 |
| **Priority** | P1 |
| **Description** | Define a `ConfigurationType` string enum for classifying configuration artifacts. |
| **Acceptance Criteria** | 1. Values: `prompt_template`, `model_config`, `system_instruction`, `tool_config`, `guard_config`. 2. Inherits from `str, Enum` following the pattern in `contracts/types.py`. 3. Added to `contracts/types.py` as the canonical enum. 4. Convenience list `CONFIGURATION_TYPE_VALUES` exported alongside existing value lists. |
| **Affected Files** | `src/contextcore/contracts/types.py` |

#### REQ-11-003: ConfigurationEntry model

| Field | Value |
|-------|-------|
| **ID** | REQ-11-003 |
| **Priority** | P1 |
| **Description** | Create a `ConfigurationEntry` Pydantic model representing a tracked configuration with its version history. |
| **Acceptance Criteria** | 1. Fields: `config_id` (str, required, `min_length=1`), `type` (ConfigurationType, required), `current_version` (str, required, semver format), `version_history` (list[ConfigurationVersion], default empty), `description` (Optional[str]), `owner` (Optional[str]). 2. Uses `ConfigDict(extra="forbid")`. 3. Validates that `current_version` appears in `version_history` when history is non-empty (model_validator, mode="after"). 4. Version history is ordered newest-first by convention (not enforced). |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py` |

#### REQ-11-004: PromotionPolicy enum

| Field | Value |
|-------|-------|
| **ID** | REQ-11-004 |
| **Priority** | P1 |
| **Description** | Define a `PromotionPolicy` string enum for configuration promotion strategies. |
| **Acceptance Criteria** | 1. Values: `gated_promotion` (requires quality/regression gates), `backward_compatible` (requires schema compatibility), `unrestricted` (any change allowed, audit-only). 2. Inherits from `str, Enum`. 3. Defined in `src/contextcore/contracts/config_evolution/schema.py` (local to this contract type, not in central `types.py` -- it is concern-specific). |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py` |

#### REQ-11-005: PromotionRequirement model

| Field | Value |
|-------|-------|
| **ID** | REQ-11-005 |
| **Priority** | P1 |
| **Description** | Create a `PromotionRequirement` Pydantic model for individual gate requirements within a promotion rule. |
| **Acceptance Criteria** | 1. Fields: `quality_threshold` (Optional[float], 0.0-1.0 range), `regression_check` (bool, default False), `schema_compatible` (bool, default False), `output_quality_check` (bool, default False), `human_approval` (Literal["required", "optional", "none"], default "none"). 2. Uses `ConfigDict(extra="forbid")`. 3. At least one requirement must be active (model_validator ensures not all fields are at default/None). |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py` |

#### REQ-11-006: PromotionRule model

| Field | Value |
|-------|-------|
| **ID** | REQ-11-006 |
| **Priority** | P1 |
| **Description** | Create a `PromotionRule` Pydantic model that maps a configuration scope to a promotion policy with requirements. |
| **Acceptance Criteria** | 1. Fields: `rule_id` (str, required, `min_length=1`), `scope` (str, required -- matches against `ConfigurationEntry.type` value or `config_id` prefix), `policy` (PromotionPolicy, required), `requirements` (PromotionRequirement, required), `description` (Optional[str]). 2. Uses `ConfigDict(extra="forbid")`. 3. Follows the `SchemaEvolutionRule` pattern from `schema_compat/schema.py` (rule_id, scope, policy structure). |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py` |

#### REQ-11-007: ConfigurationEvolutionSpec top-level model

| Field | Value |
|-------|-------|
| **ID** | REQ-11-007 |
| **Priority** | P1 |
| **Description** | Create `ConfigurationEvolutionSpec` as the root Pydantic model for configuration evolution contract YAML files. |
| **Acceptance Criteria** | 1. Fields: `schema_version` (str, required), `contract_type` (Literal["configuration_evolution"], default "configuration_evolution"), `description` (Optional[str]), `configurations` (list[ConfigurationEntry], default empty), `evolution_rules` (list[PromotionRule], default empty). 2. Uses `ConfigDict(extra="forbid")`. 3. Validates via `model_validate(yaml.safe_load(...))`. 4. Follows the `SchemaCompatibilitySpec` pattern (schema_version, contract_type discriminator, lists of entries and rules). 5. Contract type literal acts as discriminator for future multi-contract loader. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py` |

### Tracker

#### REQ-11-008: ConfigurationEvolutionTracker class

| Field | Value |
|-------|-------|
| **ID** | REQ-11-008 |
| **Priority** | P1 |
| **Description** | Create a `ConfigurationEvolutionTracker` class that detects configuration changes, classifies them against promotion rules, and produces structured results. |
| **Acceptance Criteria** | 1. Constructor accepts a `ConfigurationEvolutionSpec`. 2. `check_promotion(config_id, old_version, new_version) -> PromotionCheckResult` -- detects changes between two ConfigurationVersion snapshots and validates against the applicable PromotionRule. 3. `find_rule(config_id, config_type) -> Optional[PromotionRule]` -- finds the first rule whose scope matches the config_id or config_type value (prefix match, same as `EvolutionTracker._find_rule`). 4. `classify_change(old_version, new_version) -> ConfigurationChange` -- produces a structured change record (hash changed, version changed, etc.). 5. Follows the `EvolutionTracker` pattern from `schema_compat/evolution.py`. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/tracker.py` (new) |

#### REQ-11-009: PromotionCheckResult model

| Field | Value |
|-------|-------|
| **ID** | REQ-11-009 |
| **Priority** | P1 |
| **Description** | Create a `PromotionCheckResult` Pydantic model for the output of promotion gate checks. |
| **Acceptance Criteria** | 1. Fields: `approved` (bool), `config_id` (str), `old_version` (str), `new_version` (str), `applicable_rule` (Optional[str] -- rule_id if matched), `gates_passed` (list[str] -- names of gates that passed), `gates_failed` (list[str] -- names of gates that failed), `requires_human_approval` (bool, default False), `message` (str). 2. Uses `ConfigDict(extra="forbid")`. 3. Follows the `EvolutionCheckResult` pattern (compatible/approved, service/config_id, versions, rule reference, message). |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py` |

#### REQ-11-010: ConfigurationChange model

| Field | Value |
|-------|-------|
| **ID** | REQ-11-010 |
| **Priority** | P2 |
| **Description** | Create a `ConfigurationChange` Pydantic model that classifies the nature of a configuration change. |
| **Acceptance Criteria** | 1. Fields: `change_type` (Literal["hash_changed", "version_bumped", "type_changed", "new_config", "rollback"]), `config_id` (str), `old_hash` (Optional[str]), `new_hash` (Optional[str]), `old_version` (Optional[str]), `new_version` (Optional[str]), `is_rollback` (bool, default False -- True when new_version < old_version by semver). 2. Uses `ConfigDict(extra="forbid")`. 3. `is_rollback` is computed (model_validator) by comparing semver ordering when both versions are present. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py` |

### Loader

#### REQ-11-011: ConfigEvolutionLoader with ClassVar cache

| Field | Value |
|-------|-------|
| **ID** | REQ-11-011 |
| **Priority** | P1 |
| **Description** | Create a `ConfigEvolutionLoader` class that loads and caches `ConfigurationEvolutionSpec` from YAML files. |
| **Acceptance Criteria** | 1. `_cache: ClassVar[dict[str, ConfigurationEvolutionSpec]]` -- class-level cache keyed by resolved file path. 2. `clear_cache()` class method clears the cache. 3. `load(path: Path) -> ConfigurationEvolutionSpec` -- loads YAML, validates with `model_validate`, caches result. 4. `load_from_string(yaml_str: str) -> ConfigurationEvolutionSpec` -- convenience method for testing (no caching). 5. Raises `FileNotFoundError` for missing files, `yaml.YAMLError` for invalid YAML, `pydantic.ValidationError` for schema violations. 6. Follows `SchemaCompatLoader` pattern exactly. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/loader.py` (new) |

### OTel Emission

#### REQ-11-012: OTel span event emission for configuration changes

| Field | Value |
|-------|-------|
| **ID** | REQ-11-012 |
| **Priority** | P1 |
| **Description** | Create OTel emission helpers for configuration evolution events. |
| **Acceptance Criteria** | 1. `emit_config_evolution_check(result: PromotionCheckResult)` -- emits span event `context.config.evolution` with attributes: `config.id`, `config.old_version`, `config.new_version`, `config.approved`, `config.applicable_rule`, `config.gates_passed_count`, `config.gates_failed_count`, `config.requires_human_approval`, `config.message`. 2. `emit_config_change_detected(change: ConfigurationChange)` -- emits span event `context.config.change` with attributes: `config.id`, `config.change_type`, `config.old_hash`, `config.new_hash`, `config.is_rollback`. 3. Uses `_HAS_OTEL` guard pattern from `schema_compat/otel.py`. 4. Uses `_add_span_event()` internal helper. 5. Logs at `WARNING` level for failed promotions and rollbacks, `DEBUG` for approved changes. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/otel.py` (new) |

### Layer 7 Integration

#### REQ-11-013: RegressionGate integration for configuration promotion

| Field | Value |
|-------|-------|
| **ID** | REQ-11-013 |
| **Priority** | P2 |
| **Description** | Extend the Layer 7 `RegressionGate.check()` method to accept an optional `PromotionCheckResult` and fail the gate when configuration promotions are not approved. |
| **Acceptance Criteria** | 1. `RegressionGate.check()` accepts optional `config_promotion: Optional[PromotionCheckResult]` parameter. 2. When provided and `approved=False`, adds a failing `GateCheck` with `check_id="config_promotion"`. 3. When provided and `requires_human_approval=True` and no human approval signal is present, adds a failing `GateCheck` with `check_id="config_human_approval"`. 4. Existing gate checks (completeness, health, drift, blocking failures) are unaffected. 5. The new parameter is fully optional -- omitting it preserves backward compatibility. |
| **Affected Files** | `src/contextcore/contracts/regression/gate.py` |

### Pre-flight Validation

#### REQ-11-014: Pre-flight validation of configuration contracts

| Field | Value |
|-------|-------|
| **ID** | REQ-11-014 |
| **Priority** | P2 |
| **Description** | Validate configuration evolution contracts at load time (pre-flight) to catch structural issues before runtime. |
| **Acceptance Criteria** | 1. For each `ConfigurationEntry` with non-empty `version_history`, validate that `current_version` appears in the history. 2. For each `PromotionRule`, validate that the scope matches at least one configuration entry's `type` or `config_id`. 3. Warn (log at WARNING level) about orphaned rules (rules whose scope matches no configuration). 4. Warn about configurations with no applicable promotion rule (ungoverned configs). 5. Validation runs automatically during `ConfigEvolutionLoader.load()` after Pydantic validation succeeds. 6. Validation failures are non-blocking (warnings, not exceptions) to allow incremental contract adoption. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/loader.py` |

### Version History

#### REQ-11-015: Version history querying

| Field | Value |
|-------|-------|
| **ID** | REQ-11-015 |
| **Priority** | P2 |
| **Description** | Provide query methods on `ConfigurationEvolutionTracker` for inspecting version history. |
| **Acceptance Criteria** | 1. `get_current_version(config_id: str) -> Optional[ConfigurationVersion]` -- returns the version matching `current_version` from the entry's history. 2. `get_version_history(config_id: str) -> list[ConfigurationVersion]` -- returns the full ordered history for a config_id. 3. `get_version_at(config_id: str, timestamp: str) -> Optional[ConfigurationVersion]` -- returns the version that was deployed at the given ISO 8601 timestamp (latest `deployed_at` <= timestamp). 4. Returns `None` / empty list when config_id is not found. 5. Does not require external storage -- operates on the in-memory `ConfigurationEvolutionSpec`. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/tracker.py` |

### Module Structure

#### REQ-11-016: Package __init__.py with public API

| Field | Value |
|-------|-------|
| **ID** | REQ-11-016 |
| **Priority** | P1 |
| **Description** | Create the `config_evolution` package with a public API following the `schema_compat` module pattern. |
| **Acceptance Criteria** | 1. `src/contextcore/contracts/config_evolution/__init__.py` exports: `ConfigurationEvolutionSpec`, `ConfigurationEntry`, `ConfigurationVersion`, `PromotionRule`, `PromotionRequirement`, `PromotionPolicy`, `PromotionCheckResult`, `ConfigurationChange`, `ConfigEvolutionLoader`, `ConfigurationEvolutionTracker`, `emit_config_evolution_check`, `emit_config_change_detected`. 2. `__all__` list matches imports. 3. Follows the `schema_compat/__init__.py` grouping pattern (Schema, Loader, Tracker, OTel). |
| **Affected Files** | `src/contextcore/contracts/config_evolution/__init__.py` (new) |

### Compatibility

#### REQ-11-017: Compatibility with existing EvolutionTracker pattern

| Field | Value |
|-------|-------|
| **ID** | REQ-11-017 |
| **Priority** | P2 |
| **Description** | Ensure `ConfigurationEvolutionTracker` follows the same structural pattern as `EvolutionTracker` so that future unification is straightforward. |
| **Acceptance Criteria** | 1. Constructor signature: `__init__(self, contract: ConfigurationEvolutionSpec)`. 2. Primary check method returns a result model (not a dict). 3. Rule-finding logic uses scope prefix matching (same as `EvolutionTracker._find_rule`). 4. Logging follows the same `logger.warning` / `logger.debug` pattern. 5. No import dependency on `schema_compat` module -- the pattern is replicated, not inherited, to keep the modules independently deployable. 6. A future `AbstractEvolutionTracker` base class could unify both without breaking either. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/tracker.py` |

#### REQ-11-018: Rollback detection

| Field | Value |
|-------|-------|
| **ID** | REQ-11-018 |
| **Priority** | P3 |
| **Description** | Detect when a configuration change is a rollback (reverting to a previous version) and flag it in the change classification and OTel emission. |
| **Acceptance Criteria** | 1. `ConfigurationChange.is_rollback` is `True` when `new_version` is strictly less than `old_version` by semver ordering. 2. Semver comparison uses tuple-based `(major, minor, patch)` parsing -- does not require external `semver` library. 3. Rollback changes emit at `WARNING` log level and include `config.is_rollback=true` in the OTel span event. 4. Rollback does not automatically fail promotion -- it is an informational signal. The promotion rule's policy determines whether a rollback is allowed. |
| **Affected Files** | `src/contextcore/contracts/config_evolution/schema.py`, `src/contextcore/contracts/config_evolution/otel.py` |

---

## Contract Schema

Example YAML contract file (`config-evolution.contract.yaml`):

```yaml
configuration_evolution:
  schema_version: "1.0.0"
  contract_type: "configuration_evolution"
  description: "Configuration evolution contract for RAG pipeline"

  configurations:
    - config_id: "generation_prompt"
      type: "prompt_template"
      current_version: "v3.2.1"
      description: "Primary generation prompt for document synthesis"
      owner: "ml-team"
      version_history:
        - version: "v3.2.1"
          hash: "sha256:abc123def456789012345678901234567890123456789012345678901234"
          deployed_at: "2026-02-15T10:00:00Z"
          change_description: "Added domain-specific constraints"
          author: "alice"
        - version: "v3.2.0"
          hash: "sha256:def456abc789012345678901234567890123456789012345678901234567"
          deployed_at: "2026-02-10T10:00:00Z"
          change_description: "Initial release"

    - config_id: "retrieval_parameters"
      type: "model_config"
      current_version: "v2.0.0"
      description: "Embedding model and retrieval parameters"
      version_history:
        - version: "v2.0.0"
          hash: "sha256:789abc012345678901234567890123456789012345678901234567890123"
          deployed_at: "2026-02-12T14:00:00Z"
          change_description: "Switched to new embedding model"

    - config_id: "safety_guardrails"
      type: "guard_config"
      current_version: "v1.1.0"
      description: "Output safety guardrail configuration"

  evolution_rules:
    - rule_id: "prompt_promotion"
      scope: "prompt_template"
      policy: "gated_promotion"
      requirements:
        quality_threshold: 0.85
        regression_check: true
        human_approval: "optional"
      description: "Prompt changes must pass quality gate and regression check"

    - rule_id: "model_config_change"
      scope: "model_config"
      policy: "backward_compatible"
      requirements:
        schema_compatible: true
        output_quality_check: true
      description: "Model config changes must maintain output quality"

    - rule_id: "guard_config_change"
      scope: "guard_config"
      policy: "gated_promotion"
      requirements:
        quality_threshold: 0.95
        regression_check: true
        human_approval: "required"
      description: "Safety guardrail changes require strict review"
```

---

## Integration Points

### Fit into Existing Layers 1-7

Configuration Evolution contracts plug into the existing defense-in-depth
architecture without adding new layers:

| Layer | How Configuration Evolution Integrates |
|-------|---------------------------------------|
| **Layer 1: Declarations** | `ConfigurationEvolutionSpec` is a new YAML contract type alongside `PropagationChainSpec` and `SchemaCompatibilitySpec`. Declared in contract files, loaded by `ConfigEvolutionLoader`. |
| **Layer 2: Static Analysis** | `ConfigurationEvolutionTracker.classify_change()` performs static analysis of version differences, analogous to `EvolutionTracker.compare_versions()`. Pre-flight validation checks contract structural integrity at load time. |
| **Layer 3: Pre-Flight Verification** | Loader runs pre-flight checks: current_version exists in history, rules have matching configurations, no orphaned rules. |
| **Layer 4: Runtime Boundary Checks** | Not directly integrated. Configuration evolution is a design-time / CI-time concern, not a per-request boundary check. Future extension: `RuntimeBoundaryGuard` could stamp `config.prompt_version` at phase entry and validate it has not changed mid-execution. |
| **Layer 5: Post-Execution Validation** | Not directly integrated. Could extend `PostExecutionReport` with a `config_versions_used` field for forensic lineage. |
| **Layer 6: Observability** | OTel span events (`context.config.evolution`, `context.config.change`) enable Grafana alerting on unapproved promotions, rollbacks, and gate failures. |
| **Layer 7: Regression Prevention** | `RegressionGate.check()` extended to accept `PromotionCheckResult`. Configuration promotions that fail gates block CI merge, same as completeness or health regressions. |

### Relationship to Schema Evolution (Layer 2)

Configuration Evolution is the *control plane* analog of Schema Evolution:

| Aspect | Schema Evolution (Concern 2) | Configuration Evolution (Concern 11) |
|--------|------------------------------|--------------------------------------|
| **What evolves** | Data field schemas between services | Prompts, model configs, system instructions |
| **Drift signal** | Fields added/removed/changed | Hash changed, version bumped, rollback |
| **Policy types** | additive_only, backward_compatible, full | gated_promotion, backward_compatible, unrestricted |
| **Rule matching** | Scope prefix on service name | Scope prefix on config_type or config_id |
| **Gate integration** | DriftReport fed to RegressionGate | PromotionCheckResult fed to RegressionGate |
| **OTel event** | `schema.compatibility.*` | `context.config.*` |

### Relationship to Data Lineage (Concern 7 Enhancement)

The `configuration_lineage` extension in Concern 7 records *which* configuration
version produced *which* output. Configuration Evolution (Concern 11) governs
*whether* a configuration version is allowed to be deployed. Together they form
a complete lifecycle: governance (11) controls what gets deployed, lineage (7)
tracks what was used.

---

## Test Requirements

### Unit Tests

Tests should be placed in `tests/unit/contextcore/contracts/config_evolution/`.

| Test File | Coverage Target | Estimated Count |
|-----------|----------------|-----------------|
| `test_schema.py` | All Pydantic models: validation, extra="forbid" rejection, model_validators, edge cases | ~20 tests |
| `test_tracker.py` | `ConfigurationEvolutionTracker`: check_promotion, classify_change, find_rule, version queries | ~15 tests |
| `test_loader.py` | `ConfigEvolutionLoader`: load, cache hit, cache miss, clear_cache, load_from_string, error cases | ~8 tests |
| `test_otel.py` | OTel emission helpers: with OTel, without OTel (_HAS_OTEL=False), attribute correctness | ~8 tests |
| `test_preflight.py` | Pre-flight validation: orphaned rules, ungoverned configs, current_version mismatch | ~6 tests |

**Estimated total: ~57 tests**

### Key Test Scenarios

1. **Happy path**: Load a valid contract, promote a configuration version, all gates pass, result is approved.
2. **Quality gate failure**: Promotion rule requires `quality_threshold: 0.85`, change does not meet threshold, result is not approved.
3. **Regression gate failure**: Promotion rule requires `regression_check: true`, regression detected, result is not approved.
4. **Human approval required**: Rule specifies `human_approval: "required"`, result sets `requires_human_approval=True`.
5. **Rollback detection**: New version < old version by semver, `ConfigurationChange.is_rollback` is True.
6. **No matching rule**: Configuration has no applicable promotion rule, all changes are allowed (same as `EvolutionTracker` behavior).
7. **Scope prefix matching**: Rule with scope `"prompt"` matches config_type `"prompt_template"`.
8. **Pre-flight: current_version not in history**: Warns but does not raise.
9. **Pre-flight: orphaned rule**: Rule scope matches no configuration, warns.
10. **Cache behavior**: Second load of same file returns cached instance; `clear_cache()` forces reload.
11. **Extra field rejection**: YAML with unknown keys raises `ValidationError`.
12. **OTel not installed**: Emission helpers degrade gracefully (no-op).
13. **RegressionGate integration**: `check()` with failed `PromotionCheckResult` fails the gate; without it, gate is unaffected.

### Testing Patterns

Follow the established patterns from `tests/unit/contextcore/contracts/schema_compat/`:

- Mock OTel tracer via `patch("contextcore.contracts.config_evolution.otel._HAS_OTEL", False)`
- Use `load_from_string()` for inline YAML test fixtures
- Use `clear_cache()` in autouse fixtures to prevent cross-test contamination
- Assert on Pydantic `ValidationError` for schema violation tests

---

## Non-Requirements

The following are explicitly **out of scope** for this concern:

1. **Runtime prompt versioning at request boundaries.** Configuration evolution
   is a design-time / CI-time governance concern. It does not validate prompt
   versions on every request. Runtime boundary stamping of `config.prompt_version`
   is a future Layer 4 extension, not part of this implementation.

2. **Prompt content analysis or diffing.** The tracker compares hashes and
   version strings. It does not parse prompt templates, compute semantic
   similarity between prompt versions, or perform NLP-based quality estimation.
   Quality thresholds in promotion requirements are *declared*, not *computed*
   by this module.

3. **Prompt storage or retrieval.** Configuration evolution tracks metadata
   about configurations (version, hash, deployed_at). It does not store the
   actual prompt text, model config YAML, or system instructions. Those are
   managed by the application's own configuration management system.

4. **Automated quality evaluation.** The `quality_threshold` requirement
   declares what score is needed. A separate evaluation system (DSPy metrics,
   custom evaluators, human scoring) provides the actual score. This concern
   defines the gate contract, not the evaluator.

5. **Multi-environment promotion pipelines.** This version does not model
   promotion across environments (dev -> staging -> production). A single
   contract covers one environment's configuration governance. Multi-environment
   promotion is a future extension.

6. **Canary / gradual rollout support.** Configuration changes are modeled as
   atomic version transitions, not gradual percentage-based rollouts. Canary
   deployment strategies are orthogonal to the evolution contract model.

7. **Dependency between configurations.** This version does not model
   dependencies between configurations (e.g., "prompt v3.2 requires model
   config v2.0"). Cross-configuration dependency graphs are a future extension.

8. **Inheritance from EvolutionTracker.** The `ConfigurationEvolutionTracker`
   replicates the pattern but does not inherit from or import `EvolutionTracker`.
   This keeps the modules independently deployable. A future abstract base class
   (`AbstractEvolutionTracker`) could unify both without breaking either.
