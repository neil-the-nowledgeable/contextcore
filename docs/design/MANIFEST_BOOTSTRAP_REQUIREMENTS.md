# Manifest Bootstrap Requirements

Purpose: define the behavioral requirements for `contextcore manifest init` and `contextcore manifest migrate` — the commands that create and transform `.contextcore.yaml` manifests. These are the entry points into the ContextCore pipeline.

This document is intentionally living guidance. Update it as the commands evolve.

---

## Vision

Before anything in the pipeline can run, a valid `.contextcore.yaml` manifest must exist. Two commands address this:

- **`manifest init`** — creates a new manifest from scratch with a starter template.
- **`manifest migrate`** — converts an existing v1.1 manifest to v2.0 format.

A third command, `manifest init-from-plan`, performs programmatic inference from plan and requirements documents. Its requirements are documented separately in `plans/init-from-plan/INIT_FROM_PLAN_HIGH_LEVEL_REQUIREMENTS.md`.

All three commands produce the same output shape: a valid v2 `.contextcore.yaml` that can be consumed by `manifest validate`, `manifest export`, and downstream pipeline steps.

---

## Pipeline Placement

Pre-pipeline: these commands run before the 7-step pipeline begins.

```
manifest init  ─────────┐
manifest init-from-plan ─┼──► manifest validate ──► manifest export ──► ...
manifest migrate ────────┘
```

The typical flow after bootstrap:
1. Create manifest (init, init-from-plan, or migrate)
2. Edit manifest to refine project details
3. `contextcore manifest validate` — verify the manifest
4. `contextcore manifest export` — produce the artifact contract
5. `contextcore contract a2a-check-pipeline` — Gate 1
6. Continue pipeline...

---

## Manifest Init

### Purpose

Create a new `.contextcore.yaml` manifest with a starter template. Provides a structured scaffold that a human or automated process fills in with project-specific details.

### Functional Requirements

#### Template Generation

1. **v2 template (default)**
   - Must produce a valid v2 manifest with all required sections scaffolded.
   - Must include: `apiVersion`, `kind`, `version`, `metadata` (name, owners, changelog), `spec` (project, business, requirements, targets, observability, risks), `strategy` (objectives, tactics), `guidance` (constraints, questions).
   - Template values must be clearly identifiable as placeholders (e.g., `"your-service"`, `"engineering"`, `"99.9"`).
   - Must include `guidance.questions` with at least one example question.
   - Must include `dashboardPlacement` in target parameters.

2. **v1.1 template**
   - Must produce a valid v1.1 manifest when `--version v1.1` is specified.
   - Must include: `apiVersion`, `kind`, `version`, `metadata`, `spec`, `objectives`, `strategies`, `insights`.

3. **Name normalization**
   - Must normalize the project name: strip whitespace, lowercase, replace spaces with hyphens.
   - Must warn the user when normalization changes the name.

#### Safety

4. **Overwrite protection**
   - Must refuse to overwrite an existing file unless `--force` is specified.
   - Must display a clear error message directing the user to use `--force`.

5. **Post-write validation** (default: enabled)
   - Must validate the generated manifest immediately after writing.
   - Must fail with non-zero exit code if the template itself is invalid (indicates a bug in the template).
   - Must report validation warnings without failing (unless `--strict` were used on validate).
   - Must be opt-out via `--no-validate`.

#### Guidance

6. **Next steps output**
   - Must print numbered next steps after successful creation:
     1. Edit the manifest to add project details
     2. Validate the manifest
     3. Run `install init` (infrastructure readiness)
     4. Run `manifest export` with `--emit-provenance`
     5. Run `a2a-check-pipeline` (Gate 1)
     6. Run plan ingestion, then `a2a-diagnose` (Gate 2)

### CLI Surface

```
contextcore manifest init
  --path / -p       (default: .contextcore.yaml)  Output path
  --name            (required)   Project/manifest name
  --version         (default: v2)  Manifest version: v1.1 | v2
  --force           (flag)       Overwrite existing file
  --validate        (default: enabled)  Post-write validation
  --no-validate                  Skip post-write validation
```

### Non-Functional Requirements

- **Offline operation**: Must work without network access.
- **Determinism**: Same `--name` and `--version` must produce the same template content.
- **Speed**: Must complete in under 1 second.
- **Template quality**: Template must pass `manifest validate --strict` without errors.

---

## Manifest Migrate

### Purpose

Convert a v1.1 manifest to v2.0 format. This is a non-destructive migration that preserves all existing data while restructuring it into the v2 schema.

### Functional Requirements

#### Migration Logic

1. **Structure transformation**
   - Must flatten the v1.1 strategy/tactic hierarchy into v2 format.
   - Must add the `guidance` section (empty by default if no guidance data exists in v1.1).
   - Must preserve all existing data — no fields should be dropped during migration.
   - Must update `apiVersion` and `version` fields to v2 values.

2. **Changelog entry**
   - Must append a migration entry to the changelog with: version, date, author (`contextcore-migrate`), and change description.
   - Must support a custom `--note` for the changelog entry.

#### Safety

3. **Backup on in-place migration**
   - When `--in-place` is used, must create a backup file (`{filename}.v1.yaml.bak`) before overwriting.
   - Must report the backup path to the user.

4. **Dry-run support**
   - Must support `--dry-run` to preview the migration output without writing files.
   - Dry-run must display the full migrated YAML to stdout.

5. **Error handling**
   - Must fail with a clear error if the input is not a valid v1.1 manifest.
   - Must fail with a clear error on unexpected parsing errors.

#### Output Modes

6. **Three output modes**
   - `--in-place`: Overwrite the input file (with backup).
   - `--output <path>`: Write to a specified file.
   - Default (no flag): Write to stdout.

### CLI Surface

```
contextcore manifest migrate
  --path / -p       (required)   Path to the v1.1 manifest file
  --output / -o     (optional)   Output file path (default: stdout)
  --in-place / -i   (flag)       Overwrite input file (creates backup)
  --note            (optional)   Custom migration note for changelog
  --dry-run         (flag)       Preview without writing
```

### Non-Functional Requirements

- **Non-destructive**: Original data must never be lost. In-place always creates backup.
- **Offline operation**: Must work without network access.
- **Determinism**: Same input must produce the same migrated output.
- **Completeness**: Every field in the v1.1 manifest must have a defined mapping to v2 (even if some map to empty sections).

---

## Invariants

These must hold true for all bootstrap commands:

1. Output of `manifest init` must pass `manifest validate` without errors.
2. Output of `manifest migrate` must pass `manifest validate` without errors.
3. Output of `manifest init-from-plan` must pass `manifest validate` without errors (per its own requirements doc).
4. All three commands produce manifests that `manifest export` can consume.
5. `manifest migrate --in-place` always creates a backup before modifying the file.
6. Name normalization is consistent: `"My Project"` → `"my-project"` everywhere.

---

## Relationship to Other Commands

| Command | Relationship |
|---------|-------------|
| `manifest init-from-plan` | Alternative bootstrap path — infers fields from plan documents. Separate requirements doc. |
| `manifest validate` | Downstream — validates the manifest these commands produce |
| `manifest show` | Utility — displays manifest contents in various formats |
| `manifest distill-crd` | Utility — extracts K8s CRD from a manifest |
| `manifest export` | Downstream — reads the manifest to produce the artifact contract |
| `manifest create` | Parallel — drafts plan artifacts from the same manifest |

---

## Related Docs

- `plans/init-from-plan/INIT_FROM_PLAN_HIGH_LEVEL_REQUIREMENTS.md` — init-from-plan requirements
- `docs/MANIFEST_CREATE_REQUIREMENTS.md` — manifest create requirements
- `docs/MANIFEST_EXPORT_REQUIREMENTS.md` — export and validate requirements
- `docs/MANIFEST_ONBOARDING_GUIDE.md` — user-facing manifest lifecycle guide
- `docs/CONTEXT_MANIFEST_VALUE_PROPOSITION.md` — manifest v2 value proposition
