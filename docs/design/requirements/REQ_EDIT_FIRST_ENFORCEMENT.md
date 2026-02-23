# Requirements: Edit-First Enforcement (REQ-EFE)

**Status:** Partially Implemented
**Date:** 2026-02-22
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline integrity)
**Pipeline version:** 2.0 (Capability Delivery Pipeline)
**Depends on:** `EXPECTED_OUTPUT_CONTRACTS` (onboarding.py), `PipelineChecker` (pipeline_checker.py)

---

## Problem Statement

The artisan pipeline's IMPLEMENT phase consistently generates target files from scratch
instead of editing them. All PCA-5xx/6xx prompt-level edit-first mechanisms are
implemented, but the LLM ignores them and no mechanical gate catches the destructive
rewrite.

When an LLM rewrites a 200-line dashboard from scratch, the output often drops panels,
removes templating variables, or loses datasource configuration. The result passes syntax
validation but represents a regression in content.

The highest-leverage fix is a **post-generation size regression gate** that compares
output size to input size. If the output is smaller than a configurable threshold
(e.g., 85% of the original), the gate rejects the output before it reaches the
filesystem. This requires ContextCore to publish per-artifact-type thresholds so the
consumer side can enforce them mechanically.

---

## Scope

### In scope

- **Producer side (ContextCore export):** Publish `edit_min_pct` thresholds per artifact type in `expected_output_contracts`, propagate to `design_calibration_hints`, announce via `schema_features`
- **Pipeline checker gate:** Validate that exported metadata includes valid `edit_min_pct` values
- **Consumer-side contracts:** Define the interface that `DesignPhaseHandler` in startd8-sdk will use to enforce size regression gating

### Out of scope

- LLM prompt engineering for edit-first behavior (PCA-5xx/6xx prompt mechanisms)
- Artisan pipeline orchestration logic
- File-level diff/patch tooling

---

## Architecture

```
ContextCore (Producer)                    startd8-sdk (Consumer)
─────────────────────                     ────────────────────────
EXPECTED_OUTPUT_CONTRACTS                 DesignPhaseHandler
  └─ edit_min_pct: 85                       └─ reads edit_min_pct from metadata
       │                                         │
       ▼                                         ▼
design_calibration_hints                  Post-generation size check:
  └─ edit_min_pct: 85                       output_size / input_size >= edit_min_pct/100
       │                                         │
       ▼                                    ┌────┴────┐
schema_features                            PASS    REJECT
  └─ "edit_first_enforcement"               │         │
       │                                    write   log warning,
       ▼                                    file    request re-gen
PipelineChecker gate 10                          with edit prompt
  └─ validates edit_min_pct
     presence and range
```

---

## Threshold Rationale

Each artifact type has an `edit_min_pct` threshold reflecting how much content loss
is acceptable during a legitimate edit vs. a destructive rewrite.

| ArtifactType | `edit_min_pct` | Rationale |
|---|---|---|
| `dashboard` | 85 | Panels accumulate; shrinking signals deletion |
| `prometheus_rule` | 80 | Removing alert rules is a safety concern |
| `slo_definition` | 80 | SLO specs rarely shrink |
| `service_monitor` | 70 | Small files; legitimate resizing possible |
| `loki_rule` | 80 | Recording rules are additive |
| `notification_policy` | 80 | Removing routes is a concern |
| `runbook` | 85 | Losing sections harms incident response |
| `alert_template` | 75 | Templates may be refactored |
| `capability_index` | 90 | Removals indicate regression |
| `agent_card` | 85 | Skills accumulate |
| `mcp_tools` | 90 | Tool removal is regression |
| `onboarding_metadata` | 80 | Pipeline metadata is additive |
| `provenance` | 70 | Small; structure may change |
| `ingestion_traceability` | 70 | Small; structure may change |
| `dockerfile` | 50 | May be legitimately restructured |
| `python_requirements` | 50 | Deps may shrink during cleanup |
| `protobuf_schema` | 75 | Schema evolution is additive |
| `editorconfig` | 50 | Very small; changes are structural |
| `ci_workflow` | 70 | CI configs may be refactored |

**Design principle:** Higher thresholds for artifacts where content is strictly
additive (dashboards, capability indexes, MCP tools). Lower thresholds for artifacts
that may legitimately shrink (Dockerfiles, requirements files, editorconfigs).

---

## Requirements

### REQ-EFE-010: Producer — `edit_min_pct` in output contracts

**Status:** Implemented (commit `164b7e3`)

Every entry in `EXPECTED_OUTPUT_CONTRACTS` MUST include an `edit_min_pct` field
with an integer value in the range 0–100. This threshold is the minimum acceptable
output-size-as-percentage-of-input-size for the post-generation size regression gate.

**Implementation:**
- File: `src/contextcore/utils/onboarding.py`
- Each of 19 artifact type entries in `EXPECTED_OUTPUT_CONTRACTS` has `"edit_min_pct": N`
- `build_onboarding_metadata()` propagates via `dict(EXPECTED_OUTPUT_CONTRACTS[art_type])` shallow copy

**Acceptance criteria:**
- Every artifact type in `EXPECTED_OUTPUT_CONTRACTS` has `edit_min_pct` as `int` in 0–100
- Spot checks: `dashboard=85`, `dockerfile=50`, `capability_index=90`
- Test: `test_enrichment_edit_min_pct_in_output_contracts` in `tests/test_manifest_v2.py`

---

### REQ-EFE-011: Producer — `edit_min_pct` in calibration hints

**Status:** Implemented (commit `164b7e3`)

The `design_calibration_hints` dict MUST propagate `edit_min_pct` from the output
contract for each artifact type. Consumers that read calibration hints (e.g., the
artisan DESIGN phase) get edit-first thresholds without needing to parse full
output contracts.

**Implementation:**
- File: `src/contextcore/utils/onboarding.py`
- Calibration hints dict literal includes `"edit_min_pct": contract.get("edit_min_pct", 80)`
- Fallback to 80 ensures backward compatibility if a contract entry lacks the field

**Acceptance criteria:**
- Every calibration hint for a non-service-specific artifact type has `edit_min_pct` in 0–100
- Test: `test_enrichment_edit_min_pct_in_calibration_hints` in `tests/test_manifest_v2.py`

---

### REQ-EFE-012: Producer — `edit_first_enforcement` schema feature

**Status:** Implemented (commit `164b7e3`)

The `schema_features` list in onboarding metadata capabilities MUST include
`"edit_first_enforcement"` so downstream consumers can feature-detect edit-first
support without inspecting individual contracts.

**Implementation:**
- File: `src/contextcore/utils/onboarding.py`
- Added `"edit_first_enforcement"` to `schema_features` list

**Acceptance criteria:**
- `capabilities.schema_features` contains `"edit_first_enforcement"`
- Test: `test_schema_features_includes_edit_first` in `tests/test_manifest_v2.py`

---

### REQ-EFE-013: Pipeline checker gate 10 — edit-first coverage

**Status:** Implemented (commit `164b7e3`, refined in `043fcfe`)

The `PipelineChecker` MUST include a gate (gate 10) that validates edit-first
coverage in exported metadata. The gate checks that every output contract includes
a valid `edit_min_pct` value.

**Implementation:**
- File: `src/contextcore/contracts/a2a/pipeline_checker.py`
- Method: `_check_edit_first_coverage() -> Optional[GateResult]`
- Returns `None` (skipped) when `expected_output_contracts` is absent
- Validates: `edit_min_pct` present, numeric, finite, in range 0–100
- Severity: `WARNING` (non-blocking) — missing edit-first data degrades but doesn't block
- NaN guard via `math.isfinite()` (added in refactor commit `043fcfe`)

**Acceptance criteria:**
- All contracts with valid `edit_min_pct` → gate PASS
- Missing `edit_min_pct` on any contract → gate FAIL with evidence
- Invalid value (out of range, NaN, Inf) → gate FAIL with evidence
- Gate is non-blocking (`blocking=False`); overall report health unaffected by failure
- No `expected_output_contracts` → gate skipped (not failed)
- Tests: `TestEditFirstCoverage` class (5 tests) in `tests/test_pipeline_checker.py`

---

### REQ-EFE-020: Consumer — Size regression gate in `DesignPhaseHandler`

**Status:** Not Implemented

The `DesignPhaseHandler` in startd8-sdk MUST implement a post-generation size
regression gate. After the LLM generates output for a target file, the handler
MUST compare output size to input size (if the file exists) and reject the output
if `output_size / input_size < edit_min_pct / 100`.

**Consumer location:** `~/Documents/dev/startd8-sdk/src/startd8/contractors/`

**Algorithm:**
```python
if target_file.exists():
    input_size = len(target_file.read_text())
    output_size = len(generated_content)
    threshold = calibration_hints[artifact_type].get("edit_min_pct", 80) / 100
    if output_size / input_size < threshold:
        # Reject: destructive rewrite detected
        log.warning(
            "Size regression: %s shrank from %d to %d chars (%.0f%%, threshold %.0f%%)",
            target_file, input_size, output_size,
            100 * output_size / input_size, threshold * 100
        )
        raise SizeRegressionError(...)
```

**Acceptance criteria:**
- Gate fires only when target file already exists (new file creation is always allowed)
- Gate reads `edit_min_pct` from calibration hints or output contracts
- Gate defaults to 80% if threshold is missing (matches REQ-EFE-011 fallback)
- Rejection produces a clear log message with file path, sizes, and threshold
- Gate can be bypassed with an explicit override (e.g., `--force-rewrite`)

---

### REQ-EFE-021: Consumer — Feature detection via schema_features

**Status:** Not Implemented

Before enforcing the size regression gate, the consumer SHOULD check that
`"edit_first_enforcement"` is present in `schema_features`. If absent, the
consumer SHOULD fall back to a default threshold (80%) and emit a warning.

**Acceptance criteria:**
- Consumer checks `schema_features` for `"edit_first_enforcement"`
- When present: uses `edit_min_pct` from calibration hints
- When absent: uses default 80%, logs a deprecation warning

---

### REQ-EFE-022: Consumer — Rejection telemetry

**Status:** Not Implemented

When the size regression gate rejects an output, the consumer MUST emit a span
event recording the rejection. This enables monitoring via TraceQL.

**Span event attributes:**
- `event.name`: `"edit_first.size_regression"`
- `edit_first.artifact_type`: The artifact type
- `edit_first.input_size`: Original file size in characters
- `edit_first.output_size`: Generated output size in characters
- `edit_first.ratio`: `output_size / input_size` as float
- `edit_first.threshold`: The `edit_min_pct` value (0–100)
- `edit_first.action`: `"rejected"` or `"force_overridden"`

**TraceQL query:**
```traceql
{ span.edit_first.action = "rejected" }
```

**Acceptance criteria:**
- Rejection emits a span event with all listed attributes
- Force-override also emits the event (with action `"force_overridden"`)
- Events are queryable via TraceQL

---

### REQ-EFE-023: Consumer — Re-generation with edit prompt

**Status:** Not Implemented

When the size regression gate rejects an output, the consumer SHOULD (optionally)
re-invoke the LLM with an explicit edit-focused prompt that includes:
1. The original file content
2. The specific changes requested
3. An instruction to preserve all existing content not related to the change

This is a best-effort retry mechanism. If the retry also fails the size regression
gate, the consumer MUST halt and report the failure.

**Acceptance criteria:**
- Retry is configurable (enabled by default, can be disabled)
- Retry prompt includes original file content and change description
- Maximum 1 retry (no infinite loops)
- If retry also fails gate, consumer halts with error

---

## Implementation Status

| Requirement | Status | Commit | Location |
|---|---|---|---|
| REQ-EFE-010 | Implemented | `164b7e3` | `src/contextcore/utils/onboarding.py` |
| REQ-EFE-011 | Implemented | `164b7e3` | `src/contextcore/utils/onboarding.py` |
| REQ-EFE-012 | Implemented | `164b7e3` | `src/contextcore/utils/onboarding.py` |
| REQ-EFE-013 | Implemented | `164b7e3`, `043fcfe` | `src/contextcore/contracts/a2a/pipeline_checker.py` |
| REQ-EFE-020 | Not Implemented | — | `startd8-sdk` (consumer side) |
| REQ-EFE-021 | Not Implemented | — | `startd8-sdk` (consumer side) |
| REQ-EFE-022 | Not Implemented | — | `startd8-sdk` (consumer side) |
| REQ-EFE-023 | Not Implemented | — | `startd8-sdk` (consumer side) |

---

## Backward Compatibility

All producer-side changes (REQ-EFE-010 through REQ-EFE-013) are additive:

- `edit_min_pct` is a new field; no existing fields changed
- Existing tests don't assert absence of extra keys
- Pipeline checker gate 10 is non-blocking WARNING; old exports without `edit_min_pct` get a skipped gate or warning
- `schema_features` list gains one entry; consumers that don't check for it are unaffected

Consumer-side changes (REQ-EFE-020 through REQ-EFE-023) will also be additive:
- Size regression gate fires only when target file exists
- Feature detection falls back to default when `schema_features` is absent
- Telemetry events are new attributes (no breaking changes)

---

## Verification

```bash
# Producer-side tests (implemented)
python3 -m pytest tests/test_manifest_v2.py -v -k "edit_min_pct or edit_first"
python3 -m pytest tests/test_pipeline_checker.py -v -k "TestEditFirstCoverage"

# Full test suite (no regressions)
python3 -m pytest --tb=short

# Verify export output includes edit_min_pct
contextcore manifest export -p .contextcore.yaml -o /tmp/efe-test --dry-run 2>&1 | head -20
```

---

## Cross-References

- **PCA-5xx/6xx**: Prompt-level edit-first mechanisms (artisan pipeline, not ContextCore)
- **REQ-CAP-008**: Capability-aware question generation in init-from-plan
- **Pipeline checker gates 1–9**: Existing integrity checks in `pipeline_checker.py`
- **Refactor archive**: `/Users/neilyashinsky/Documents/craft/Lessons_Learned/skills/python-code-refactor/archive/2026-02-22-edit-first-enforcement.md`
