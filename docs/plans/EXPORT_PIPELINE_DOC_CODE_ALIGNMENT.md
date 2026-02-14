# Export Pipeline: Documentation & Code Alignment Plan

**Created:** 2026-02-14
**Scope:** ContextCore-specific documentation and code updates identified during a full
7-step pipeline audit comparing `EXPORT_PIPELINE_ANALYSIS_GUIDE.md` and
`contextcore-a2a-comms-design.md` against actual code in both ContextCore and startd8-sdk.

**Related audit:** A parallel plan exists in startd8-sdk for SDK-side code fixes.

---

## Summary

| Category | Count | Priority Mix |
|----------|-------|-------------- |
| Documentation fixes | 8 | 5 medium, 3 low |
| Code fixes | 2 | 1 high, 1 low |

---

## Documentation Updates

### D1 — A2A Design Doc: File count is stale (4 → 6)

**File:** `docs/design/contextcore-a2a-comms-design.md` line 69
**Problem:** Says "produces up to 4 files" but the export implementation produces up to **6 files**.
`validation-report.json` (always) and `export-quality-report.json` (`--emit-quality-report`)
were added but the design doc was never updated.
**Fix:** Change "up to 4 files" to "up to 6 files" and add rows 5-6 to the file table (lines 71-76).
**Priority:** Medium

### D2 — A2A Design Doc: Step numbering in section headers

**File:** `docs/design/contextcore-a2a-comms-design.md` lines 96, 108
**Problem:** "Plan Ingestion Phases **(Step 3)**" should be **(Step 4)**.
"Artisan Workflow Phases **(Step 4)**" should be **(Step 6)**.
The pipeline diagram correctly shows 7 steps, but these section headers use the wrong numbers.
**Fix:** Change "(Step 3)" to "(Step 4)" and "(Step 4)" to "(Step 6)".
**Priority:** Medium

### D3 — A2A Design Doc: Phase enum table missing `OTHER`

**File:** `docs/design/contextcore-a2a-comms-design.md` lines 300-311
**Problem:** Table lists 10 Phase enum values but code (`models.py` line ~39) has 11 — `OTHER` is undocumented.
**Fix:** Add `OTHER` row to the Phase Enum Coverage table.
**Priority:** Low

### D4 — Export Pipeline Guide: `--emit-task-spans` listed but not implemented

**File:** `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` line 117
**Problem:** The contract table's `TaskSpanContract` row says "Emitted by: Export (optional `--emit-task-spans`)".
This flag does NOT exist in the CLI. It is a planned feature (see `docs/plans/EXPORT_TASK_TRACKING_PROJECT_PLAN.md`).
**Fix:** Change to "Export (planned — `--emit-task-spans` not yet implemented)" or remove and add a footnote.
**Priority:** Low

### D5 — Export Pipeline Guide: `parameter_sources` consumption overstated

**File:** `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` lines 78, 184
**Problem:** The onboarding-metadata field table (line 78) says `parameter_sources` is "Used by: Artisan DESIGN, IMPLEMENT".
The Artisan IMPLEMENT description (line 184) says "The `parameter_sources` from onboarding metadata
tell the generator exactly which manifest or CRD fields to read for each parameter."
**Reality:** startd8-sdk code never reads `parameter_sources`. It's available in onboarding metadata
but not consumed by any phase handler.
**Fix:** Change "Used by" to "Available for: Artisan DESIGN, IMPLEMENT (not yet consumed — see startd8-sdk code fix plan)".
Update line 184 to say "The `parameter_sources` from onboarding metadata *are available to* tell the generator
which fields to read (consumption not yet implemented)."
**Priority:** Medium

### D6 — Export Pipeline Guide: `semantic_conventions` consumption overstated

**File:** `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` line 81
**Problem:** Says `semantic_conventions` is "Used by: Artisan DESIGN, IMPLEMENT".
startd8-sdk code never reads `semantic_conventions`.
**Fix:** Same pattern as D5 — change to "Available for" with a note about planned consumption.
**Priority:** Medium

### D7 — Export Pipeline Guide: FINALIZE provenance chain verification overstated

**File:** `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` line 196
**Problem:** Says FINALIZE produces "provenance chain (`source_checksum` from export → onboarding → seed → finalize)
enables end-to-end verification." The artisan FINALIZE phase produces per-artifact sha256 checksums
and a status rollup, but does NOT verify the source_checksum provenance chain. The `source_checksum`
is present in the seed but never compared or recorded in the finalize manifest.
**Fix:** Split into what exists ("per-artifact sha256 checksums and status rollup") and what's planned
("provenance chain verification — source_checksum comparison — is not yet implemented in FINALIZE").
**Priority:** Medium

### D8 — Pipeline Checker docstring says 5 gates, code runs 6

**File:** `src/contextcore/contracts/a2a/pipeline_checker.py` lines 7-12
**Problem:** Module/class docstring says 5 gates but the implementation runs 6 (design calibration was added later).
**Fix:** Update docstring to say 6 gates.
**Priority:** Low

---

## Code Updates

### C1 — `onboarding.py` does not generate `design_calibration_hints` (HIGH)

**File:** `src/contextcore/utils/onboarding.py`
**Consumer:** `src/contextcore/contracts/a2a/pipeline_checker.py` line 568
**Problem:** The pipeline checker's Gate 6 (design calibration) reads
`self._metadata.get("design_calibration_hints")` from onboarding metadata. If the key is absent,
the gate is **skipped** entirely (line 800-806). But `onboarding.py` does NOT generate
`design_calibration_hints`. It generates `expected_output_contracts` (line 516), which is a
related but different structure (max_lines/tokens per type vs depth/LOC ranges per type).

The actual exported `out/enrichment-validation/onboarding-metadata.json` contains
`design_calibration_hints`, but this data was either hand-added or produced by a prior version
that no longer matches the current `onboarding.py` code.

**Impact:** Gate 6 (design calibration) always skips in production exports, silently disabling
one of the 6 pipeline integrity checks.

**Fix options:**
1. **Generate `design_calibration_hints` in `onboarding.py`** — derive from artifact types and
   `expected_output_contracts`. For each artifact type with gaps, emit `expected_depth`,
   `expected_loc_range`, and `red_flag` based on type conventions.
2. **Make pipeline checker fall back to `expected_output_contracts`** — if `design_calibration_hints`
   is absent, derive calibration from `expected_output_contracts` at check time.

**Recommended:** Option 1 (generate in the producer).

**Priority:** High

### C2 — `--emit-task-spans` not implemented

**File:** `src/contextcore/cli/manifest.py`
**Problem:** Feature is designed and planned (see `docs/plans/EXPORT_TASK_TRACKING_*`) but the
CLI flag does not exist. The `TaskSpanContract` type is defined in the A2A models but the export
command doesn't emit task spans.
**Fix:** Implement as per the existing project plan.
**Priority:** Low (planned feature, not a regression)

---

## Cross-Repository Notes

The following issues affect startd8-sdk and are tracked in a separate plan there:

| ID | Description | startd8-sdk files |
|----|-------------|-------------------|
| SDK-C1 | Artisan workflow doesn't verify `source_checksum` from seed | `context_seed_handlers.py` |
| SDK-C2 | `parameter_sources` from onboarding metadata not consumed | `context_seed_handlers.py` |
| SDK-C3 | `semantic_conventions` from onboarding metadata not consumed | `context_seed_handlers.py` |
| SDK-C4 | FINALIZE manifest doesn't record `source_checksum` for provenance | `context_seed_handlers.py` |
| SDK-C5 | SCAFFOLD doesn't read `output_conventions` from onboarding | `context_seed_handlers.py` |

---

## Verification

After applying fixes, validate with:

```bash
# Verify design_calibration_hints generation
contextcore manifest export -p .contextcore.yaml -o /tmp/test-export --emit-provenance
python3 -c "import json; d=json.load(open('/tmp/test-export/onboarding-metadata.json')); print('design_calibration_hints' in d)"

# Verify Gate 6 no longer skips
contextcore contract a2a-check-pipeline /tmp/test-export
# Should show 6/6 gates (not 5/6 + 1 skipped)

# Verify docstring
grep -n "gates" src/contextcore/contracts/a2a/pipeline_checker.py | head -5
```
