# Requirements: Fix Stage (Deterministic Auto-Remediation)

**Status:** Draft
**Date:** 2026-02-16
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline evolution)
**Predecessor:** Polish Step Requirements (`docs/design/POLISH_STEP_REQUIREMENTS.md`)
**Pipeline version:** 2.0 (Capability Delivery Pipeline, Stage 1.5)

---

## Problem Statement

Polish (Stage 1) identifies 14 structural issues in plan documents but cannot fix
them. When plans are well-intentioned but structurally non-compliant --- for example,
an Overview section that describes objectives in prose but lacks the `**Objectives:**`
keyword --- the author must manually reformat before the plan can feed init-from-plan
with full fidelity.

Three polish checks detect conditions that are **deterministically fixable**: the
content exists in the document, it is just not in the format downstream stages expect.

| Polish check ID | What polish detects | What's actually present |
|----------------|---------------------|------------------------|
| `overview-objectives` | Missing `**Objectives:**` keyword in Overview | Intent verbs in Overview prose |
| `overview-goals` | Missing `**Goals:**` keyword in Overview | Phase headings indicating completion criteria |
| `requirements-exist` | No `## Functional Requirements` section | REQ-IDs scattered in `**Satisfies:**` lines |

The fix stage bridges this gap automatically, producing a remediated copy that passes
polish and feeds richer data to init-from-plan.

---

## Scope

### In scope

- Deterministic, content-preserving auto-remediation for 3 fixable polish checks
- Remediated output as a new file (never overwrites the original)
- Machine-readable fix report with pipeline traceability
- Inventory registration in run-provenance.json
- Idempotent behavior (running on already-fixed content produces no changes)

### Out of scope

- LLM-assisted remediation (all fixes are regex/heuristic-based)
- Fixing non-deterministic checks (risks-exist, validation-exist, etc.)
- Modifying the original plan document in-place

---

## Pipeline Traceability

Each fixable check traces through all 5 pipeline stages. This section documents
the end-to-end data flow for each fix, making this requirements doc a worked
example of how the Capability Delivery Pipeline validates plans.

### Fix 1: `overview-objectives`

| Stage | What happens |
|-------|-------------|
| **Polish** | Detects Overview section exists but lacks `\bObjectives?\b` keyword |
| **Fix** | Extracts intent verbs from Overview prose, inserts `**Objectives:**` line |
| **Init-from-plan** | `infer_init_from_plan()` extracts Overview text for `spec.project.description` --- objectives enrich the description |
| **Manifest** | `spec.project.description` contains objective-enriched text |
| **Export** | Description propagates to onboarding-metadata and downstream agent prompts |

### Fix 2: `overview-goals`

| Stage | What happens |
|-------|-------------|
| **Polish** | Detects Overview section exists but lacks `\bGoals?\b` keyword |
| **Fix** | Synthesizes goals from phase headings (completion-oriented), inserts `**Goals:**` block |
| **Init-from-plan** | `### Goals` section is parsed to populate `strategy.objectives` |
| **Manifest** | `strategy.objectives` contains goal-derived OBJ-PLAN entries |
| **Export** | Objectives appear in onboarding-metadata for agent planning |

### Fix 3: `requirements-exist`

| Stage | What happens |
|-------|-------------|
| **Polish** | Detects no `## Functional Requirements` section |
| **Fix** | Collects REQ-IDs from `**Satisfies:**` lines, builds `## Functional Requirements` table |
| **Init-from-plan** | `_REQ_ID_PATTERN` extracts IDs from the new section for `requirement_ids` inference |
| **Manifest** | `requirement_ids` populated, traceability_matrix coverage_ratio > 0 |
| **Export** | Requirements appear in traceability context for downstream agents |

---

## Requirements

### FR-FIX-001: Fix command accepts plan file target

The `contextcore fix` command MUST accept a positional `TARGET` argument pointing
to a markdown plan file. The command MUST NOT modify the original file under any
circumstances.

**Acceptance criteria:**
- `contextcore fix path/to/plan.md` reads the file and applies fixes
- The original file is unchanged after the command runs
- Non-markdown files are rejected with a clear error

### FR-FIX-002: Three deterministic fix strategies

The fix stage MUST implement exactly 3 fix strategies, one per fixable polish check:

| Check ID | Strategy name | Algorithm |
|----------|--------------|-----------|
| `overview-objectives` | `extract_from_overview_prose` | Find intent verbs (implement, establish, create, enable, ensure, define, build, design, deliver, align, provide, integrate, support, automate, validate, verify) in Overview paragraph, insert `**Objectives:**` line summarizing them |
| `overview-goals` | `synthesize_from_phases` | Extract completion-oriented phrases from phase headings or synthesize from phase count, insert `**Goals:**` block with bullet list |
| `requirements-exist` | `collect_req_ids_from_satisfies` | Gather all REQ-IDs from `**Satisfies:**` lines, build `## Functional Requirements` table mapping each to its containing phase |

**Acceptance criteria:**
- Each strategy transforms content deterministically (no randomness, no LLM calls)
- Each strategy is composable (operates on the output of previous strategies)
- Each strategy includes a pipeline traceability trace documenting downstream impact

### FR-FIX-003: Idempotent fix application

Running `contextcore fix` on an already-remediated plan MUST produce no changes.
The `FixResult` MUST report 0 fixed actions and the remediated content MUST be
identical to the input.

**Acceptance criteria:**
- `apply_fixes(already_fixed_content, checks)` returns `fixed_count == 0`
- `result.remediated_content == result.original_content`

### FR-FIX-004: Unfixable checks documented with reasons

Checks that are not fixable MUST be explicitly documented in the fix registry with
human-readable reasons explaining why they cannot be auto-remediated.

**Not fixable (with reasons):**
- `risks-exist` --- Requires domain knowledge to identify and describe risks
- `validation-exist` --- Validation criteria depend on implementation approach
- `pipeline-phases-exist` --- Phase decomposition requires understanding of work
- `pipeline-phase-metadata` --- Satisfies/Depends on/Repo require per-phase decisions
- `pipeline-deliverables` --- Deliverable paths require knowledge of target codebase
- `pipeline-validation-criteria` --- Per-phase validation depends on deliverable types
- `context-propagation` --- Self-validation harness is domain-specific
- `no-placeholders` --- Placeholder content must be filled by the author
- `overview-exists` --- Cannot generate an overview from nothing
- `pipeline-req-ids-found` --- REQ-IDs must be authored, not fabricated
- `pipeline-plan-title` --- H1 title requires human decision

**Acceptance criteria:**
- `FixAction` for unfixable checks has `status == "skipped"` and a non-empty `reason`
- The fix report lists all unfixable checks with their reasons

### FR-FIX-005: CLI options mirror polish plus fix-specific flags

The `contextcore fix` command MUST support:

| Flag | Description |
|------|------------|
| `--polish-report PATH` | Path to pre-computed polish-report.json (avoids re-running polish) |
| `--strict` | Exit with non-zero code if any fixable check could not be fixed |
| `--format text\|json` | Output format (default: text) |
| `--output-dir DIR` | Write remediated file, fix-report.json, and inventory entry |
| `--dry-run` | Preview fixes without writing any files |

**Acceptance criteria:**
- `--polish-report` reads the file and extracts check statuses
- `--dry-run` produces output describing what would be fixed but writes nothing
- `--output-dir` creates `<stem>.fixed.md`, `fix-report.json`, and updates `run-provenance.json`
- `--strict` exits with code 1 if any fixable check remains failed after fix

### FR-FIX-006: Output artifacts follow inventory conventions

When `--output-dir` is specified, the fix stage MUST produce:

1. `<stem>.fixed.md` --- The remediated plan (never overwrites original)
2. `fix-report.json` --- Machine-readable report with:
   - `source_file`: original file path
   - `actions`: list of `FixAction` dicts (check_id, status, strategy, diff_summary)
   - `summary`: counts (fixed, skipped, not_applicable)
   - `traceability`: per-fix pipeline traceability traces
3. Updated `run-provenance.json` with two inventory entries:
   - `fix.fix_report` (role: `fix_report`)
   - `fix.remediated_plan` (role: `remediated_plan`)

**Acceptance criteria:**
- Inventory entries have correct `artifact_id`, `role`, `stage`, `consumers`, `consumption_hint`
- `run-provenance.json` accumulates with entries from prior stages (create, polish)

### FR-FIX-007: Reuse existing patterns from polish and init-from-plan

The fix stage MUST reuse the following from existing modules rather than
reimplementing them:

| Import | Source | Used for |
|--------|--------|----------|
| `_extract_section_text` | `polish.py` | Extracting Overview section text |
| `_REQ_ID_PATTERN` | `init_from_plan_ops.py` | Matching REQ-/FR-/NFR- identifiers |
| `_SATISFIES_PATTERN` | `init_from_plan_ops.py` | Matching `**Satisfies:**` lines |
| `_PHASE_HEADING_PATTERN` | `polish.py` | Matching phase/milestone headings |
| `_H1_TITLE_PATTERN` | `polish.py` | Matching H1 titles |

**Acceptance criteria:**
- No duplicated regex patterns for requirement IDs, satisfies lines, or phase headings
- Fix operations import from existing modules

---

## Verification

```bash
# Unit tests
python3 -m pytest tests/unit/contextcore/cli/test_fix.py -v

# End-to-end: fix a plan, verify it passes polish
contextcore fix plan.md --output-dir output/
contextcore polish output/plan.fixed.md --format json | python3 -c \
  "import json,sys; d=json.load(sys.stdin); \
   fixable={'overview-objectives','overview-goals','requirements-exist'}; \
   fails=[c for r in d for c in r['checks'] if c['check_id'] in fixable and c['status']=='failed']; \
   assert not fails, f'Fixable checks still failing: {fails}'"
```
