# Convergent Review Agent Guide: Weaver Registry & Cross-Repo Alignment

**Documents under review:**
- `docs/design/weaver/WEAVER_REGISTRY_REQUIREMENTS.md` (738 lines) — what goes into the registry
- `docs/design/weaver/WEAVER_CROSS_REPO_ALIGNMENT_PLAN.md` (731 lines) — how to build and align it

**Date:** 2026-02-28
**Author perspective:** Claude Opus 4.6 (primary author of both documents)

---

## Purpose of This Guide

I wrote both of these documents. This guide is my honest assessment of where they are weakest, what I'm least confident about, and where external input would have the highest return. It is organized by the kind of reviewer most likely to catch the issue, then by specific questions within each area.

The plan's Appendix C already has one round of external review (R2, from gemini-2.5-pro). Five of those seven suggestions were applied. This guide identifies the next layer of issues — the ones I can see but can't resolve from my position as the author.

---

## 1. Reviewer Profile: OTel Weaver Practitioner

**What they know that I don't:** Whether the V2 schema format actually works as documented.

### 1.1 The V2 format is specified from documentation, not from running Weaver

Every V2 decision in the requirements doc (Section 2.5) was derived from reading Weaver's changelog, GitHub issues, and README — not from running `weaver registry check` against actual YAML files. The specific concerns:

| Decision | My confidence | Risk |
|----------|--------------|------|
| `file_format: definition/2` as the format header | Medium | This may not be the actual syntax. Weaver's docs use it but I haven't seen a validated example registry using this exact string. |
| `imports:` section with `scope:` array | Low | The import mechanism was introduced in v0.15.3 but examples are scarce. The `scope:` syntax with glob patterns (`gen_ai.*`) may not work as I specified. |
| `schema_url` replacing `registry_url` | Medium | Documented in changelog but could still require the old field name in v0.21.2. |
| `manifest.yaml` replacing `registry_manifest.yaml` | Medium | Same concern — the rename may not yet be enforced. |

**What I want a reviewer to do:** Run the Phase 1 manifest.yaml example (Plan Section 1.1) through `weaver registry check` on an actual v0.21.2 install and report what breaks. Even a "this parses" or "this doesn't parse" is extremely valuable.

### 1.2 The attribute group YAML structure is assumed, not validated

Section 1.2 of the plan specifies that each attribute group file (task.yaml, project.yaml, etc.) uses V2 format. But I never provide a complete, syntactically valid example of what a single attribute group YAML looks like in V2. The plan jumps from "create these files" to listing attributes in a table, without showing the exact YAML structure that Weaver expects.

**Question for reviewer:** What does a minimal, valid V2 attribute group YAML look like? Does it need `attribute_group:` at the top level, or `groups:`, or something else? How are enum values declared — inline or as separate `members:` blocks?

### 1.3 Pipeline gates YAML has no Weaver precedent

Section 1.7 defines `semconv/pipeline-gates.yaml` using `file_format: definition/2`, but pipeline gates are not a Weaver concept — this is a ContextCore-specific schema that borrows the format header. This may confuse `weaver registry check` if it tries to parse it as an attribute group.

**Question for reviewer:** Should `pipeline-gates.yaml` live outside the `semconv/` directory to avoid Weaver trying to validate it? Or should it use a different format header?

---

## 2. Reviewer Profile: Consumer / Dashboard Builder

**What they know that I don't:** Whether the attributes and requirement levels make sense from the consuming side.

### 2.1 Requirement level assignments are producer-biased

I assigned `required`, `recommended`, and `opt_in` levels to 250+ attributes from the perspective of "what does the emitter naturally produce?" A consumer perspective would ask the opposite: "what do I need to be present to build a useful dashboard or query?"

Specific attributes where I'm uncertain about the level:

| Attribute | Current Level | My concern |
|-----------|--------------|------------|
| `task.title` | opt_in | Dashboard panels commonly display titles. Should this be `recommended`? |
| `task.percent_complete` | recommended | Burndown charts break without this. Should it be `required`? |
| `sprint.start_date`, `sprint.end_date` | recommended | Sprint burndown is impossible without these. Are they effectively required? |
| `task.parent_id` | recommended | Hierarchy views depend on this. opt_in would break the tree, but is recommended strong enough? |
| `budget.remaining` | recommended | Marked as "derived" but consumers may expect it. Should it be required if `allocated` and `consumed` are required? |

**What I want a reviewer to do:** Walk through Sections 4.1–4.20 of the requirements doc from the perspective of "I'm building a Grafana dashboard that needs to show X." Flag any attribute whose level is too low for its downstream importance.

### 2.2 The 5 new opt_in task attributes have no consumers yet

Plan Section 1.2 adds `task.prompt`, `task.feature_id`, `task.target_files`, `task.estimated_loc`, and `task.depends_on` as opt_in. These exist because the StartD8 emitter produces them, but no dashboard or query currently uses them. The rejected suggestion R2-S2 proposed adding consumer updates to Phase 5, which was rejected as scope creep.

**Question for reviewer:** Is the plan correct to defer consumer adoption of these attributes, or does publishing attributes with zero consumers create "dead schema" that nobody will validate?

### 2.3 Layer 1-7 attributes may be too internal

The 7 contract domain layers (propagation, schema_compat, semconv, boundary, capability, budget, lineage) define 28 attributes that are emitted by internal contract validators. These are useful for debugging contract failures but may not belong in external-facing dashboards.

**Question for reviewer:** Should Layer 1-7 attributes be marked `internal` in the registry (V2 supports `visibility: internal` on attribute groups)? Or are there legitimate consumer use cases for querying, say, `propagation.chain_status` in a Grafana dashboard?

---

## 3. Reviewer Profile: StartD8 SDK Maintainer

**What they know that I don't:** Whether the emitter alignment (Phase 3) captures the real-world integration surface.

### 3.1 Phase 3 is suspiciously simple

Phase 3 of the plan (Align StartD8 Emitter) is 3 files modified, rated "Low" complexity. This feels too light given that StartD8 is the primary cross-repo consumer. The phase assumes:

- No attribute renames are needed (because both `depends_on` and `blocked_by` are kept)
- The emitter already conforms to the registry
- The main work is adding tests

**Question for reviewer:** Is this accurate? Are there emitter attributes not listed in Plan Section 3.1's table? Does the emitter use any attribute names that differ from the registry's conventions (e.g., `task_id` vs `task.id`, different casing, extra prefixes)?

### 3.2 Edit-first enforcement is documented as "already implemented"

Plan Section 3.4 and Section 7.5 both claim edit-first enforcement is already implemented across both repos. But neither section links to the specific test files or code locations in StartD8 that prove this.

**Question for reviewer:** Can you verify that the `ImplementPhaseHandler` Gate 5 check and the `edit_first.size_regression` span event are actually present in the current StartD8 codebase? If they are, linking the file paths would strengthen the plan. If they aren't, Section 7.5's "no new work required" claim is wrong.

### 3.3 Round-trip test assumes ContextCore's SpanState can be imported

Plan Section 3.2 proposes a `TestSpanStateRoundTrip` that calls `ContextCore.state.SpanState.from_dict()`. This creates a cross-repo import dependency in tests. If StartD8's CI doesn't install ContextCore as a dependency, this test can't run.

**Question for reviewer:** Does StartD8's test suite currently import from ContextCore? If not, should the round-trip test use a mocked SpanState schema instead of the real import? This affects whether Phase 3 depends on Phase 6 (cross-repo CI) or not.

---

## 4. Reviewer Profile: Schema Evolution / Versioning Expert

**What they know that I don't:** Whether the deprecation and versioning strategy will actually work over multiple releases.

### 4.1 The deprecation policy has no enforcement mechanism

Plan Section 1.6 defines a deprecation policy: "deprecated attributes supported for 2 minor versions, removed in next major version." But nothing in the CI pipeline or Weaver configuration actually enforces this. A developer could leave deprecated attributes in the registry for 10 minor versions and nothing would flag it.

**Question for reviewer:** Should the plan include a Phase 3 deliverable that checks deprecated-since versions against the current registry version and warns (or fails) when the grace period expires?

### 4.2 Version 0.1.0 creates ambiguity about what "breaking change" means

The registry starts at v0.1.0 (per applied R2-S5), which under semver means any change can be breaking. But the plan simultaneously defines a deprecation policy that references "minor versions" and "major versions." If the registry is at 0.x, there is no distinction between minor and major — every 0.x bump is semantically equivalent.

**Question for reviewer:** Should the deprecation policy be phrased differently for the 0.x era? For example: "During 0.x, deprecated attributes will be supported for at least 2 registry releases (0.1.0 → 0.2.0 → removable in 0.3.0)" instead of referencing semver minor/major distinctions that don't exist yet.

### 4.3 The OTel semconv pin (v1.34.0) will become stale

The manifest imports OTel semconv v1.34.0. OTel semconv ships new versions regularly. The plan has no mechanism for bumping this dependency, no CI check for upstream compatibility, and no policy for when to upgrade.

**Question for reviewer:** Should the plan include a lightweight "upstream dependency check" in Phase 6's CI, or is manual bumping acceptable for a 0.x registry? What would a reviewer recommend as the trigger for upgrading the OTel semconv pin?

---

## 5. Reviewer Profile: CI/CD Architect

**What they know that I don't:** Whether the cross-repo validation design is practical.

### 5.1 Option A vs Option B is the most important unresolved design decision

Phase 6.2 proposes two approaches for cross-repo schema validation:

- **Option A:** Hardcode the attribute allowlist in StartD8's test files. Update manually when the registry changes.
- **Option B:** StartD8's CI fetches the allowlist from ContextCore's registry YAML at build time.

The plan recommends Option A. Reviewer R2-S1 argued for mandating Option B. The suggestion was rejected because "Option B before cross-repo CI infrastructure exists adds complexity." But R2-S1 was also endorsed by the same reviewer as "the most critical missing piece."

**This tension is unresolved.** The plan punts on it by choosing the simpler option, but the rejected suggestion has merit — Option A re-introduces manual synchronization in a project whose entire purpose is eliminating manual synchronization.

**What I want a reviewer to do:** Propose a concrete Option C — a middle ground that is more automated than Option A but simpler than Option B. For example: a GitHub Action in ContextCore that, on registry changes, opens a PR in StartD8 with the updated allowlist. This would be automated distribution without requiring StartD8 to fetch from ContextCore at build time.

### 5.2 The enum consistency script has no specification

Phase 6.3 proposes `scripts/validate_enum_consistency.py` that cross-checks all 27 enums between `types.py` and registry YAML. The plan describes what it should do but never specifies:

- How it discovers enums in the YAML (parse `members:` blocks? regex?)
- How it matches YAML enum names to Python enum class names (naming convention? explicit mapping file?)
- What its exit code behavior is (0 = all match, 1 = any mismatch, 2 = parse error?)
- Whether it handles cross-cutting enums differently from layer-specific enums

**Question for reviewer:** Should this script specification be added to the plan, or is it an implementation detail that can be figured out during Phase 6?

---

## 6. Reviewer Profile: Project Scope / Effort Estimator

**What they know that I don't:** Whether the 49-file estimate is realistic and whether the phases are correctly sized.

### 6.1 Phase 2 tripled in scope but kept the same phase number

Phase 2 went from "2 files modified" to "23 files new/modified" when Layer 1-7 attribute groups were added. This is no longer a consolidation phase — it's the largest phase in the plan, rated "Medium-High" complexity. It might benefit from being split:

- Phase 2a: Consolidate ATTRIBUTE_MAPPINGS (original scope, 2-3 files)
- Phase 2b: Layer 1-7 attribute groups (7 new YAMLs, mechanical)
- Phase 2c: Remaining attribute groups (8 additional YAMLs)
- Phase 2d: Spans, events, and metrics (6 new YAMLs)

**Question for reviewer:** Is splitting Phase 2 worth the planning overhead, or is the work mechanical enough that a single phase with clear subsections (2.1-2.6) is sufficient?

### 6.2 The 86/12/6 split across repos may undercount Wayfinder work

The plan allocates 86% of files to ContextCore, 12% to StartD8, and 6% to Wayfinder. Phase 5 (Wayfinder) is rated "Low" complexity with 2 files modified. But this assumes Wayfinder's only obligation is to point to ContextCore's registry and keep its own `skill.*` conventions.

If Wayfinder has runtime consumers that emit or query `task.*` attributes (dashboards, scripts, loaders), those consumers need to be audited even if they aren't modified. The plan deliberately excludes this (R2-S2 rejected), but the audit itself — discovering what exists — might reveal that Phase 5 is underscoped.

**Question for reviewer:** Should Phase 5 include a read-only audit step ("list all Wayfinder files that reference task.*, project.*, sprint.*, or agent.* attributes") before concluding that 2 files is sufficient?

### 6.3 No phase accounts for learning Weaver YAML syntax

Phase 1 notes "Weaver YAML syntax learning curve" but doesn't account for it in effort estimates. The plan assumes YAML files are mechanical translations from Python. But if the V2 format has surprises (see Section 1 of this guide), Phase 1 could take significantly longer as the author iterates on getting `weaver registry check` to pass.

**Question for reviewer:** Should Phase 1 include an explicit "spike" deliverable — e.g., "create a single minimal attribute group YAML, validate it against Weaver v0.21.2, document the working syntax" — before committing to generating all 4 attribute group files?

---

## 7. Reviewer Profile: Adversarial / Devil's Advocate

**What they know that I don't:** What failure modes I'm blind to because I wrote both documents.

### 7.1 Both documents assume Python remains canonical — but the plan creates a YAML registry

The requirements doc (Section 13, Non-Goals) states: "Python remains canonical; YAML mirrors it." The plan implements this by generating YAML from Python. But once the registry exists and CI validates it, there will be pressure to make the YAML canonical — especially if `weaver registry mcp` is adopted for agent discovery.

**Question for reviewer:** Is the plan setting up a future conflict where two sources of truth (Python enums + YAML registry) drift despite CI checks? Should the plan take a position on which source of truth wins when they disagree, beyond "Python is canonical"?

### 7.2 The risk register is comprehensive but misses organizational risks

The plan's 12 risks are all technical. Missing:

- **Bandwidth risk:** The plan requires work in 3 repos. If the person doing the work can only access one repo at a time, Phases 3 and 5 could stall.
- **Coordination risk:** Phase 6 (cross-repo CI) requires agreement from StartD8 maintainers to add a CI step. What if they have different priorities?
- **Abandonment risk:** The plan's 0.1.0 versioning signals instability. What happens if the registry is created but never reaches 1.0 because priorities shift?

**Question for reviewer:** Are these organizational risks worth adding to the register, or are they out of scope for a technical plan?

### 7.3 No acceptance criteria for the plan as a whole

Individual phases have acceptance criteria ("weaver registry check passes"), but there is no definition of when the entire plan is "done." Is it done when all 7 phases complete? When all 11 REQs are satisfied? When the old `semantic-conventions.md` is deleted?

**Question for reviewer:** Should the plan include a top-level "Definition of Done" section?

### 7.4 The Appendix C review system may not converge

The plan's iterative review log (Appendix C) is append-only with endorsement counting. But there's no threshold for auto-applying endorsed suggestions, no deadline for triage, and no mechanism for resolving conflicting suggestions. The "Areas Needing Further Review" section tracks coverage thresholds but doesn't define what happens when they're reached.

**Question for reviewer:** Is the review system itself well-designed, or does it need a governance layer (e.g., "suggestions with 3+ endorsements are auto-triaged within 1 week")?

---

## Summary: Highest-ROI Review Actions

Ranked by how much they would reduce risk if answered well:

| Priority | Section | Action | Reviewer type |
|----------|---------|--------|---------------|
| 1 | 1.1 | Validate V2 format against running Weaver v0.21.2 | Weaver practitioner |
| 2 | 5.1 | Propose concrete Option C for cross-repo schema distribution | CI/CD architect |
| 3 | 2.1 | Audit requirement level assignments from consumer perspective | Dashboard builder |
| 4 | 3.1 | Verify Phase 3 completeness against actual StartD8 emitter | StartD8 maintainer |
| 5 | 4.2 | Clarify deprecation semantics during 0.x era | Schema evolution expert |
| 6 | 7.1 | Address the "two sources of truth" tension | Adversarial reviewer |
| 7 | 6.3 | Evaluate whether Phase 1 needs a Weaver syntax spike | Effort estimator |
| 8 | 2.3 | Decide whether Layer 1-7 attributes should be `internal` visibility | Consumer + Weaver practitioner |

---

## How to Submit Review Feedback

Feedback should be submitted as suggestions to the plan's **Appendix C** (Incoming Suggestions), using the established format:

```
Review Round: R{next_round}
Reviewer: {name} ({model_id or human})
Date: {ISO 8601}
Scope: {which sections reviewed}
```

Each suggestion needs: ID, Area, Severity, Suggestion, Rationale, Proposed Placement, Validation Approach.

Reviewers should read Appendix A (applied) and Appendix B (rejected with rationale) before submitting to avoid re-proposing settled items. Endorsing prior untriaged suggestions is encouraged and builds consensus signal.
