# Contract Drift Detection Requirements

Purpose: define the behavioral requirements for `ContractDriftDetector` and the `contextcore contract check` CLI command — the governance capability that detects when actual pipeline outputs structurally diverge from declared A2A contract schemas over time.

This document is intentionally living guidance. Update it as the implementation evolves.

---

## Vision

Boundary enforcement (`boundary.py`) catches runtime violations on individual payloads — a missing field, a wrong type, a value outside an enum. But it cannot detect **structural drift**: the gradual divergence between what the code actually produces and what the schemas declare.

Contract drift detection fills this gap. It compares the declared schema (JSON Schema files in `schemas/contracts/`) against actual outputs (export files, gate results, contract payloads) and reports where the two have diverged. This is the "are we still building what we said we'd build?" check.

**Core principle**: Schema and implementation should be one conversation. When they diverge, trust in the governance layer erodes.

---

## Current State

### What Exists

| Component | Path | Status |
|-----------|------|--------|
| CLI command | `src/contextcore/cli/contract.py` (`contract_check_cmd`) | Exists, imports `ContractDriftDetector` |
| OpenAPI parser | `src/contextcore/integrations/contract_drift.py` | Exists — `parse_openapi()` and `EndpointSpec` |
| OpenAPI parser (alt) | `src/contextcore/integrations/openapi_parser.py` | Exists — duplicate/parallel implementation |
| `__init__.py` exports | `src/contextcore/integrations/__init__.py` | Exports `ContractDriftDetector`, `DriftIssue`, `DriftReport` |
| JSON schemas | `schemas/contracts/*.schema.json` | 4 schemas: gate-result, handoff-contract, task-span-contract, artifact-intent |

### What's Missing

| Component | Status |
|-----------|--------|
| `ContractDriftDetector` class | Not implemented — `__init__.py` exports it but it doesn't exist in `contract_drift.py` |
| `DriftIssue` dataclass | Not implemented |
| `DriftReport` dataclass | Not implemented |
| A2A schema drift detection | Not implemented (current stub is OpenAPI-focused, not A2A-schema-focused) |

### Design Decision: Scope Pivot

The original `contract check` command was designed around OpenAPI drift detection (comparing API specs against live service responses). The A2A governance layer has introduced a different, more pressing drift detection need: **A2A schema drift** — comparing JSON schema declarations against actual pipeline outputs.

This requirements document covers **both** scopes:
- **Scope A**: A2A schema drift (new, higher priority — validates governance layer integrity)
- **Scope B**: OpenAPI drift (original scope — validates service contract compliance)

---

## Scope A: A2A Schema Drift Detection

### Problem

ContextCore declares 4 A2A contract schemas in `schemas/contracts/`:

| Schema | File | Validates |
|--------|------|-----------|
| GateResult | `gate-result.schema.json` | Output of every gate check |
| HandoffContract | `handoff-contract.schema.json` | Agent handoff payloads |
| TaskSpanContract | `task-span-contract.schema.json` | Task span attributes |
| ArtifactIntent | `artifact-intent.schema.json` | Artifact work declarations |

These schemas are the contract between ContextCore modules (which produce the payloads) and downstream consumers (which rely on the shape). Drift occurs when:

1. **Code adds a field** that the schema doesn't declare (undocumented field)
2. **Schema declares a field** that the code never populates (phantom field)
3. **Enum values diverge** between Python code and JSON schema (e.g., new `Phase` member added to `types.py` but not to schema)
4. **Type changes** in code that aren't reflected in schema (e.g., `str` → `Optional[str]`)

### Functional Requirements

#### Detection

1. **Schema-to-model comparison**
   - Must compare each JSON schema in `schemas/contracts/` against the corresponding Pydantic model in `contracts/a2a/models.py`.
   - Must detect: fields present in model but absent in schema, fields present in schema but absent in model, type mismatches, enum value mismatches.
   - Must handle Pydantic v2 `model_json_schema()` output for comparison.

2. **Schema-to-output comparison**
   - Must compare JSON schemas against actual pipeline output files (e.g., `onboarding-metadata.json`, `provenance.json`, gate result JSON files).
   - Must detect: undeclared fields in output, missing required fields, type mismatches.
   - Must support scanning an output directory for all relevant files.

3. **Enum drift detection**
   - Must compare Python enum values (from `contracts/types.py`) against JSON schema `enum` arrays.
   - Must report: values in Python but not in schema, values in schema but not in Python.
   - Must cover all enums: `Phase`, `TaskStatus`, `TaskType`, `Priority`, `HandoffStatus`, `InsightType`, `AgentType`, etc.

4. **Severity classification**
   - Must classify each drift issue by severity:
     - **Critical**: Required field missing, type mismatch on required field, enum value in code but not in schema (could cause validation failures)
     - **Warning**: Optional field undocumented, deprecated field still present, enum value in schema but not in code
     - **Info**: Extra metadata fields, documentation-only differences

#### Reporting

5. **Drift report**
   - Must produce a structured `DriftReport` with: project context, schemas checked, issues found (grouped by severity), summary statistics.
   - Must support `text` (human-readable) and `json` (machine-readable) output formats.
   - Must support writing the report to a file via `--output`.

6. **Actionable recommendations**
   - Each drift issue must include a `recommendation` field with a specific fix action.
   - Example: "Add `reason` field (type: string, required: false) to gate-result.schema.json"
   - Example: "Add `Phase.ARTISAN_FINALIZE` to phase enum in gate-result.schema.json"

### CLI Surface (Scope A)

```
contextcore contract check
  --scope              (default: a2a)    Drift scope: a2a | openapi | all
  --schemas-dir        (default: schemas/contracts/)  Path to JSON schemas
  --output-dir         (optional)        Scan actual output files for drift
  --output / -o        (optional)        Write report to file
  --format / -f        (default: text)   Output format: text | json
  --fail-on-drift      (flag)            Exit 1 if any critical drift found
```

---

## Scope B: OpenAPI Drift Detection (Original)

### Functional Requirements

7. **OpenAPI spec parsing**
   - Must parse OpenAPI 3.x specifications from URL or local file path (already implemented in `parse_openapi()`).
   - Must extract endpoint paths, methods, request/response schemas, parameters.

8. **Live service probing**
   - Must send sample requests to live service endpoints.
   - Must compare actual responses against declared response schemas.
   - Must detect: missing endpoints, unexpected response fields, schema mismatches, status code mismatches.

9. **ProjectContext integration**
   - Must auto-detect contract URL from `ProjectContext` CRD `spec.design.apiContract` field.
   - Must auto-detect service URL from `spec.targets[]` when not explicitly provided.

### CLI Surface (Scope B)

```
contextcore contract check
  --scope openapi
  --project / -p       (required)        Project name (for CRD lookup)
  --service-url        (optional)        Live service URL (auto-detected if omitted)
  --contract-url       (optional)        OpenAPI spec URL/path (auto-detected if omitted)
  --output / -o        (optional)        Write report to file
  --format / -f        (default: text)   Output format: text | json
  --fail-on-drift      (flag)            Exit 1 if any critical drift found
  --namespace / -n     (default: default) K8s namespace for CRD lookup
```

---

## Data Models

### DriftIssue

```python
@dataclass
class DriftIssue:
    scope: str           # "a2a" or "openapi"
    schema_id: str       # Schema file or OpenAPI spec path
    location: str        # JSON path or endpoint path
    issue_type: str      # "missing_field", "extra_field", "type_mismatch",
                         # "enum_drift", "missing_endpoint", "schema_mismatch"
    severity: str        # "critical", "warning", "info"
    expected: str        # What the schema declares
    actual: str          # What the code/output produces
    recommendation: str  # Specific fix action
```

### DriftReport

```python
@dataclass
class DriftReport:
    project_id: str
    scope: str                     # "a2a", "openapi", "all"
    schemas_checked: int
    issues: list[DriftIssue]
    timestamp: str
    has_drift: bool               # Any issues found
    critical_issues: list[DriftIssue]  # Severity == critical

    def to_markdown(self) -> str: ...
    def to_json(self) -> str: ...
    def summary(self) -> str: ...
```

---

## Non-Functional Requirements

1. **Offline operation** (Scope A): A2A schema drift detection must work without network access — it compares local files only.
2. **Network required** (Scope B): OpenAPI drift detection requires access to the live service.
3. **Read-only**: Must not modify schemas, models, or output files.
4. **Determinism**: Same inputs must produce the same report.
5. **Performance**: A2A drift check must complete in under 2 seconds. OpenAPI drift depends on service response times.
6. **CI-friendly**: `--fail-on-drift` enables use as a CI gate.

---

## Invariants

1. A2A drift detection never makes network calls — it reads only local files.
2. Every `DriftIssue` has a non-empty `recommendation` field.
3. If `--fail-on-drift` is set, exit code 1 means at least one critical issue was found.
4. Enum drift detection covers every enum referenced in any JSON schema `enum` array.
5. The `ContractDriftDetector` class is importable from `src/contextcore/integrations/contract_drift.py` (existing import path in CLI).

---

## Relationship to Other Commands

| Command | Relationship |
|---------|-------------|
| `contract check` (this command) | Detects structural drift |
| `contract a2a-validate` | Validates individual payloads against schema (runtime, not drift) |
| `contract a2a-check-pipeline` | Validates pipeline output integrity (runtime, not drift) |
| `boundary.py` (`validate_outbound` / `validate_inbound`) | Runtime boundary enforcement |

---

## Related Docs

- `src/contextcore/integrations/contract_drift.py` — Current stub (OpenAPI parser only)
- `src/contextcore/cli/contract.py` — CLI command that imports `ContractDriftDetector`
- `schemas/contracts/*.schema.json` — A2A contract schemas
- `src/contextcore/contracts/a2a/models.py` — Pydantic v2 contract models
- `src/contextcore/contracts/types.py` — Canonical Python enums
- `docs/design/contextcore-a2a-comms-design.md` — A2A architecture (Extension 4)
- `docs/design/A2A_GATE_REQUIREMENTS.md` — Gate requirements
