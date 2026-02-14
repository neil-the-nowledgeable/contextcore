# Code Generation Patterns & Anti-Patterns

This document codifies patterns and anti-patterns for AI-assisted code generation workflows, based on lessons learned from the ContextCore project.

## The Core Problem

When AI agents generate code for multiple features without integration checkpoints, **technical debt compounds silently**. Each feature is developed in isolation, unaware of changes from other features. When integration finally happens, conflicts emerge that require careful manual resolution.

This is analogous to long-lived feature branches in traditional development—the longer they stay unmerged, the harder the eventual merge.

## Pattern: Continuous Integration (Prime Contractor)

### ✅ DO: Integrate After Each Feature

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Feature  │───▶│ Generate │───▶│ Integrate│───▶│ Validate │───▶ NEXT
│    1     │    │   Code   │    │   Now    │    │ Checkpoint│
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

**Benefits:**
- Each feature builds on the integrated codebase
- Conflicts detected immediately when they're small
- Mainline always in working state
- Clear audit trail of changes

**Implementation:**
```bash
# Use Prime Contractor workflow
python3 scripts/prime_contractor/cli.py run --import-backlog
```

### Why It Works

1. **Context Preservation**: Feature 2 is generated with knowledge of Feature 1's integrated code
2. **Small Conflicts**: If conflicts occur, they involve only 2 features, not N features
3. **Fast Feedback**: Problems surface immediately, not after hours of generation
4. **Reversibility**: Easy to revert a single feature vs. untangling N features

---

## Anti-Pattern: Batch Generation (Backlog Accumulation)

### ❌ DON'T: Generate All, Integrate Later

```
┌──────────┐    ┌──────────┐
│ Feature  │───▶│ Generate │───▶ Backlog
│    1     │    │   Code   │         │
└──────────┘    └──────────┘         │
                                     │
┌──────────┐    ┌──────────┐         │
│ Feature  │───▶│ Generate │───▶ Backlog  (no knowledge of Feature 1)
│    2     │    │   Code   │         │
└──────────┘    └──────────┘         │
                                     │
┌──────────┐    ┌──────────┐         │
│ Feature  │───▶│ Generate │───▶ Backlog  (no knowledge of Features 1, 2)
│    3     │    │   Code   │         │
└──────────┘    └──────────┘         │
                                     ▼
                              ┌──────────────┐
                              │  INTEGRATE   │
                              │  ALL AT ONCE │
                              └──────────────┘
                                     │
                                     ▼
                              🔥 CONFLICTS 🔥
                              Manual merge required
```

**Problems:**
- Features developed without awareness of each other
- Conflicts multiply combinatorially (N features = N² potential conflicts)
- Manual merge required for overlapping changes
- Risk of regressions when resolving conflicts
- Lost context about why changes were made

**Real Example from ContextCore:**

```
4 features targeting src/contextcore/compat/otel_genai.py:
  - OTel_ConversationId
  - OTel_ToolMapping  
  - Foundation_GapAnalysis
  - Foundation_DualEmit

Result: HIGH RISK conflict (60/100)
  - Would remove classes: InsightQuerier, InsightRecord, InsightsAPI
  - Would remove functions: transform, query, emit
  - Required careful manual merge
```

---

## Pattern: Checkpoint Validation

### ✅ DO: Validate Before Proceeding

```python
# After each feature integration
checkpoints = [
    "syntax_check",      # Code compiles
    "import_check",      # Imports resolve
    "lint_check",        # No critical lint errors
    "test_check",        # No test regressions
]

for checkpoint in checkpoints:
    if not checkpoint.passes():
        STOP()  # Fix before continuing
        
proceed_to_next_feature()
```

**Benefits:**
- Catch problems when they're fresh
- Clear signal of what broke
- Prevents cascade of failures
- Maintains code quality baseline

### ❌ DON'T: Skip Validation

```python
# Generate all features first, validate later
for feature in features:
    generate(feature)  # No validation

# Now try to validate everything
validate_all()  # Which feature broke it? 🤷
```

**Problems:**
- Unclear which feature introduced the problem
- Debugging requires bisecting through features
- May need to regenerate multiple features
- Lost time and context

---

## Pattern: Conflict-Aware Generation

### ✅ DO: Detect Conflicts Before They Happen

```python
# Before generating Feature N
potential_conflicts = detect_overlapping_targets(
    feature_n.target_files,
    already_integrated_files
)

if potential_conflicts:
    warn("Feature N targets files modified by previous features")
    strategy = determine_merge_strategy(potential_conflicts)
    # merge, choose, or manual review
```

**Benefits:**
- Proactive conflict detection
- Informed decisions about merge strategy
- No surprises during integration

### ❌ DON'T: Discover Conflicts During Integration

```python
# Just try to integrate and see what happens
try:
    integrate(feature)
except ConflictError:
    # Now what? Manual intervention required
    panic()
```

---

## Pattern: Atomic Feature Commits

### ✅ DO: Commit Each Feature Separately

```bash
# Feature 1
git commit -m "feat: Add authentication service"

# Feature 2  
git commit -m "feat: Add user API endpoints"

# Feature 3
git commit -m "feat: Add rate limiting"
```

**Benefits:**
- Clear history of what changed
- Easy to revert specific features
- Bisectable for debugging
- Code review per feature

### ❌ DON'T: One Big Commit

```bash
# After integrating 10 features
git commit -m "Integrate backlog"  # What changed? Everything.
```

**Problems:**
- Impossible to revert one feature
- Can't bisect to find bugs
- Code review is overwhelming
- Lost feature-level context

---

## Pattern: Dependency-Ordered Processing

### ✅ DO: Process Features in Dependency Order

```python
# Define dependencies
features = [
    Feature("auth", dependencies=[]),
    Feature("user_api", dependencies=["auth"]),
    Feature("admin_api", dependencies=["auth", "user_api"]),
]

# Process in order
for feature in topological_sort(features):
    if all_dependencies_complete(feature):
        integrate(feature)
```

**Benefits:**
- Dependencies available when needed
- Logical build order
- Clear failure points

### ❌ DON'T: Random Order Processing

```python
# Process in whatever order they were generated
for feature in features:  # Random order
    integrate(feature)  # May fail due to missing dependencies
```

---

## Decision Framework

Use this flowchart to decide which pattern to use:

```
                    ┌─────────────────────────┐
                    │ How many features are   │
                    │ being generated?        │
                    └───────────┬─────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
              ┌─────────┐            ┌─────────────┐
              │ 1 only  │            │ 2 or more   │
              └────┬────┘            └──────┬──────┘
                   │                        │
                   ▼                        ▼
         ┌─────────────────┐    ┌─────────────────────────┐
         │ Lead Contractor │    │ Do features target the  │
         │ is sufficient   │    │ same files?             │
         └─────────────────┘    └───────────┬─────────────┘
                                            │
                                ┌───────────┴───────────┐
                                │                       │
                                ▼                       ▼
                          ┌─────────┐            ┌─────────┐
                          │   No    │            │   Yes   │
                          └────┬────┘            └────┬────┘
                               │                      │
                               ▼                      ▼
                    ┌─────────────────┐    ┌─────────────────────┐
                    │ Lead Contractor │    │ MUST use Prime      │
                    │ may be okay,    │    │ Contractor to       │
                    │ but Prime is    │    │ prevent conflicts   │
                    │ still safer     │    │                     │
                    └─────────────────┘    └─────────────────────┘
```

---

## Implementation Checklist

When setting up a code generation workflow:

### Before Generation

- [ ] Identify all features to be generated
- [ ] Map features to target files
- [ ] Detect potential conflicts (same file, multiple features)
- [ ] Determine processing order (dependencies)
- [ ] Choose workflow: Prime Contractor (recommended) or Lead Contractor

### During Generation

- [ ] Process one feature at a time
- [ ] Integrate immediately after generation
- [ ] Run checkpoints (syntax, imports, lint, tests)
- [ ] Stop on failure, fix before continuing
- [ ] Commit each feature separately

### After Generation

- [ ] Verify all checkpoints pass
- [ ] Review integration history
- [ ] Document any manual interventions
- [ ] Update patterns based on lessons learned

---

## Quick Reference

| Scenario | Pattern | Command |
|----------|---------|---------|
| Multiple features | Prime Contractor | `python3 scripts/prime_contractor/cli.py run --import-backlog` |
| Preview changes | Dry run | `python3 scripts/prime_contractor/cli.py run --dry-run` |
| Single feature | Lead Contractor | `python3 scripts/lead_contractor/integrate_backlog.py --feature X` |
| Check status | Status | `python3 scripts/prime_contractor/cli.py status` |
| Retry failed | Retry | `python3 scripts/prime_contractor/cli.py retry feature_id` |
| Reset failures | Reset | `python3 scripts/prime_contractor/cli.py reset` |

---

## Related Documentation

- [PRIME_CONTRACTOR_WORKFLOW.md](PRIME_CONTRACTOR_WORKFLOW.md) - Detailed Prime Contractor documentation
- [CONFLICT_RESOLUTION_GUIDE.md](../CONFLICT_RESOLUTION_GUIDE.md) - Manual conflict resolution
- [WORKFLOW_ADJUSTMENTS_AFTER_CONFLICT_RESOLUTION.md](../WORKFLOW_ADJUSTMENTS_AFTER_CONFLICT_RESOLUTION.md) - Lead Contractor improvements
