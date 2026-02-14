# Init-from-Plan Operational Requirements

## Purpose

Define the operational intent and high-level requirements for `contextcore manifest init-from-plan` so it can:

- convert plan + requirements documents into a valid `.contextcore.yaml`
- reduce manual bootstrap work
- improve downstream quality for `manifest export`, StartD8 plan ingestion, and contractor workflows
- enforce quality and traceability early in the lifecycle

## Problem Statement

Current lifecycle is:

1. `manifest init` creates a scaffold
2. operator manually fills project-specific fields
3. `manifest export` generates contract artifacts

Manual step 2 is high-friction and error-prone. `init-from-plan` addresses this by inferring structured manifest fields programmatically from plan/requirements inputs.

## Operational Intent

`init-from-plan` should act as a deterministic, auditable translation layer between human planning artifacts and machine-consumable manifest structure.

It should:

- infer as much as possible with confidence metadata
- fail fast when strict quality minimums are not met
- emit an inference report that explains exactly what was inferred and why
- produce a valid v2 manifest suitable for strict export

## In-Scope Behavior

- Input:
  - plan file (required)
  - zero or more requirements files
  - optional project root
- Output:
  - generated/updated v2 `.contextcore.yaml`
  - `init-from-plan` inference report JSON
- Quality:
  - optional strict-quality gate (default on)
  - optional post-write manifest validation (default on)

## Out of Scope (for now)

- full semantic understanding of all planning patterns
- perfect extraction for every doc structure
- automatic source-code deep analysis beyond lightweight inference hooks
- direct generation of final observability artifacts (done later by export/generate workflows)

## Functional Requirements

1. **Manifest creation**
   - Must generate a v2 manifest structure compatible with `manifest export`.
2. **Inference**
   - Must infer key fields from plan/requirements where possible:
     - `spec.project.description` (heading + first meaningful line)
     - `spec.targets` (from project root basename)
     - `spec.business.criticality` (P0-P4, sev-1, explicit criticality keywords)
     - `spec.business.owner` (owner/team keywords)
     - `spec.requirements.*` (availability, latencyP99, throughput, errorBudget via regex)
     - `spec.observability.alertChannels` (Slack channel extraction)
     - `spec.risks[]` with **keyword-inferred risk types** (security, compliance, data-integrity, availability, financial, reputational) — maps to `RiskType` enum
     - `guidance.constraints` from guardrail patterns ("Do not...", "Keep...")
     - `guidance.questions` from question-ending lines (optional, `--emit-guidance-questions`)
     - `strategy.objectives[]` — **multiple objectives** from `### Goals` and `### Execution Scope` sections (up to 3)
     - `strategy.tactics[]` — extracted from `### Phase`, `### Milestone`, `### Action Items`, `### Deliverables` sections (headings + bullet items, up to 10)
     - `metadata.links` — **URL extraction** for repo (GitHub/GitLab/Bitbucket), tracker (Jira/Linear), docs (wiki/Confluence/Notion), dashboard (Grafana)
3. **Strict-quality mode**
   - Must gate low-confidence outputs by requiring a minimum set of core inferred fields.
4. **Validation**
   - Must support post-write validation and fail if invalid.
5. **Auditability**
   - Must emit an inference report (v1.1.0) with:
     - inputs
     - inferred fields and confidence
     - warnings
     - quality-gate status
     - **downstream readiness assessment** (see below)
6. **Downstream readiness assessment**
   - Must score manifest readiness for export on a 0-100 scale with verdict (ready/needs_enrichment/insufficient)
   - Must check: requirements population, targets defined, observability configured, objectives defined, guidance populated, risks defined, estimated artifact count
   - Must predict A2A gate readiness: checksum_chain, derivation_rules, design_calibration, gap_parity

## Non-Functional Requirements

- **Deterministic behavior:** same inputs should produce materially similar outputs.
- **Explainability:** report must clearly show field-level inference provenance.
- **Safety:** on strict-quality failure, write report and return non-zero.
- **Compatibility:** output must remain consumable by strict `manifest export`.

## Downstream Success Criteria

1. Export can run in strict mode using generated manifest with minimal manual edits.
2. Export outputs include coherent onboarding metadata and mapping-ready structure.
3. Plan ingestion receives cleaner, less ambiguous contract inputs.
4. Contractor workflows receive higher-fidelity constraints/objectives earlier.

## Key Risks and Mitigations

- **Risk:** mis-inference of criticality or requirements.
  - **Mitigation:** confidence thresholds + strict-quality gate + report transparency.
- **Risk:** overfitting to one document style.
  - **Mitigation:** heuristic layering and explicit fallback defaults.
- **Risk:** hidden quality regressions.
  - **Mitigation:** include command-level tests with representative plan fixtures.

## Implementation Note: Relationship to `manifest init`

`init-from-plan` does **not** currently call `manifest init` as a subprocess or wrapper command.

It uses shared template-building logic directly in code, then applies inference transforms, and optionally validates the resulting manifest.

This is intentional to keep control over inference-specific flow and reporting while preserving compatibility with `manifest init` output shape.

## Implementation Status

| Capability | Status | Notes |
|------------|--------|-------|
| Description inference | Implemented | heading + first meaningful line |
| Criticality inference | Implemented | P0-P4, sev-1, explicit keywords |
| Requirements extraction | Implemented | availability, latencyP99, throughput, errorBudget |
| Alert channel extraction | Implemented | Slack `#channel` patterns |
| Owner/team inference | Implemented | owner/team keyword regex |
| Target inference | Implemented | from project root basename |
| Risk extraction | Implemented | with keyword-based type inference |
| Guardrail → constraint | Implemented | "Do not" / "Keep" patterns |
| Question extraction | Implemented | question-ending lines |
| Multiple objectives | Implemented | up to 3 from Goals/Execution Scope |
| Tactics extraction | Implemented | from Phase/Milestone/Action Items/Deliverables sections |
| URL extraction | Implemented | GitHub, Jira, wiki, Grafana → metadata.links |
| Downstream readiness | Implemented | 0-100 score, A2A gate readiness prediction |
| Inference report v1.1.0 | Implemented | includes downstream_readiness field |

## Next Increments

1. ~~improve objective extraction from execution scope and goals sections~~ — **Done** (multiple objectives + tactics)
2. add optional source-code metadata extraction hooks (repo/service detection)
3. add confidence-calibrated review prompts for unresolved fields
4. add regression tests for known plan doc formats
5. LLM-assisted inference for complex plan structures (beyond regex)
6. cross-reference extracted objectives with existing CI/CD pipeline metadata
