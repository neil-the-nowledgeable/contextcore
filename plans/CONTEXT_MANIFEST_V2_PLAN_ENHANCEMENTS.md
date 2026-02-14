# Context Manifest v2.0 Prime Contractor Plan - Enhancement Review

## Review Summary

**Date**: 2026-02-05  
**Reviewer**: agent:claude-code (new model iteration)  
**Plan Version Reviewed**: 1.1.0  
**Status**: ✅ Plan is solid, with 7 additional enhancements recommended

---

## Validation: Plan Approach Assessment

### ✅ Strengths

1. **Feature decomposition** is well-structured with clear dependencies
2. **Target files** are explicit (enables conflict detection)
3. **Acceptance criteria** exist for each feature
4. **Checkpoint expectations** cover syntax → imports → tests
5. **Definition of Done** is clear
6. **Lessons Learned integration** already includes many patterns (git safety, deliverable validation, dry-run, recovery)

### ⚠️ Areas for Improvement

The following enhancements leverage additional patterns from `/Users/neilyashinsky/Documents/craft/Lessons_Learned` that strengthen the plan:

---

## Enhancement 1: Truncation Prevention Gate *(Leg 11 #4, workflow.py:129-130)*

**Problem**: Features that exceed token/line limits will truncate during generation, producing incomplete code.

**Current State**: Plan mentions "stay well under truncation limits" but doesn't specify HOW to validate.

**Solution**: Add explicit size validation before generation:

```bash
# Add to Step 2 (before Step 3):
python3 scripts/prime_contractor/cli.py validate --check-size

# Expected limits (from workflow.py):
# - max_lines_per_feature: 150
# - max_tokens_per_feature: 500
```

**Rationale**: 
- **Business**: Prevents wasted API costs on incomplete generations
- **Technical**: Catches size issues before generation, not after integration

**Action**: Add size validation step to Step 2, with warnings if features exceed limits.

---

## Enhancement 2: Multi-File Deliverable Validation *(Leg 11 #4)*

**Problem**: Features with multiple target files may produce partial output (only some files generated).

**Current State**: Plan has "Deliverables" sections but doesn't explicitly validate ALL files exist.

**Solution**: Explicitly validate ALL expected files exist:

```bash
# After each feature completes, verify ALL deliverables:
# V2-01 validation (2 files expected)
test -f src/contextcore/models/manifest_v2.py && \
test -f src/contextcore/models/__init__.py && \
grep -q "ContextManifestV2" src/contextcore/models/__init__.py && \
echo "✓ V2-01: Both files exist and export added"

# V2-03 validation (2 files expected)
test -f src/contextcore/models/manifest_loader.py && \
grep -q "load_manifest" src/contextcore/models/manifest.py && \
echo "✓ V2-03: Loader exists and re-exported"
```

**Rationale**:
- **Business**: Prevents incomplete features from being marked "complete"
- **Technical**: Catches partial generation early (Leg 11 #4 pattern)

**Action**: Enhance Step 4 (deliverable validation) with explicit multi-file checks for V2-01, V2-03, V2-04.

---

## Enhancement 3: Incremental Verification Ladder *(Leg 7 #2)*

**Problem**: Running all checks at once masks which validation stage failed.

**Current State**: Plan mentions "syntax → imports → tests" but doesn't structure as a progressive ladder.

**Solution**: Structure checkpoints as a progressive ladder:

```bash
# Stage 1: Syntax (fastest, catches obvious errors)
python3 -m py_compile src/contextcore/models/manifest_v2.py

# Stage 2: Imports (catches missing dependencies)
python3 -c "from contextcore.models.manifest_v2 import ContextManifestV2"

# Stage 3: Test Collection (catches import errors in tests)
python3 -m pytest --collect-only tests/test_manifest_v2.py

# Stage 4: Test Execution (catches logic errors)
python3 -m pytest -q -o addopts='' -p no:cov -p no:cacheprovider tests/test_manifest_v2.py
```

**Rationale**:
- **Business**: Faster feedback (fail fast at syntax stage)
- **Technical**: Clearer error diagnosis (know which stage failed)

**Action**: Update "Checkpoint Expectations" section to show ladder progression with stage-by-stage validation.

---

## Enhancement 4: Reference-Based Schema Validation *(Leg 11 #7)*

**Problem**: v2 schema may deviate from v1.1 patterns without explicit comparison.

**Current State**: Plan mentions "keep apiVersion/kind/metadata alignment" but doesn't validate against v1.1 reference.

**Solution**: Compare v2 models against v1.1 reference:

```python
# After V2-01 completes, validate structural alignment:
# 1. v2 has same top-level fields as v1.1 (apiVersion, kind, metadata, spec)
# 2. v2 reuses v1.1 enum patterns (TacticStatus, RiskType, etc.)
# 3. v2 follows v1.1 naming conventions (snake_case, populate_by_name)

# Validation script:
python3 -c "
from contextcore.models.manifest import ContextManifest
from contextcore.models.manifest_v2 import ContextManifestV2

# Check v2 has expected sections
assert hasattr(ContextManifestV2, 'strategy')
assert hasattr(ContextManifestV2, 'guidance')
assert hasattr(ContextManifestV2, 'spec')
assert hasattr(ContextManifestV2, 'insights')
print('✓ v2 structure aligns with plan')
"
```

**Rationale**:
- **Business**: Ensures v2 maintains consistency with v1.1 (easier migration)
- **Technical**: Prevents schema drift (Leg 11 #7 pattern)

**Action**: Add reference validation step after V2-01 and V2-02 completion.

---

## Enhancement 5: Cost Estimation & Budget Tracking *(Leg 11 #1)*

**Problem**: No visibility into API costs before execution.

**Current State**: Plan doesn't include cost estimates.

**Solution**: Add cost estimates per feature:

| Feature | Estimated Cost | Rationale |
|---------|---------------|-----------|
| V2-01 | $0.20-0.25 | Single model file, ~100 lines |
| V2-02 | $0.20-0.25 | Extends V2-01, ~80 lines |
| V2-03 | $0.20-0.25 | Loader logic, ~60 lines |
| V2-04 | $0.25-0.30 | CLI commands, ~120 lines |
| V2-05 | $0.25-0.30 | Migration transform, ~100 lines |
| **Total** | **$1.10-1.35** | Within budget for v2.0 |

**Rationale**:
- **Business**: Budget visibility before execution (Leg 11 #1 pattern)
- **Technical**: Helps prioritize features if budget is constrained

**Action**: Add cost tracking section before Step 3, with `python3 scripts/prime_contractor/cli.py estimate-cost` command.

---

## Enhancement 6: Test Isolation Verification *(Leg 9 #2, #3)*

**Problem**: Tests may interfere with each other if fixtures aren't properly isolated.

**Current State**: Plan doesn't verify test isolation.

**Solution**: Verify test isolation:

```bash
# After V2-05 (migration tests), verify:
# 1. Tests use tmp_path fixture (no repo writes)
# 2. Tests don't modify examples/context_manifest_example.yaml
# 3. Tests can run in any order

python3 -m pytest -q --random-order tests/test_manifest_v2.py
```

**Rationale**:
- **Business**: Prevents test flakiness (tests pass/fail based on order)
- **Technical**: Ensures tests are properly isolated (Leg 9 #2, #3 patterns)

**Action**: Add test isolation check to checkpoint expectations, especially for V2-05.

---

## Enhancement 7: Semantic Validation Details *(Leg 11 #5)*

**Problem**: "Semantic validation" is mentioned but HOW to validate isn't specified.

**Current State**: V2-02 mentions "semantic validation" but doesn't show validation code.

**Solution**: Explicit validation steps for V2-02:

```python
# V2-02 semantic validation checklist:
# ✓ ConstraintSeverity imports from contextcore.contracts.types
# ✓ QuestionStatus imports from contextcore.contracts.types  
# ✓ Focus.areas is List[str], not str
# ✓ Constraint.id and Constraint.rule are required (non-optional)
# ✓ All enums match canonical types exactly (no local duplicates)

# Validation script:
python3 -c "
from contextcore.models.manifest_v2 import AgentGuidanceSpec, Constraint, Focus
from contextcore.contracts.types import ConstraintSeverity, QuestionStatus

# Verify enum reuse
assert Constraint.model_fields['severity'].annotation == ConstraintSeverity
assert Question.model_fields['status'].annotation == QuestionStatus
print('✓ Enums reuse canonical types')
"
```

**Rationale**:
- **Business**: Ensures v2 reuses existing types (maintainability)
- **Technical**: Prevents duplicate enum definitions (Leg 11 #5 pattern)

**Action**: Expand V2-02 "Semantic Checks" section with explicit validation code.

---

## Updated Execution Steps (Recommended)

### Step 2.5: Pre-Generation Validation (NEW)

Add before Step 3:

```bash
# 1. Size limits (truncation prevention)
python3 scripts/prime_contractor/cli.py validate --check-size

# 2. Cost estimate (budget awareness)
python3 scripts/prime_contractor/cli.py estimate-cost

# Expected output:
# Total estimated cost: $1.10-1.35
# Continue? (y/n)
```

### Step 3.5: Post-Feature Validation (ENHANCED)

Add after each feature completes:

```bash
# Feature V2-01 example:
FEATURE="V2-01"
TARGET="src/contextcore/models/manifest_v2.py"

# Ladder Stage 1: Syntax
python3 -m py_compile "$TARGET" && echo "✓ Syntax OK"

# Ladder Stage 2: Imports  
python3 -c "from contextcore.models.manifest_v2 import ContextManifestV2" && echo "✓ Imports OK"

# Ladder Stage 3: Test Collection
python3 -m pytest --collect-only tests/test_manifest_v2.py && echo "✓ Tests collect OK"

# Ladder Stage 4: Multi-file validation
test -f src/contextcore/models/manifest_v2.py && \
test -f src/contextcore/models/__init__.py && \
grep -q "ContextManifestV2" src/contextcore/models/__init__.py && \
echo "✓ All deliverables exist"

# Ladder Stage 5: Reference validation (if applicable)
# (See Enhancement 4 above)

# Ladder Stage 6: Test Execution
python3 -m pytest -q -o addopts='' -p no:cov -p no:cacheprovider tests/test_manifest_v2.py && \
echo "✓ All tests pass"
```

---

## Summary: Lessons Learned Integration Status

| Pattern | Source | Current Status | Enhancement |
|---------|--------|---------------|-------------|
| Deliverable Validation Gate | Leg 11 #9 | ✅ Present | Enhanced with multi-file checks |
| Truncation Prevention | Leg 11 #4 | ⚠️ Mentioned | Add explicit validation |
| Multi-file Output Validation | Leg 11 #4 | ⚠️ Partial | Add explicit checks |
| Incremental Verification Ladder | Leg 7 #2 | ⚠️ Implied | Structure as ladder |
| Reference-Based Validation | Leg 11 #7 | ❌ Missing | Add v1.1 comparison |
| Cost Estimation | Leg 11 #1 | ❌ Missing | Add cost table |
| Test Isolation | Leg 9 #2, #3 | ❌ Missing | Add isolation check |
| Semantic Validation Details | Leg 11 #5 | ⚠️ Vague | Add explicit code |
| Git Safety Pre-flight | Leg 11 #12 | ✅ Present | No change needed |
| State-Aware Reset | Leg 11 #10 | ✅ Present | No change needed |
| Dry-Run End-to-End | Leg 11 #11 | ✅ Present | No change needed |
| Registry Verification | Leg 11 #15 | ✅ Present | No change needed |

---

## Recommendation

**Status**: ✅ Plan is production-ready with enhancements

The plan is solid and already incorporates many best practices. The 7 enhancements above strengthen it further by:
1. Adding explicit validation gates (truncation, multi-file, semantic)
2. Structuring checkpoints as a progressive ladder
3. Adding cost visibility
4. Ensuring test isolation
5. Validating against v1.1 reference patterns

**Priority**: All enhancements are recommended, but highest priority are:
1. **Enhancement 1** (Truncation Prevention) - Prevents wasted API costs
2. **Enhancement 2** (Multi-file Validation) - Prevents incomplete features
3. **Enhancement 3** (Verification Ladder) - Improves error diagnosis

---

## Changelog

| Date | Version | Actor | Summary |
|------|---------|-------|---------|
| 2026-02-05 | 1.0.0 | agent:claude-code | Initial enhancement review |