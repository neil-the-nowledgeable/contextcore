# Context Manifest v2.0 Prime Contractor Plan

## Goal

Implement **Context Manifest v2.0 ("Active Control Plane")** improvements using the **Startd8 Prime Contractor** workflow so we get:
- Small, conflict-minimized feature increments
- Checkpoint validation after each integration
- Clear rollback / retry behavior when something fails

This plan assumes we keep **v1.1** stable and introduce **v2.0** as additive + migrated-by-tooling (no breaking changes to v1.1 parsing unless explicitly opted in).

---

## Constraints (Prime Contractor friendly)

- **Keep features small**: each feature should touch 1–3 target files and stay well under truncation limits.
- **Avoid overlap**: do not schedule multiple features that heavily modify the same file in parallel (especially `src/contextcore/models/manifest.py`).
- **Prefer additive modules**: add `manifest_v2.py`, `cli/manifest.py`, etc., instead of rewriting existing modules.
- **Checkpoints per feature**: syntax → imports → unit tests (at minimum: `tests/test_manifest.py` plus any new tests).
- **Deliverable validation**: verify expected files exist before marking features complete *(Leg 11 #9)*.

---

## v2.0 Feature Breakdown (Prime Contractor Queue)

### Feature V2-01a: Create v2 schema skeleton

- **Intent**: Add v2 model file without breaking v1.1.
- **Target files**:
  - `src/contextcore/models/manifest_v2.py` (new)
- **Key design**:
  - v2 has explicit sections: `strategy`, `guidance`, `spec`, `insights`
  - keep `apiVersion/kind/metadata` alignment
  - reuse existing enums from `contracts/types.py`
- **Deliverables**:
  - `src/contextcore/models/manifest_v2.py` exists, >80 lines
  - Contains `class ContextManifestV2(BaseModel)`
- **Tests to Add**:
  - `tests/test_manifest_v2.py::test_v2_model_basic_structure` (new file)
- **Acceptance**:
  ```bash
  test -f src/contextcore/models/manifest_v2.py && \
  python3 -c "from contextcore.models.manifest_v2 import ContextManifestV2; print('OK')"
  ```

### Feature V2-01b: Export v2 models from __init__.py

- **Intent**: Make v2 models importable from `contextcore.models`.
- **Depends on**: V2-01a
- **Target files**:
  - `src/contextcore/models/__init__.py` (modify)
- **Deliverables**:
  - `__init__.py` contains `from contextcore.models.manifest_v2 import ContextManifestV2`
- **Acceptance**:
  ```bash
  grep -q "ContextManifestV2" src/contextcore/models/__init__.py && \
  python3 -c "from contextcore.models import ContextManifestV2; print('OK')"
  ```

### Feature V2-02: Add AgentGuidanceSpec models (schema + validation)

- **Intent**: Make governance first-class (focus/constraints/questions).
- **Depends on**: V2-01b
- **Target files**:
  - `src/contextcore/models/manifest_v2.py` (extend)
- **Semantic Checks** *(Leg 11 #5)*:
  - `ConstraintSeverity` must reuse `contextcore.contracts.types.ConstraintSeverity`
  - `QuestionStatus` must reuse `contextcore.contracts.types.QuestionStatus`
  - `Focus.areas` must be `List[str]`, not `str`
- **Deliverables**:
  - `manifest_v2.py` contains `class AgentGuidanceSpec`
  - `manifest_v2.py` contains `class Constraint`, `class Focus`, `class Question`
- **Tests to Add**:
  - `tests/test_manifest_v2.py::test_guidance_constraint_requires_id_and_rule`
  - `tests/test_manifest_v2.py::test_guidance_uses_canonical_enums`
- **Acceptance**:
  ```bash
  python3 -c "from contextcore.models.manifest_v2 import AgentGuidanceSpec; print('OK')" && \
  grep -q "ConstraintSeverity" src/contextcore/models/manifest_v2.py
  ```

### Feature V2-03: Loader that selects v1.1 vs v2 by `apiVersion`

- **Intent**: One entrypoint to load manifests, returning the right model.
- **Depends on**: V2-02
- **Target files**:
  - `src/contextcore/models/manifest_loader.py` (new)
  - `src/contextcore/models/manifest.py` (optional: re-export loader)
- **Behavior**:
  - If `apiVersion` is `contextcore.io/v1alpha2` → parse `ContextManifestV2`
  - Else → parse `ContextManifest` (v1.1) using existing `load_context_manifest()`
- **Deliverables**:
  - `manifest_loader.py` exists with `load_manifest()` function
  - Function returns `ContextManifest | ContextManifestV2` based on apiVersion
- **Tests to Add**:
  - `tests/test_manifest_v2.py::test_loader_returns_v1_for_v1alpha1`
  - `tests/test_manifest_v2.py::test_loader_returns_v2_for_v1alpha2`
- **Acceptance**:
  ```bash
  python3 -c "from contextcore.models.manifest_loader import load_manifest; print('OK')"
  ```

### Feature V2-04: CLI commands for v2 lifecycle (validate / migrate / distill)

- **Intent**: Tooling is required for adoption; keep schema from becoming shelfware.
- **Depends on**: V2-03
- **Target files**:
  - `src/contextcore/cli/manifest.py` (new Click group)
  - `src/contextcore/cli/__init__.py` (register group)
- **Commands**:
  - `contextcore manifest validate --path ...`
  - `contextcore manifest distill-crd --path ... --namespace ...`
  - `contextcore manifest migrate --from v1.1 --to v2.0` (initially: "structural lift" only)
- **Deliverables**:
  - `cli/manifest.py` exists with `@click.group()` named `manifest`
  - CLI group registered in `cli/__init__.py`
- **Tests to Add**:
  - `tests/test_manifest_v2.py::test_cli_validate_returns_nonzero_on_error`
- **Acceptance**:
  ```bash
  contextcore manifest --help | grep -q "validate" && \
  contextcore manifest --help | grep -q "distill-crd"
  ```

### Feature V2-05: Migration transform v1.1 → v2 (non-destructive)

- **Intent**: Provide a safe upgrade path.
- **Depends on**: V2-04
- **Target files**:
  - `src/contextcore/models/manifest_migrate.py` (new)
  - `tests/test_manifest_v2.py` (extend)
- **Rules**:
  - Move `objectives/strategies` into `strategy.*`
  - Keep `spec` unchanged
  - Default `guidance` empty
  - Preserve `metadata.changelog` and append a migration entry
- **Deliverables**:
  - `manifest_migrate.py` exists with `migrate_v1_to_v2()` function
  - Function returns valid `ContextManifestV2` dict
- **Tests to Add**:
  - `tests/test_manifest_v2.py::test_migrate_example_yaml_produces_valid_v2`
  - `tests/test_manifest_v2.py::test_migrate_preserves_changelog`
- **Acceptance**:
  ```bash
  python3 -c "
  from contextcore.models.manifest_migrate import migrate_v1_to_v2
  from contextcore.models.manifest import load_context_manifest
  v1 = load_context_manifest('examples/context_manifest_example.yaml')
  v2_dict = migrate_v1_to_v2(v1)
  print('Migration OK')
  "
  ```

### Feature V2-06 (optional): Guidance write-back (agent answers questions)

- **Intent**: Close the loop from "read guidance" to "update guidance state".
- **Depends on**: V2-05
- **Target files**:
  - `src/contextcore/agent/guidance.py` (extend to support local file mode)
  - `src/contextcore/models/manifest_loader.py` (read/write helpers)
- **Deliverables**:
  - `guidance.py` has `GuidanceResponder.answer_question_local()` method
  - Method updates YAML file in-place
- **Tests to Add**:
  - `tests/test_manifest_v2.py::test_guidance_writeback_marks_question_answered`
- **Acceptance**:
  - A function can mark a question as answered in a v2 YAML file (local), preserving formatting as best-effort

---

## Prime Contractor Execution Steps

### Step -1: Verify v1.1 Baseline *(Leg 11 #15)*

Before starting v2.0 work, verify the v1.1 implementation is stable:

```bash
cd /Users/neilyashinsky/Documents/dev/ContextCore

# Verify v1.1 code works
python3 -c "from contextcore.models.manifest import ContextManifest, load_context_manifest; print('v1.1 OK')"

# Verify example parses
python3 -c "
from contextcore.models.manifest import load_context_manifest
m = load_context_manifest('examples/context_manifest_example.yaml')
print(f'v1.1 example OK: {m.metadata.name}')
"

# Run existing tests
python3 -m pytest -q -o addopts='' -p no:cov -p no:cacheprovider tests/test_manifest.py
```

**If any of the above fail, fix v1.1 before proceeding.**

### Step 0: Git Safety Pre-Flight *(Leg 11 #12)*

```bash
cd /Users/neilyashinsky/Documents/dev/ContextCore

# Check git status - must be clean
git status --porcelain

# If ANY output, either commit or stash:
# Option A: Commit current work
git add -A && git commit -m "WIP: checkpoint before v2.0 implementation"

# Option B: Stash for safety
git stash push -m "pre-v2-implementation-$(date +%Y%m%d_%H%M%S)"
```

### Step 1: Create the queue (manual add)

Add features in order (IDs should be stable, filenames listed to help conflict detection):

```bash
python3 scripts/prime_contractor/cli.py add "V2-01a Manifest v2 skeleton" \
  --description "Create src/contextcore/models/manifest_v2.py with ContextManifestV2" \
  --target-files src/contextcore/models/manifest_v2.py

python3 scripts/prime_contractor/cli.py add "V2-01b Export v2 models" \
  --description "Export ContextManifestV2 from models/__init__.py" \
  --depends-on v2-01a_manifest_v2_skeleton \
  --target-files src/contextcore/models/__init__.py

python3 scripts/prime_contractor/cli.py add "V2-02 Agent guidance schema" \
  --description "Add AgentGuidanceSpec (focus/constraints/questions) to v2 schema" \
  --depends-on v2-01b_export_v2_models \
  --target-files src/contextcore/models/manifest_v2.py

python3 scripts/prime_contractor/cli.py add "V2-03 Manifest loader" \
  --description "Load v1.1 vs v2 by apiVersion" \
  --depends-on v2-02_agent_guidance_schema \
  --target-files src/contextcore/models/manifest_loader.py src/contextcore/models/manifest.py

python3 scripts/prime_contractor/cli.py add "V2-04 Manifest CLI" \
  --description "contextcore manifest validate/distill/migrate" \
  --depends-on v2-03_manifest_loader \
  --target-files src/contextcore/cli/manifest.py src/contextcore/cli/__init__.py

python3 scripts/prime_contractor/cli.py add "V2-05 v1.1 to v2 migration" \
  --description "Non-destructive migration transform and tests" \
  --depends-on v2-04_manifest_cli \
  --target-files src/contextcore/models/manifest_migrate.py tests/test_manifest_v2.py
```

**Verify queue:**
```bash
python3 scripts/prime_contractor/cli.py status
```

**Expected conflict detection output** *(Leg 7 #3)*:
```
⚠️  POTENTIAL CONFLICTS DETECTED:
   1 target(s) have multiple features:
   • src/contextcore/models/manifest_v2.py:
     - V2-01a Manifest v2 skeleton
     - V2-02 Agent guidance schema

This is EXPECTED because V2-02 depends on V2-01a.
The Prime Contractor processes them sequentially, so this is not a true conflict.
```

### Step 2: Validate backlog (truncation + integrity)

```bash
python3 scripts/prime_contractor/cli.py validate
```

### Step 2.5: Dry-Run End-to-End *(Leg 11 #11)*

Before live execution, run a dry-run to catch configuration issues:

```bash
python3 scripts/prime_contractor/cli.py run --dry-run

# Expected output should show for each feature:
#   [DRY RUN] Would generate: V2-01a Manifest v2 skeleton
#   [DRY RUN] Would update: src/contextcore/models/manifest_v2.py
#   ...
```

**Only proceed to Step 3 if dry-run completes without errors.**

### Step 3: Run with continuous integration

```bash
python3 scripts/prime_contractor/cli.py run --auto-commit --strict
```

If you want to reduce risk further (one feature at a time with manual review):

```bash
python3 scripts/prime_contractor/cli.py run --auto-commit --strict --max-features 1
```

### Step 4: Validate deliverables after each feature *(Leg 11 #9)*

After each feature completes, verify deliverables exist:

```bash
# V2-01a validation
test -f src/contextcore/models/manifest_v2.py && echo "✓ V2-01a: manifest_v2.py exists"

# V2-01b validation
grep -q "ContextManifestV2" src/contextcore/models/__init__.py && echo "✓ V2-01b: export added"

# V2-02 validation
grep -q "AgentGuidanceSpec" src/contextcore/models/manifest_v2.py && echo "✓ V2-02: guidance schema added"

# V2-03 validation
test -f src/contextcore/models/manifest_loader.py && echo "✓ V2-03: loader exists"

# V2-04 validation
test -f src/contextcore/cli/manifest.py && echo "✓ V2-04: CLI exists"

# V2-05 validation
test -f src/contextcore/models/manifest_migrate.py && echo "✓ V2-05: migrate exists"
```

---

## Recovery from Failed Integration *(Leg 7 #2, Leg 11 #10)*

### 1. Identify failure point

```bash
python3 scripts/prime_contractor/cli.py status
# Look for FAILED or BLOCKED status
```

### 2. Check for partial integration

```bash
git diff --name-only
# If target files modified, decide: keep or revert
```

### 3. Reset appropriately *(state-aware reset - Leg 11 #10)*

```bash
# If generated files exist but integration failed:
python3 scripts/prime_contractor/cli.py retry <feature_id>

# If no generated files (development failed):
# The retry command will detect this and restart from development
```

### 4. Revert if needed

```bash
# Revert specific file to last commit
git checkout -- <file>

# Or restore from backup if one was created
ls *.backup 2>/dev/null && echo "Backup files available"
```

### 5. Clear and restart (nuclear option)

```bash
# Clear queue entirely and start fresh
python3 scripts/prime_contractor/cli.py clear -f

# Re-run Step 1 to rebuild queue
```

---

## Checkpoint Expectations (per feature)

Minimum checks per feature:
- **Syntax**: `python3 -m py_compile` on touched files (Prime Contractor does this)
- **Imports**: `python3 -c "import contextcore"` plus targeted imports
- **Semantic**: Verify enums reuse canonical types *(Leg 11 #5)*
- **Tests**:
  - `python3 -m pytest -q -o addopts='' -p no:cov -p no:cacheprovider tests/test_manifest.py tests/test_manifest_v2.py`

### Feature-specific test expectations

| Feature | New Tests Required | Test File |
|---------|-------------------|-----------|
| V2-01a | `test_v2_model_basic_structure` | `tests/test_manifest_v2.py` (new) |
| V2-01b | (covered by V2-01a import test) | - |
| V2-02 | `test_guidance_constraint_requires_id_and_rule`, `test_guidance_uses_canonical_enums` | `tests/test_manifest_v2.py` |
| V2-03 | `test_loader_returns_v1_for_v1alpha1`, `test_loader_returns_v2_for_v1alpha2` | `tests/test_manifest_v2.py` |
| V2-04 | `test_cli_validate_returns_nonzero_on_error` | `tests/test_manifest_v2.py` |
| V2-05 | `test_migrate_example_yaml_produces_valid_v2`, `test_migrate_preserves_changelog` | `tests/test_manifest_v2.py` |

---

## Definition of Done (v2.0)

- [ ] `ContextManifestV2` exists and validates
- [ ] `AgentGuidanceSpec` reuses canonical enums from `contracts/types.py`
- [ ] Loader can parse both v1.1 and v2 based on `apiVersion`
- [ ] CLI supports `manifest validate`, `manifest distill-crd`, `manifest migrate`
- [ ] Migration transforms `examples/context_manifest_example.yaml` into a valid v2 manifest
- [ ] v1.1 remains supported (no breaking changes)
- [ ] All deliverables validated (files exist, contain expected content)
- [ ] All new tests pass
- [ ] Git history shows atomic commits per feature

---

## Lessons Learned References

This plan incorporates patterns from:

| Pattern | Source | Applied In |
|---------|--------|------------|
| Deliverable Validation Gate | Leg 11 #9 | Step 4, Deliverables sections |
| Git Safety Pre-flight | Leg 11 #12 | Step 0 |
| State-Aware Reset | Leg 11 #10 | Recovery section |
| Dry-Run End-to-End | Leg 11 #11 | Step 2.5 |
| Semantic Validation | Leg 11 #5 | V2-02 Semantic Checks |
| Multi-file Split | Leg 11 #4 | V2-01 split into V2-01a/V2-01b |
| Registry Verification | Leg 11 #15 | Step -1 |
| Prime Contractor Pattern | Leg 7 #3 | Overall workflow |
| Conflict Detection | Leg 7 #3 | Step 1 expected output |

---

## Changelog

| Date | Version | Actor | Summary |
|------|---------|-------|---------|
| 2026-02-05 | 1.0.0 | agent:claude-code | Initial plan |
| 2026-02-05 | 1.1.0 | agent:claude-code | Added Lessons Learned improvements: deliverable validation, git safety, dry-run, recovery, semantic checks, feature split |