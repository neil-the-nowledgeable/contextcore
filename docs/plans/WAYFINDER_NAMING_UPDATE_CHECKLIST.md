# Wayfinder Naming Update Checklist

**Created:** 2026-01-28
**Status:** Pending Review
**Reference:** [ADR-002: Naming Convention — Wayfinder and ContextCore](adr/002-naming-wayfinder.md)

---

## Naming Convention Summary

| Layer | Name | Use When... |
|-------|------|-------------|
| **Standard** | **ContextCore** | Referring to the metadata model, specification, semantic conventions |
| **Implementation** | **Wayfinder** | Referring to the suite of tools, the fleet, the reference implementation |

---

## Already Updated (2026-01-28)

The following HTML files have been updated to use "Wayfinder" for the implementation:

- [x] `docs/harbor-tour.html` - Title, header, footer updated
- [x] `docs/harbor-tour-platform-engineer.html` - Title, subtitle, footer updated
- [x] `docs/harbor-tour-ai-developer.html` - Title, subtitle, ecosystem section, footer updated
- [x] `docs/harbor-tour-team-lead.html` - Title, subtitle, comparison section, footer updated
- [x] `docs/getting-started-solopreneur.html` - Title, comparison section, CTA, footer updated

---

## Documents Requiring Updates

### Priority 1: High-Visibility User-Facing Documents

| File | Update Needed |
|------|---------------|
| `README.md` | Update ecosystem description, "ContextCore ecosystem" → "Wayfinder suite" |
| `CLAUDE.md` | Update "Expansion Pack Ecosystem" section header and descriptions |
| `docs/EXPANSION_PACKS.md` | Major update - this describes the Wayfinder fleet, not ContextCore |
| `docs/NAMING_CONVENTION.md` | Add Wayfinder context, clarify relationship |
| `docs/harbor-tour.md` | Markdown version needs same updates as HTML |
| `docs/harbor-tour-solopreneur.md` | Markdown version needs same updates as HTML |

### Priority 2: Configuration and Metadata Files

| File | Update Needed |
|------|---------------|
| `.contextcore.yaml` | Update `ecosystem:` section description; clarify packages are Wayfinder components |
| `DASHBOARD_CONSOLIDATION_INDEX.yaml` | Review for naming consistency |

### Priority 3: Technical Documentation

| File | Update Needed |
|------|---------------|
| `docs/OPERATIONAL_RUNBOOK.md` | Review "ContextCore ecosystem" references |
| `docs/OTEL_GENAI_MIGRATION_GUIDE.md` | Review for implementation vs standard distinction |
| `docs/OTEL_GENAI_GAP_ANALYSIS.md` | Review for implementation vs standard distinction |
| `docs/skill-semantic-conventions.md` | Review ecosystem references |
| `docs/ROADMAP_AFTER_MERGE_ANALYSIS.md` | Review for naming consistency |

### Priority 4: Internal/Development Documents

| File | Update Needed |
|------|---------------|
| `contextcore-owl/CLAUDE.md` | Review ecosystem references |
| `contextcore-owl/README.md` | Review for naming consistency |
| `plans/dashboard-persistence-phase-1-3.md` | Review for naming consistency |

### Priority 5: Inbox/Working Documents

| File | Update Needed |
|------|---------------|
| `inbox/CAPABILITY_INDEX_PREPARATION.md` | Review ecosystem references |
| `inbox/CAPABILITY_INDEX_RESUME_GUIDE.md` | Review for naming consistency |
| `inbox/OTEL_ALIGNED_MATURITY_MODEL.md` | Review for naming consistency |
| `inbox/CAPABILITY_INDEX_PREPARATION_FEEDBACK.md` | Review for naming consistency |

### Priority 6: OTel Submission Documents

These should be reviewed carefully - may need to distinguish between:
- ContextCore (the standard being proposed to OTel)
- Wayfinder (the reference implementation demonstrating the standard)

| File | Update Needed |
|------|---------------|
| `docs/otel-submission/01-community-issue-blueprint-category.md` | Review for standard vs implementation distinction |
| `docs/otel-submission/02-community-issue-agent-blueprint.md` | Review for standard vs implementation distinction |
| `docs/otel-submission/03-semconv-issue-project-namespace.md` | Review for standard vs implementation distinction |
| `docs/otel-submission/04-semconv-issue-agent-namespace.md` | Review for standard vs implementation distinction |
| `docs/otel-submission/README.md` | Review for standard vs implementation distinction |
| `docs/otel-semconv-wg-proposal.md` | Review for standard vs implementation distinction |

### Priority 7: Blueprint Documents

| File | Update Needed |
|------|---------------|
| `docs/blueprint-reference-architecture.md` | Review for naming consistency |
| `docs/blueprint-reusable-patterns.md` | Review for naming consistency |
| `docs/blueprint-implementation-guide.md` | Review for naming consistency |
| `docs/blueprint-integration-existing.md` | Review for naming consistency |
| `docs/blueprint-new-categories.md` | Review for naming consistency |
| `docs/blueprint-validation-framework.md` | Review for naming consistency |

---

## Documents That Should NOT Be Updated

These documents correctly use "ContextCore" because they refer to the standard/specification:

| File | Reason |
|------|--------|
| `docs/semantic-conventions.md` | Defines the ContextCore semantic conventions (the standard) |
| `docs/agent-semantic-conventions.md` | Defines agent conventions (part of the standard) |
| `docs/agent-communication-protocol.md` | Defines the protocol (part of the standard) |
| `docs/adr/001-tasks-as-spans.md` | Core design decision for the standard |
| `docs/adr/002-naming-wayfinder.md` | Already correctly distinguishes the terms |
| `docs/TERMINOLOGY.md` | Already correctly defines both terms |
| `terminology/**/*.yaml` | Terminology definitions are correct |
| `crds/**` | CRD is `contextcore.io/v1` - this is the standard |
| Package names (`contextcore-*`) | Keep package names - they implement the ContextCore standard |

---

## Guidance for Updates

### When updating, change:

```
"ContextCore ecosystem" → "Wayfinder suite" or "Wayfinder ecosystem"
"ContextCore fleet" → "Wayfinder fleet"
"ContextCore Harbor Tour" → "Wayfinder Harbor Tour"
"The ContextCore suite of tools" → "The Wayfinder suite"
"ContextCore expansion packs" → "Wayfinder expansion packs" (or keep as-is if referring to packages)
```

### When NOT to change:

```
"ContextCore standard" → Keep as-is
"ContextCore semantic conventions" → Keep as-is
"ContextCore CRD" → Keep as-is (ProjectContext CRD)
"contextcore" (package name) → Keep as-is
"contextcore-rabbit" etc. → Keep as-is (packages implement the standard)
"ContextCore metadata model" → Keep as-is
```

### Example transformations:

**Before:**
> "The ContextCore ecosystem uses Anishinaabe animal names..."

**After:**
> "The Wayfinder suite uses Anishinaabe animal names..."

**Before:**
> "Install ContextCore and its expansion packs..."

**After:**
> "Install the Wayfinder suite..." OR "Install contextcore and its expansion packs..."
> (Package names stay lowercase `contextcore`)

---

## Notes

- The package names (`contextcore`, `contextcore-rabbit`, etc.) remain unchanged because they are implementations of the ContextCore standard
- The `contextcore` CLI command remains unchanged
- The `contextcore.io` API group for CRDs remains unchanged
- "ContextCore" as the name of the standard/specification remains unchanged
- Only the high-level suite/implementation name changes to "Wayfinder"

---

## Estimated Effort

| Priority | Files | Est. Time |
|----------|-------|-----------|
| P1 | 6 files | 2-3 hours |
| P2 | 2 files | 30 min |
| P3 | 5 files | 1 hour |
| P4 | 2 files | 30 min |
| P5 | 4 files | 1 hour |
| P6 | 6 files | 2 hours (requires careful review) |
| P7 | 6 files | 1-2 hours |
| **Total** | **31 files** | **8-10 hours** |
