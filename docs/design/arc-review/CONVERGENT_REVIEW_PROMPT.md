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
You are the primary author of the following document(s):

[PASTE OR REFERENCE YOUR DOCUMENT(S) HERE]

Your task is to write a Convergent Review Agent Guide — a structured
self-assessment that identifies where this document is weakest and where
external input would have the highest return on investment.

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
not been tested against reality. The Weaver V2 format example: decisions
made from reading documentation rather than running the actual tool.

**B. Consumer-side blind spots** — Places where the document specifies
what is produced but not whether consumers can actually use it. Requirement
levels, API designs, or schema decisions that feel correct from the
producer's perspective but may be wrong from the consumer's.

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
reordered. Include organizational risks (bandwidth, coordination,
abandonment) not just technical ones.

**F. Unresolved design tensions** — Decisions where the document chose
one option but the alternative has legitimate merit. The Option A vs
Option B pattern: the plan picks the simpler path but the harder path
may be correct. These are the most valuable items for external review
because the author has already considered both sides and cannot resolve
the tension alone.

### 2. Priority Table

End with a summary table ranking all review actions by ROI:

| Priority | Section | Action | Reviewer type |
|----------|---------|--------|---------------|

Rank by: How much would the document improve if this question were
answered well? Consider both probability of the current approach being
wrong AND the cost of being wrong.

### 3. Submission Instructions

Include instructions for how reviewers should submit feedback, adapted
to the document's existing review mechanism (if any). If the document
has an appendix-based review log, reference it. If not, specify a
lightweight format.

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
```

---

## What Makes a Good Guide vs a Bad One

**Good guide characteristics:**
- The author admits specific things they don't know ("I specified this format from docs, not from running the tool")
- Questions are answerable by a specific type of person ("run this YAML through weaver v0.21.2 and tell me what breaks")
- Unleveraged value items include a concrete description of the user benefit and the modest additional work required
- The priority table forces hard choices about what matters most

**Bad guide characteristics:**
- Generic questions ("is this design good?") that any reviewer could answer about any document
- Profiles that are roles rather than expertise ("senior engineer" instead of "someone who has built a Weaver registry")
- Every section marked as "high priority" — the ranking exists to force differentiation
- No specificity gaps identified — this usually means the author hasn't considered what happens when the document is used as LLM input

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
