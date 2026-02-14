# Operator Pipeline Quickstart

Run the ContextCore export pipeline in CI/production, validate outputs with A2A governance gates, and troubleshoot failures — from an operator's perspective.

**Audience**: Operators, SREs, platform engineers who need to run and maintain the ContextCore pipeline rather than author manifests.

**Prerequisite docs**: If you need to *create* a manifest first, see [MANIFEST_ONBOARDING_GUIDE.md](MANIFEST_ONBOARDING_GUIDE.md). This guide assumes you have a valid `.contextcore.yaml` and want to run the pipeline reliably.

---

## Quick Navigation

| I want to... | Go to... |
|--------------|----------|
| Run the full pipeline end-to-end | [End-to-End Pipeline Run](#end-to-end-pipeline-run) |
| Validate the stack is healthy first | [Pre-Flight: Verify Installation](#pre-flight-verify-installation) |
| Integrate into CI/CD | [CI/CD Integration](#cicd-integration) |
| Understand what each gate checks | [Gate Reference](#gate-reference) |
| Fix a broken pipeline run | [Troubleshooting Runbook](#troubleshooting-runbook) |
| Monitor the pipeline itself | [Pipeline Observability](#pipeline-observability) |
| Know which files to expect | [Output File Inventory](#output-file-inventory) |

---

## Pre-Flight: Verify Installation

Before running the pipeline, confirm the environment is healthy.

```bash
# Quick health check (no telemetry emitted)
contextcore install status

# Full verification with telemetry (seeds the installation dashboard)
contextcore install verify

# Verify specific category only
contextcore install verify --category infrastructure
```

**What to look for**: All `critical` requirements should pass. Non-critical failures are advisory — the pipeline will still run, but some features may degrade.

```bash
# If critical failures exist, fix them before proceeding:
contextcore install init --endpoint localhost:4317
```

> **Tip**: `install init` always exits 0 (advisory). For strict CI gating that fails on incomplete installation, use `install verify` instead.

---

## End-to-End Pipeline Run

The ContextCore-specific portion is Steps 0–3. Copy this block and run it.

```bash
# ── Step 0: Validate the manifest ──────────────────────
contextcore manifest validate -p .contextcore.yaml
# Fix any errors before proceeding. Use --strict for tighter checks.

# ── Step 1: Verify installation baseline ───────────────
contextcore install init

# ── Step 2: Export artifact manifest + provenance ──────
contextcore manifest export \
  -p .contextcore.yaml \
  -o ./out/export \
  --emit-provenance \
  --min-coverage 80

# ── Step 3: Gate 1 — Structural integrity (6 checks) ──
contextcore contract a2a-check-pipeline ./out/export
```

If Gate 1 passes, hand off `./out/export/` to the downstream system (plan ingestion or manual review).

### What each step produces

| Step | Command | Key output |
|------|---------|------------|
| 0 | `manifest validate` | Pass/fail + diagnostics (no files written) |
| 1 | `install init` | Telemetry flushed to backend; installation dashboard seeded |
| 2 | `manifest export` | 4–6 files in output dir (see [Output File Inventory](#output-file-inventory)) |
| 3 | `a2a-check-pipeline` | Gate result: PASS/FAIL with per-check breakdown |

---

## Output File Inventory

After `manifest export --emit-provenance`, expect these files:

| File | Always present | Purpose | Operator action |
|------|----------------|---------|-----------------|
| `{project}-artifact-manifest.yaml` | Yes | The contract: what artifacts are needed | Don't edit — this is the source of truth |
| `{project}-projectcontext.yaml` | Yes | K8s CRD with business metadata | Apply to cluster if using the controller |
| `provenance.json` | With `--emit-provenance` | Audit trail: git context, checksums, timestamps | Archive for compliance; required for full Gate 1 |
| `onboarding-metadata.json` | Yes (default) | Schemas, enrichment, checksums for downstream | Don't edit — checksums will break |
| `validation-report.json` | Yes | Export-time diagnostics | Review if export warns; archive for CI |
| `export-quality-report.json` | With `--emit-quality-report` | Quality gate summary | Use for pre-ingestion audit |

**Critical rule**: Never hand-edit generated files. The checksum chain (`source_checksum` → `artifact_manifest_checksum` → `project_context_checksum`) will break and Gate 1 will fail.

---

## CI/CD Integration

### Minimal CI pipeline (GitHub Actions example)

```yaml
name: contextcore-pipeline
on:
  push:
    paths: ['.contextcore.yaml']

jobs:
  pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install ContextCore
        run: pip install contextcore

      - name: Validate manifest
        run: contextcore manifest validate -p .contextcore.yaml --strict

      - name: Export
        run: |
          contextcore manifest export \
            -p .contextcore.yaml \
            -o ./out/export \
            --emit-provenance \
            --min-coverage 80

      - name: Gate 1 — Pipeline integrity
        run: contextcore contract a2a-check-pipeline ./out/export --fail-on-unhealthy

      - name: Archive export
        uses: actions/upload-artifact@v4
        with:
          name: contextcore-export
          path: ./out/export/
```

### Key CI flags

| Flag | Purpose | When to use |
|------|---------|-------------|
| `--fail-on-unhealthy` | Non-zero exit on any gate failure | Gate 1 in CI |
| `--fail-on-issue` | Non-zero exit on any diagnostic issue | Gate 2 in CI |
| `--strict` | Strict schema validation | `manifest validate` in CI |
| `--min-coverage N` | Fail if artifact coverage < N% | `manifest export` in CI |
| `--deterministic-output` | Stable ordering for diff-friendly output | When committing export to Git |
| `--format json` | Machine-readable output | For downstream automation |

### Post-ingestion gate (if using plan ingestion)

```bash
# After plan ingestion completes, run Gate 2:
contextcore contract a2a-diagnose ./out/export \
  --ingestion-dir ./out/plan \
  --fail-on-issue
```

---

## Gate Reference

### Gate 1: `a2a-check-pipeline` (6 checks)

Run after export, before handing off to downstream consumers.

| Check | What it validates | Common failure cause |
|-------|-------------------|---------------------|
| structural-integrity | All expected files present and parseable | Export was interrupted; output dir has stale files from a previous run |
| checksum-chain | source → artifact manifest → CRD checksums match | Generated files were hand-edited; export ran against a different manifest version |
| provenance-consistency | Git metadata and timestamps are coherent | `--emit-provenance` was not used (check is skipped without `provenance.json`) |
| mapping-completeness | Every target has corresponding artifacts | Manifest has targets without artifact definitions |
| gap-parity | Coverage gaps match parsed feature count | Manifest changed between export and gate check |
| design-calibration | Artifact depth tiers match type expectations | Artifact types have wrong complexity estimates |

### Gate 2: `a2a-diagnose` (Three Questions)

Run after plan ingestion, before contractor execution.

| Question | What it validates | Requires |
|----------|-------------------|----------|
| Q1: Contract complete? | Artifact manifest has all required artifacts | `--ingestion-dir` (optional) |
| Q2: Faithfully translated? | Plan features match coverage gaps | `--ingestion-dir` |
| Q3: Faithfully executed? | Task count matches feature count | `--artisan-dir` (optional) |

The diagnostic stops at the first failing question — there's no point checking translation if the contract itself is incomplete.

---

## Troubleshooting Runbook

### Gate 1 fails: checksum-chain

```bash
# 1. Verify no hand edits
sha256sum out/export/*-artifact-manifest.yaml
# Compare with checksum in onboarding-metadata.json

# 2. Re-export from the current manifest
contextcore manifest export -p .contextcore.yaml -o ./out/export --emit-provenance

# 3. Re-run gate
contextcore contract a2a-check-pipeline ./out/export
```

### Gate 1 fails: structural-integrity

```bash
# 1. Check what's in the output directory
ls -la ./out/export/

# 2. Clean and re-export
rm -rf ./out/export/
contextcore manifest export -p .contextcore.yaml -o ./out/export --emit-provenance
```

### Gate 1 fails: mapping-completeness

```bash
# The manifest declares targets that have no artifact definitions.
# Check which targets are missing:
contextcore contract a2a-check-pipeline ./out/export --format json | python3 -m json.tool

# Fix: add artifact definitions for all targets in .contextcore.yaml,
# or use --scan-existing to mark artifacts that already exist on disk:
contextcore manifest export -p .contextcore.yaml -o ./out/export \
  --emit-provenance --scan-existing ./k8s/observability
```

### Export fails: coverage below minimum

```bash
# Lower the threshold for initial runs:
contextcore manifest export -p .contextcore.yaml -o ./out/export --min-coverage 50

# Or add more artifact definitions to the manifest to increase coverage.
# Check current coverage:
contextcore manifest export -p .contextcore.yaml -o ./out/export --dry-run
```

### Stale output suspected

```bash
# Compare source checksum against current manifest
python3 -c "
import hashlib, pathlib
manifest = pathlib.Path('.contextcore.yaml').read_bytes()
print('Current:', hashlib.sha256(manifest).hexdigest()[:16])
"

# Compare with source_checksum in onboarding-metadata.json
python3 -c "
import json
meta = json.load(open('./out/export/onboarding-metadata.json'))
print('Export:', meta.get('source_checksum', 'NOT SET')[:24])
"

# If they differ, the export is stale. Re-export.
```

### Manifest validation fails

```bash
# Get detailed diagnostics
contextcore manifest validate -p .contextcore.yaml --format json

# Common fixes:
# - Missing required field: add to .contextcore.yaml
# - Invalid enum value: check docs/MANIFEST_ONBOARDING_GUIDE.md#field-reference
# - Schema version mismatch: run `contextcore manifest migrate`
```

---

## Pipeline Observability

ContextCore pipelines emit telemetry that you can monitor in Grafana.

### Dashboards

| Dashboard | What it shows | URL |
|-----------|---------------|-----|
| Installation Status | Pre-flight health, requirement pass rates | `http://localhost:3000/d/contextcore-installation` |
| Project Portfolio | Cross-project status, task progress | `http://localhost:3000/d/contextcore-portfolio` |

### Key metrics to watch

| Metric | Meaning | Alert threshold |
|--------|---------|-----------------|
| `contextcore_install_completeness_percent` | Installation health | < 80% |
| `contextcore_install_requirement_status_ratio` | Per-requirement pass rate | Any critical requirement = 0 |

### Log queries (Loki)

```logql
# Export events
{service_name="contextcore"} |= "manifest export"

# Gate results
{service_name="contextcore"} |= "a2a-check-pipeline" OR "a2a-diagnose"

# Installation verification
{service_name="contextcore"} |= "install"
```

---

## Quick Reference Card

```bash
# ── Validate ───────────────────────────────────────────
contextcore manifest validate -p .contextcore.yaml           # basic
contextcore manifest validate -p .contextcore.yaml --strict  # strict

# ── Install check ─────────────────────────────────────
contextcore install status                                   # quick (no telemetry)
contextcore install verify                                   # full (emits telemetry)

# ── Export ─────────────────────────────────────────────
contextcore manifest export -p .contextcore.yaml -o ./out/export --emit-provenance
contextcore manifest export -p .contextcore.yaml -o ./out/export --dry-run  # preview

# ── Gates ──────────────────────────────────────────────
contextcore contract a2a-check-pipeline ./out/export                        # Gate 1
contextcore contract a2a-check-pipeline ./out/export --fail-on-unhealthy   # CI mode
contextcore contract a2a-diagnose ./out/export --ingestion-dir ./out/plan  # Gate 2
contextcore contract a2a-diagnose ./out/export --fail-on-issue             # CI mode

# ── Troubleshoot ───────────────────────────────────────
contextcore manifest export -p .contextcore.yaml -o ./out/export --dry-run  # preview
contextcore contract a2a-check-pipeline ./out/export --format json         # machine-readable
```

---

## Related Documentation

| Document | What it covers |
|----------|----------------|
| [MANIFEST_ONBOARDING_GUIDE.md](MANIFEST_ONBOARDING_GUIDE.md) | Creating and editing `.contextcore.yaml` manifests |
| [EXPORT_PIPELINE_ANALYSIS_GUIDE.md](EXPORT_PIPELINE_ANALYSIS_GUIDE.md) | Full 7-step pipeline architecture and defense-in-depth |
| [A2A_GATE_REQUIREMENTS.md](A2A_GATE_REQUIREMENTS.md) | Formal requirements for Gate 1 and Gate 2 |
| [MANIFEST_EXPORT_REQUIREMENTS.md](MANIFEST_EXPORT_REQUIREMENTS.md) | Formal requirements for export and validate |
| [MANIFEST_EXPORT_TROUBLESHOOTING.md](MANIFEST_EXPORT_TROUBLESHOOTING.md) | Detailed troubleshooting for export-specific issues |
| [INSTALLATION.md](INSTALLATION.md) | Full installation guide (Docker Compose, Kind) |
| [A2A_QUICKSTART.md](A2A_QUICKSTART.md) | A2A contract validation and Python API quickstart |
