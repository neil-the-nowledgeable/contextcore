# Manifest Create Requirements

Purpose: persist the working requirements for a proposed `contextcore manifest create` command that acts as a quality-first precursor to `manifest init` and `manifest export`, and a handoff producer for `startd8` plan ingestion and contractor workflows.

This document is intentionally living guidance. Update it as the command evolves.

---

## Vision

`manifest create` should do two jobs:

1. Define and validate requirements early (before `init`/`export`) to reduce downstream rework.
2. Draft a plan package that is directly consumable by `startd8 workflow run plan-ingestion`, which then routes to:
   - Prime contractor for simpler work
   - Artisan contractor for more complex work

Non-goal: `manifest create` does not execute code generation. Execution remains in `startd8`.

---

## Pipeline Placement

Target 5-step flow:

1. `contextcore manifest create` (new)
2. `contextcore install init` (existing)
3. `contextcore manifest export` (existing)
4. `startd8 workflow run plan-ingestion` (existing)
5. `prime` or `artisan` contractor execution (existing)

---

## User Walkthrough (Requirements Definition)

The command should walk users through the following sections, either interactively or via an input file:

1. Intent and outcomes
   - What is being built?
   - What business or operational outcome is expected?
   - Definition of done (testable acceptance outcomes).

2. Scope and boundaries
   - In-scope components and out-of-scope items.
   - Repositories and directories involved.
   - Environment target (dev/test/prod).

3. Functional requirements
   - Requirement IDs and plain-language requirement statements.
   - Acceptance criteria per requirement.
   - Requirement priority and dependencies.

4. Non-functional requirements
   - Reliability, performance, security, compliance, maintainability.
   - Explicit constraints and "must not" conditions.

5. Source mapping for parameters
   - For each required parameter, identify source path:
     - context manifest path
     - project context CRD path
     - requirements document path
     - policy/reference doc path
   - Flag unresolved or unknown sources explicitly.

6. Artifact contract preview
   - Required and recommended artifact types.
   - Priority and ordering guidance.
   - Required coverage threshold policy.

7. Gate policy before ingestion
   - Checksum chain expectations.
   - Coverage threshold and waiver policy.
   - Validation diagnostics policy (blocking vs warning).

8. Startd8 handoff policy
   - Default complexity threshold.
   - Route policy: auto, forced prime, or forced artisan.
   - Low-quality translation policy:
     - bias to artisan
     - hard fail

---

## Draft Plan Authoring Modes

`manifest create` should support draft generation modes:

- `scaffold`: deterministic template draft, no LLM.
- `enriched`: template plus inferred task structure from export and onboarding context.

In both modes, output should be editable and human-reviewable before ingestion.

---

## Proposed CLI Surface (MVP)

Command:

`contextcore manifest create`

Suggested options:

- `--project-id`
- `--project-name`
- `--manifest-path` (default `.contextcore.yaml`)
- `--requirements-path` (repeatable)
- `--output-dir` (default `./out/create`)
- `--draft-plan-mode` (`scaffold|enriched`)
- `--interactive/--no-interactive`
- `--complexity-threshold` (default `40`)
- `--route-policy` (`auto|prime|artisan`)
- `--low-quality-policy` (`bias_artisan|fail`)
- `--min-export-coverage` (default `70`)
- `--emit-startd8-config`
- `--emit-wayfinder-config`
- `--dry-run`

---

## Output Package (Create Step)

Minimum outputs:

1. `PLAN-draft.md`
   - Initial implementation plan intended for plan-ingestion input.

2. `create-spec.json`
   - Canonical machine-readable requirement and policy record.

3. `create-gates.json`
   - Pre-ingestion gating policy and pass/fail conditions.

4. `startd8-plan-ingestion-config.json`
   - Generated config skeleton for:
     - `plan_path`
     - `contextcore_export_dir`
     - `requirements_path` / `requirements_files`
     - `complexity_threshold`
     - `force_route` (if set)
     - quality/coverage policy options

Optional:

- `wayfinder-run-config.json`
- `create-session-summary.md`

---

## Proposed `create-spec.json` Schema (Draft)

```json
{
  "schema": "contextcore.io/create-spec/v1",
  "project": {
    "id": "string",
    "name": "string"
  },
  "intent": {
    "problem_statement": "string",
    "desired_outcomes": ["string"],
    "definition_of_done": ["string"]
  },
  "scope": {
    "in_scope": ["string"],
    "out_of_scope": ["string"],
    "repos": ["string"],
    "environments": ["string"]
  },
  "requirements": {
    "functional": [
      {
        "id": "FR-xxx",
        "description": "string",
        "acceptance_criteria": ["string"],
        "priority": "critical|high|medium|low",
        "depends_on": ["FR-yyy"]
      }
    ],
    "non_functional": [
      {
        "id": "NFR-xxx",
        "category": "reliability|performance|security|compliance|maintainability",
        "description": "string",
        "acceptance_criteria": ["string"]
      }
    ],
    "constraints": [
      {
        "type": "must|must_not|should",
        "statement": "string"
      }
    ]
  },
  "parameter_sources": [
    {
      "parameter": "string",
      "source_kind": "manifest|crd|requirements|policy|unknown",
      "source_path": "string",
      "resolved": true,
      "notes": "string"
    }
  ],
  "artifact_contract": {
    "required_types": ["dashboard", "prometheus_rule", "loki_rule", "service_monitor", "slo_definition", "notification_policy", "runbook"],
    "recommended_types": ["string"],
    "priority_order": ["string"]
  },
  "quality_policy": {
    "min_export_coverage": 70,
    "checksum_chain_required": true,
    "block_on_unresolved_parameters": true,
    "block_on_validation_errors": true
  },
  "routing_policy": {
    "complexity_threshold": 40,
    "route_policy": "auto|prime|artisan",
    "low_quality_policy": "bias_artisan|fail"
  },
  "handoff": {
    "plan_path": "PLAN-draft.md",
    "contextcore_export_dir_expected": "./out/export",
    "requirements_files": ["string"]
  }
}
```

---

## Proposed `PLAN-draft.md` Structure

1. Overview
2. Goals and outcomes
3. Scope and assumptions
4. Requirements mapping table (FR/NFR to artifacts)
5. Artifact generation plan
6. Validation and test obligations
7. Risks and mitigations
8. Acceptance criteria and sign-off checklist

Note: this structure should remain compatible with `plan-ingestion` parse and refine stages.

---

## Startd8 Compatibility Requirements

`manifest create` outputs should align with `startd8` plan-ingestion expectations:

- Plan file is always emitted and path-resolvable.
- ContextCore export directory expectation is explicit.
- Requirements files are explicit, not implicit context.
- Route and quality policy values map directly to known config fields.
- Output can be consumed without hand-editing for the common path.

---

## Inferred and Implied Requirements (Persisted)

The following requirements were inferred from pipeline docs, capability manifests, and discussion:

1. Boundary-first validation is mandatory.
2. Checksum chain continuity must be treated as a hard gate.
3. Parameter source resolvability must be explicit and machine-readable.
4. Coverage should be thresholded and enforced before ingestion.
5. Plan authoring and plan execution must remain decoupled.
6. ContextCore stays "what/contract"; Startd8 stays "how/execution".
7. Route defaults should favor safety:
   - auto route by complexity
   - bias to artisan on low translation quality unless strict-fail policy is selected
8. All emitted artifacts must be path-portable where possible (prefer relative paths in handoff-oriented outputs).
9. Command outputs must support deterministic reruns and auditability.
10. Human review remains first-class before contractor execution.

---

## Open Questions

1. Should `create` support an LLM-assisted mode in MVP, or remain deterministic first?
2. Should `create` write into `.startd8/` directly or a neutral folder?
3. Is there a required minimum FR/NFR count to proceed?
4. Should policy defaults vary by business criticality?
5. How should waivers be represented (coverage/checksum exceptions)?

---

## Update Checklist

When updating this document:

1. Keep schema version notes current.
2. Track added/removed CLI flags.
3. Record new gate rules and route policy changes.
4. Add cross-repo compatibility changes for `startd8`.
5. Move resolved open questions into "Inferred and Implied Requirements".

---

## Related Docs

- `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md`
- `docs/MANIFEST_ONBOARDING_GUIDE.md`
- `docs/ONBOARDING_METADATA_SCHEMA.md`
- `docs/ARTIFACT_MANIFEST_CONTRACT.md`
- `docs/ARTISAN_CONTEXT_SEED_QUALITY_REPORT.md`
- `docs/PRIME_CONTRACTOR_WORKFLOW.md`
