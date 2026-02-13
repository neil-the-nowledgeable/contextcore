# Weaver-Aligned Phase C Decision Memo

Date: 2026-02-13  
Status: Accepted for implementation

## Purpose

Define Phase C export-contract decisions so ContextCore onboarding/export enhancements remain compatible with Weaver cross-repo alignment requirements.

## Non-Negotiable Constraints

- Do not rename runtime semantic conventions in this phase.
- Keep `task.depends_on` (structural) and `task.blocked_by` (runtime blockers) semantically distinct.
- Keep Python contracts as canonical for runtime semantics; this phase is additive contract metadata.
- Do not introduce StartD8- or Wayfinder-specific workflow semantics into ContextCore export schemas.

## Decisions

1) Versioning Strategy (Additive)

- Keep existing `version` and `schema` fields.
- Add `schema_version` alongside existing fields for machine compatibility.
- Use semver compatibility semantics:
  - major: breaking changes
  - minor: additive compatible changes
  - patch: clarifications/fixes without contract change

1) Capability Negotiation

- Add `capabilities` block to onboarding metadata with:
  - `schema_features`
  - `optional_sections`
- Downstream consumers must gate behavior on capabilities rather than inferred field presence.

1) Parameter Resolvability

- Add machine-readable `parameter_resolvability` matrix:
  - status: `resolved|unresolved`
  - `source_path`
  - unresolved diagnostics: `reason_code`, `reason`
- Add `parameter_resolvability_summary` counts for deterministic preflight gates.

1) Validation Report Artifact

- Emit `validation-report.json` at export time (always).
- Report includes:
  - integrity/checksum diagnostics
  - coverage diagnostics
  - resolvability diagnostics
  - structured diagnostics list with severity+code
- This artifact is intended for downstream gating without embedding ContextCore business logic.

## Explicitly Out of Scope for Phase C

- Changing dual-emit runtime behavior (`legacy|dual|otel`).
- Altering Weaver enum cardinality decisions (e.g., HandoffStatus 6 vs 9).
- Replacing prose/documentation generation workflows.

## Impact

- Backward compatible for existing consumers (fields added, not renamed/removed).
- Enables deterministic StartD8 preflight checks and traceability gating.
- Preserves Weaver alignment by treating semconv naming as stable and contract evolution as additive metadata.
