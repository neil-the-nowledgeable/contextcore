# Requirements: Manifest Fix Wiring (Stage 2 → 3)

**Status:** Draft
**Date:** 2026-02-21
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 1 (pipeline evolution)
**Predecessor:** REQ_CAPABILITY_DELIVERY_PIPELINE.md, contextcore manifest fix (REQ-FIX-*)
**Pipeline version:** 2.0 (Capability Delivery Pipeline)
**Depends on:** `contextcore manifest fix` (--interactive, --answers), REQ-CAP-008 (capability-aware question generation)

---

## Problem Statement

Stage 2 (INIT-FROM-PLAN) produces `.contextcore.yaml` with inferred manifest fields. When capability-aware inference is enabled (REQ-CAP-008), the manifest may contain **open questions** in `guidance.questions` — e.g., Q-001 (traffic pattern), Q-CAP-1 (context propagation contracts), Q-CAP-2 (A2A governance gates), Q-CAP-3 (agent-to-agent handoffs).

Stage 3 (VALIDATE) runs `contextcore manifest validate --strict`, which **fails** when any question has `status: open`. The pipeline halts with:

```
Manifest failed schema validation.
Fix the manifest or re-run with --skip-validate to bypass.
```

The `contextcore manifest fix` command can resolve open questions via `--interactive` (prompts the user) or `--answers FILE` (batch mode). However, this command is **not wired** into `run-cap-delivery.sh`. Users must manually run fix, then re-run the pipeline or skip validation.

This creates two problems:

1. **Friction.** Users who want to pass validation must exit the pipeline, run fix manually, then re-invoke — or use `--skip-validate` and accept incomplete manifests.
2. **Inconsistent flow.** The fix capability exists but is invisible in the orchestrated pipeline; there is no documented "Stage 2.5" or retry path.

---

## Scope

### In scope

- Wiring `contextcore manifest fix` into `run-cap-delivery.sh` between Stage 2 (INIT) and Stage 3 (VALIDATE)
- Support for interactive resolution (`--interactive`) when validation fails due to open questions
- Support for batch resolution via `--answers FILE` for non-interactive/CI use
- Bypass flag `--skip-fix` to preserve current behavior (validate fails, user fixes manually)
- Provenance: fix stage produces inventory entry when questions are resolved
- Backward compatibility: pipeline behavior unchanged when `--skip-fix` or when manifest has no open questions

### Out of scope

- Changing `contextcore manifest fix` implementation (it already supports --interactive and --answers)
- Fixing plan-level issues (REQ_FIX_STAGE.md covers polish fixes; this doc covers manifest-level fixes only)
- LLM-assisted question answering

---

## Pipeline Position

```
Stage 2: INIT-FROM-PLAN  →  .contextcore.yaml (may have open questions)
                                    │
                                    ▼
Stage 2.5: MANIFEST FIX  →  Resolve open questions (interactive or --answers)
         (optional)               │
                                    ▼
Stage 3: VALIDATE        →  schema check (pass when no open questions)
```

Stage 2.5 is **conditional**: it runs only when (a) validation would fail due to open questions, and (b) `--skip-fix` is not set. If the manifest has no open questions, Stage 2.5 is skipped.

---

## Requirements

### REQ-MFW-001: Fix stage runs between INIT and VALIDATE

The `run-cap-delivery.sh` script MUST support a **Stage 2.5: MANIFEST FIX** that runs after Stage 2 (INIT-FROM-PLAN) and before Stage 3 (VALIDATE).

**Trigger condition:** Stage 2.5 runs when:
1. `contextcore manifest validate --path "$MANIFEST_PATH" --strict` would fail due to open questions, AND
2. `--skip-fix` is not set

**Skip condition:** Stage 2.5 is skipped when:
- `--skip-fix` is set, OR
- Manifest has no open questions (validation would pass)

**Acceptance criteria:**
- Script invokes `contextcore manifest fix` only when validation fails with open-question diagnostic
- Script does not run fix when validation fails for other reasons (schema errors, etc.) — those remain hard failures
- `--skip-fix` prevents fix from running; pipeline proceeds to Stage 3 (which will fail if questions remain)

---

### REQ-MFW-002: Interactive mode when TTY and no --answers

When Stage 2.5 runs and the following conditions hold:
- stdin is a TTY (interactive terminal)
- `--answers` was not provided

the script MUST invoke:
```bash
contextcore manifest fix --path "$MANIFEST_PATH" --interactive
```

The user is prompted for each open question. Resolved questions are written back to the manifest.

**Acceptance criteria:**
- `[ -t 0 ]` (or equivalent) used to detect TTY
- When TTY and no --answers: fix runs with --interactive
- User can skip a question by entering empty line (per existing fix behavior)
- After fix, validation is re-run; if it passes, pipeline continues to Stage 4

---

### REQ-MFW-003: Batch mode via --answers

When `--answers PATH` is provided, the script MUST invoke:
```bash
contextcore manifest fix --path "$MANIFEST_PATH" --answers "$ANSWERS_PATH"
```

This enables non-interactive and CI usage.

**Acceptance criteria:**
- `--answers` takes a path to a YAML/JSON file (question_id → answer mapping)
- When --answers is provided, --interactive is not used (batch mode takes precedence)
- Answers file format matches `contextcore manifest fix` expectations (flat mapping or `questions: [...]` envelope)
- If answers file is missing or invalid, fix fails with clear error

---

### REQ-MFW-004: Retry validation after fix

After Stage 2.5 completes successfully (at least one question resolved), the script MUST re-run Stage 3 (VALIDATE). If validation passes, the pipeline continues to Stage 4. If validation still fails (e.g., some questions skipped or unresolved), the pipeline halts with the same failure message as today.

**Acceptance criteria:**
- Validation is always run after fix (no short-circuit to export)
- If fix resolves all questions → validation passes → Stage 4 runs
- If fix resolves some but not all → validation fails → pipeline halts with "Manifest failed schema validation"
- User can still use `--skip-validate` to bypass validation entirely (unchanged behavior)

---

### REQ-MFW-005: Bypass flag --skip-fix

The script MUST support `--skip-fix` to disable Stage 2.5. When set:
- Fix is never run
- Pipeline proceeds directly from Stage 2 to Stage 3
- Behavior matches current pipeline (validation fails on open questions, user must fix manually)

**Acceptance criteria:**
- `--skip-fix` is parsed and stored
- When --skip-fix: no fix invocation; Stage 3 runs as today
- Banner displays `Skip fix: true` when set

---

### REQ-MFW-006: Provenance and inventory

When Stage 2.5 runs and resolves at least one question, the script MUST record an inventory entry in the output directory's provenance chain. The entry MUST reference the manifest path and the fix operation (interactive or answers file).

**Acceptance criteria:**
- `contextcore manifest fix` already writes to the manifest in-place; no separate artifact path
- If fix produces a fix-report or similar, it is written to OUTPUT_DIR
- Provenance entry documents: stage=manifest_fix, inputs=(manifest path, answers path or "interactive"), outputs=(updated manifest)

*Note: Current `contextcore manifest fix` may not emit provenance. This requirement may require a follow-on change to the fix command. If so, REQ-MFW-006 is satisfied when fix is extended to support --output-dir or --emit-provenance.*

---

### REQ-MFW-007: Detection of open-question failure

The script MUST distinguish validation failure due to open questions from other validation failures (e.g., schema violations, invalid YAML). Fix is only invoked for open-question failures.

**Acceptance criteria:**
- `contextcore manifest validate` exit code 1 with stderr containing "open question" or similar → trigger fix
- Exit code 1 with other errors (schema, parse) → do not run fix; fail immediately
- Implementation may use exit code + stderr parsing, or a `contextcore manifest validate --check-open-questions` pre-check if added

---

### REQ-MFW-008: Non-interactive without --answers

When Stage 2.5 would run but stdin is NOT a TTY and `--answers` was not provided, the script MUST NOT block waiting for input. Instead, it MUST:
- Emit a clear message: "Manifest has N open question(s). Run with --answers FILE or in an interactive terminal to resolve."
- Exit with non-zero (pipeline halted)
- Suggest: `contextcore manifest fix --path "$MANIFEST_PATH" --interactive` for manual resolution, or `--answers answers.yaml` for batch

**Acceptance criteria:**
- No hang in CI or when piped
- Message includes manifest path and question count
- Exit code 1

---

## CLI Summary

| Flag | Description |
|------|-------------|
| `--skip-fix` | Skip Stage 2.5; do not run manifest fix (default: false) |
| `--answers PATH` | YAML/JSON file with question_id → answer for batch resolution |
| `--skip-validate` | (existing) Skip Stage 3 validation entirely |

**Precedence:** `--answers` overrides interactive mode. `--skip-fix` prevents Stage 2.5 from running.

---

## Verification

```bash
# Interactive: run pipeline, when validate fails, fix prompts for answers
./run-cap-delivery.sh --plan plan.md --requirements reqs.md --project myproj --name myrun
# (validation fails) → fix --interactive prompts → user answers → validate passes → export

# Batch: provide answers file
./run-cap-delivery.sh --plan plan.md --requirements reqs.md --project myproj --name myrun \
  --answers answers.yaml

# Bypass: preserve current behavior (fail at validate)
./run-cap-delivery.sh --plan plan.md --requirements reqs.md --project myproj --name myrun \
  --skip-fix
# (validation fails, pipeline halts, no fix)
```

---

## Dependencies

- `contextcore manifest fix` with `--interactive` and `--answers` (implemented)
- `contextcore manifest validate --strict` (implemented)
- REQ-CAP-008: capability-aware question generation in init-from-plan (implemented)
- `run-cap-delivery.sh` in cap-dev-pipe (orchestration script to be modified)
