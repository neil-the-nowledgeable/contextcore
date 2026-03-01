# Convergent Review Prompt

Use this prompt to generate a **Convergent Review Agent Guide** for any project plan, requirements document, or design document. The output is a review solicitation guide — an honest self-assessment of where a document is weakest and where external input would have the highest return.

---

## When to Use This

- Before sending a plan or design doc for external review
- When you've finished a requirements document and want to maximize the quality of feedback you receive
- When a plan is technically complete but you suspect blind spots
- When preparing inputs for LLM-assisted code generation and want to identify where greater specificity in the plan would substantially improve generated output quality
- When an effort unlocks value that the plan doesn't leverage — the low-hanging fruit visible only in hindsight

---

## The Prompt

Copy and adapt the following. Replace the bracketed sections with your specifics.

```
You have deep familiarity with the following document(s), either as the
primary author or as an agent that has thoroughly read and understood them:

[PASTE OR REFERENCE YOUR DOCUMENT(S) HERE]

Your task is to write a Convergent Review Agent Guide — a structured
assessment that identifies where this document is weakest and where
external input would have the highest return on investment.

Write from the perspective of someone who understands the document's
intent and can see its blind spots. If you wrote the document, be candid
about your uncertainties. If you are reviewing someone else's work,
note where the author's assumptions seem untested or where you lack
the context to judge a claim.

Use the reference guide at docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md
as a structural template. Your output should follow the same pattern but be
entirely specific to the document(s) above.

## What the guide must contain

### 1. Reviewer Profiles (3-8 profiles)

Identify the types of people or agents whose expertise would most improve
the document. For each profile:

- Name the profile by what they know (e.g., "Database Migration Expert",
  "End User / Customer", "Performance Engineer")
- State explicitly what they know that you, the author, do not
- List 2-4 specific, numbered questions or review actions under each profile
- For each question, explain why YOU cannot answer it from your position
  as the author

Prioritize profiles that address these categories (in order of importance):

**A. Validation gaps** — Claims or assumptions in the document that have
not been tested against reality. Examples:
  - Decisions made from reading documentation rather than running the
    actual tool
  - Performance claims based on estimates rather than benchmarks
  - Compatibility claims that assume behavior of an external system
    without verifying it
  - "This API supports X" where X was read from a changelog, not tested

**B. Consumer-side blind spots** — Places where the document specifies
what is produced but not whether consumers can actually use it. Examples:
  - Requirement levels assigned from the producer's perspective without
    checking what consumers actually need to function
  - API designs that feel elegant to the author but require awkward
    workarounds for callers
  - Configuration defaults chosen for the author's use case that will
    be wrong for most users
  - Error messages written for the implementer that are meaningless
    to the operator

**C. Unleveraged value** — Capabilities, data, or infrastructure that the
plan creates as a side effect but never exploits. These are the low-hanging
fruit visible in hindsight: the effort builds something, but the plan
stops short of connecting it to the user benefit it enables. Examples:
  - A registry that enables agent discovery, but the plan never adds
    a discovery endpoint
  - A validation script that could generate a compliance report, but
    the plan only uses it as a CI gate
  - Test data that could seed a demo environment, but the plan treats
    it as disposable
  - Metadata that could drive documentation generation, but the plan
    only uses it for validation

For each piece of unleveraged value, describe:
  - What the effort creates as a byproduct
  - What user-facing benefit it could deliver with modest additional work
  - Why the plan doesn't currently capture this (scope control, oversight,
    deferred intentionally, or genuinely not noticed)

**D. Specificity that would improve LLM generation quality** — Places
where the document will be used as input to an LLM for code generation,
content creation, or decision-making, and where greater precision in the
input would substantially improve the output. Examples:
  - A requirements section that says "add validation" without specifying
    what valid and invalid look like — an LLM will guess, and guess wrong
  - A plan that says "create YAML files" without showing the exact
    schema — an LLM will invent a schema that doesn't match the tool's
    expectations
  - An architecture description that names components but doesn't specify
    their interfaces — an LLM will generate plausible but incompatible APIs
  - Enum values listed without behavioral descriptions — an LLM won't
    know when to use "degraded" vs "broken" vs "failed"

For each specificity gap, describe:
  - What the LLM will likely get wrong without the missing information
  - What concrete artifact (example, schema, test case, decision record)
    would close the gap
  - The estimated quality improvement (e.g., "eliminates a class of
    generation errors" vs "marginal improvement")

**E. Effort and sequencing risks** — Phases that are underscoped,
dependencies that are unstated, or work that would benefit from being
reordered. Include organizational risks, not just technical ones. Examples:
  - A phase that tripled in scope but kept its original effort estimate
  - Work that requires access to a system the team doesn't control
  - A dependency on another team's deliverable with no fallback plan
  - Learning curve for a new tool that the plan treats as zero-cost
  - A plan that will be abandoned if the first phase takes too long,
    but the first phase has no quick-win checkpoint to sustain momentum

**F. Unresolved design tensions** — Decisions where the document chose
one option but the alternative has legitimate merit. These are the most
valuable items for external review because the author has already
considered both sides and cannot resolve the tension alone. Examples:
  - Choosing a simpler approach now vs investing in a robust approach
    that prevents rework later
  - Keeping two sources of truth "temporarily" vs forcing consolidation
    upfront
  - Scoping a plan tightly (risk of missing value) vs expanding scope
    (risk of never finishing)
  - Building for the current use case vs abstracting for future ones

### 2. Priority Table

End with a summary table ranking all review actions by ROI:

| Priority | Section | Action | Reviewer type |
|----------|---------|--------|---------------|

Rank by: How much would the document improve if this question were
answered well? Consider both probability of the current approach being
wrong AND the cost of being wrong.

### 3. Self-Apply Step

Before finalizing the guide, check: did the review process itself
surface any issues that you can fix right now without external input?
List up to 3 obvious improvements to the source document that the
analysis revealed. These are "free fixes" — issues that became visible
through the structured self-assessment but didn't require an external
reviewer. Describe each fix and whether you recommend applying it
immediately or deferring it to the review cycle.

The purpose of this step is to capture value from the review process
itself, not just from the reviewers it attracts.

### 4. Submission Instructions

Include instructions for how reviewers should submit feedback, adapted
to the document's existing review mechanism (if any). If the document
has an appendix-based review log, reference it. If not, specify a
lightweight format.

## Quality Criteria

The guide is good if:
- The author admits specific things they don't know ("I specified this
  format from docs, not from running the tool")
- Questions are answerable by a specific type of person ("run this YAML
  through weaver v0.21.2 and tell me what breaks")
- Unleveraged value items include a concrete description of the user
  benefit and the modest additional work required
- The priority table forces hard choices about what matters most
- At least one category (A-F) is explicitly marked "not applicable to
  this document" — if all six apply equally, the analysis is too shallow

The guide is bad if:
- Questions are generic ("is this design good?") and could apply to
  any document
- Profiles are roles rather than expertise ("senior engineer" instead
  of "someone who has built a Weaver registry")
- Every section is marked high priority — the ranking must differentiate
- No specificity gaps are identified — this usually means the author
  hasn't considered what happens when the document is used as LLM input

## Constraints

- Be honest about what you don't know. The value of this guide is in
  its candor, not its completeness.
- Do not invent reviewer profiles for coverage. Only include profiles
  where you can articulate a specific question you cannot answer yourself.
- Do not repeat the document's content. Reference sections by number
  or name. The guide should be readable without having the source
  document open, but it should not duplicate it.
- Keep the guide under 400 lines. Longer guides won't be read.
- If the document has already received external review, acknowledge
  what was covered and focus on what remains.
- Not every category (A-F) will apply to every document. If a category
  genuinely doesn't apply, say so in one line and move on. A guide that
  forces all six categories onto a document that only has three real
  issues is worse than a focused guide that covers three deeply.
```

---

## Adapting for Different Document Types

### For a Requirements Document
Focus on: validation gaps (are the requirements testable?), consumer blind spots (do the requirement levels match downstream needs?), and specificity for generation (will an LLM implementing these requirements make correct choices?).

### For a Project Plan
Focus on: effort/sequencing risks (are phases correctly sized?), unleveraged value (what does the plan build that it doesn't exploit?), and unresolved design tensions (where did the plan choose the simpler path?).

### For a Design Document
Focus on: specificity for generation (are interfaces specified precisely enough for code generation?), validation gaps (has the design been tested against the actual tools/APIs?), and consumer blind spots (does the design serve producers and consumers equally?).

### For an Architecture Decision Record
Focus on: unresolved design tensions (is the rejected alternative truly inferior?), organizational risks (does the team have the skills and bandwidth for this choice?), and unleveraged value (does this decision enable future work that should be captured now?).

---

## Reference Implementation

See `CONVERGENT_REVIEW_AGENT_GUIDE.md` in this directory for a complete example applied to the ContextCore Weaver registry documents. It demonstrates all six categories (validation gaps, consumer blind spots, unleveraged value, specificity gaps, effort risks, design tensions) across 7 reviewer profiles with 8 prioritized review actions.

---

## Self-Review Log (Convergent Review Applied to This Document)

This prompt was subjected to its own convergent review process. The findings and dispositions are recorded below for transparency and as a demonstration of the self-apply pattern.

### Applied

| # | Finding | Category | Change Made |
|---|---------|----------|-------------|
| 1 | **Quality criteria were outside the prompt block.** An LLM executing the prompt would never see the "good vs bad" section because it sits after the closing triple-backtick. The criteria need to be inside the prompt to influence the output. | D (specificity) | Moved quality criteria inside the prompt as a "Quality Criteria" section. Removed the duplicate external section. |
| 2 | **Categories A, B, E, F had no examples; category C had four.** An LLM will produce output proportional to the guidance given per category. The asymmetry would cause rich "unleveraged value" sections and thin everything else. | D (specificity) | Added 3-4 concrete examples to each of categories A, B, E, and F, matching the detail level of category C. |
| 3 | **"You are the primary author" excluded the common case of reviewing someone else's work.** A human developer or agent frequently needs to generate a review guide for a document they didn't write. The original framing forced an awkward role-play. | B (consumer blind spot) | Changed to "you have deep familiarity with" and added guidance for both author and non-author perspectives. |
| 4 | **No self-apply step.** The review process itself surfaces obvious fixes, but the prompt had no mechanism to capture them. Value was being generated and discarded. | C (unleveraged value) | Added Section 3: "Self-Apply Step" — up to 3 free fixes that the analysis itself revealed, with recommendation to apply or defer. |
| 5 | **No guidance on skipping inapplicable categories.** The prescriptive 6-category structure could produce formulaic output where every category is force-filled even when it doesn't apply. | B (consumer blind spot) | Added constraint: "If a category genuinely doesn't apply, say so in one line and move on." Added quality criterion: "At least one category (A-F) is explicitly marked not applicable." |

### Rejected

| # | Finding | Category | Rejection Rationale |
|---|---------|----------|---------------------|
| 1 | **Add scalability for document suites** (reviewing 5+ related docs at once). | E (effort) | The single-document focus is a feature, not a limitation. Reviewing a document suite requires different coordination patterns (cross-document consistency, shared terminology, dependency ordering) that would double the prompt's complexity. A separate "Suite Review" prompt would be more useful than overloading this one. |
| 2 | **Connect the priority table to a task tracking system** (auto-create tasks from review findings). | C (unleveraged value) | Different projects use different tracking systems (GitHub Issues, Jira, ContextCore spans, plain TODO files). Baking in a specific integration would make the prompt less portable. The priority table is already actionable as-is — a human or agent can create tasks from it in whatever system they use. |
| 3 | **Make reviewer profiles reusable across documents** (generate a profile library that persists across reviews). | C (unleveraged value) | Marginal benefit for significant complexity. Reviewer profiles are valuable because they're specific to a document's blind spots. A "Database Migration Expert" profile for one document needs entirely different questions than the same profile for another. Reuse would water down specificity. |
| 4 | **Replace the prescriptive 6-category structure with a freeform "find the weak spots" approach.** | F (design tension) | The structure is what makes the output useful and comparable across documents. The applied fix (allowing categories to be marked "not applicable") addresses the formulaic risk without losing the structural benefit. Freeform prompts produce inconsistent output quality — some guides would be excellent, others would miss entire categories of risk. The structure is a floor, not a ceiling. |
| 5 | **Add output length guidance** (e.g., "aim for 150-250 lines"). | E (effort) | The existing "under 400 lines" constraint is sufficient. Adding a target range over-constrains the output. A document with 2 real issues needs a short guide; a document with 8 needs a longer one. The constraint should prevent bloat, not prescribe length. |
| 6 | **The prompt has only been validated on one document type.** | A (validation gap) | True, but unfixable by editing the prompt. This is a "run it and see" validation that happens through usage, not through prompt revision. The adaptation guidance for four document types (requirements, plans, designs, ADRs) provides structural support for generalization. The real validation will come from the next person who uses it. |
