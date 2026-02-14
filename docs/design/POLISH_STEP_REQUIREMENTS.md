# Polish Step Requirements [EXPERIMENTAL]

Purpose: Define the behavioral requirements for `contextcore polish` — an experimental advisory pipeline step that analyzes artifacts for missing elements and suggests improvements to enhance output quality.

> **Status**: Experimental. Not officially part of the 7-step pipeline yet.

This document is intentionally living guidance. Update it as the polish heuristics evolve.

---

## Experimental Status

This command is currently in the **experimental** phase. It is available for manual use but should not be treated as a blocking gate in production pipelines yet.

---

## Vision

The Polish step acts as an automated editor or "linter for content quality." Unlike gates which enforce structural correctness (valid JSON, existing files), the Polish step focuses on **completeness and quality** of the *content* within artifacts.

It is strictly **advisory**. It suggests improvements but does not block the pipeline by default. It helps users (human or agent) refine their inputs (plans, specs, requirements) before they are processed by downstream contractors.

**Core principle**: Catch missing semantic elements early. A plan without clear objectives will lead to ambiguous execution.

---

## Pipeline Placement

The Polish step is designed to run **before** critical pipeline transitions where ambiguity is costly.

Recommended placement:
1. **Pre-Export**: Run on source plans/markdown files before `manifest export`.
2. **Pre-Ingestion**: Run on exported artifacts before `plan-ingestion` starts.

It can be run standalone to iterate on a document:
`contextcore polish plans/MY_PLAN.md`

---

## Functional Requirements

### Scope: Plans (Markdown)

The initial implementation focuses on Plan artifacts (Markdown files, typically in `plans/`).

#### Check 1: Overview Section Existence
- **Requirement**: A Plan MUST have a dedicated section for "Overview".
- **Detection**: Look for a Markdown header (H1 or H2) matching "Overview" (case-insensitive).
- **Advisory**: If missing, suggest: "Add an 'Overview' section to describe the plan's context."

#### Check 2: Overview Content (Objectives & Goals)
- **Requirement**: The "Overview" section SHOULD clearly state the "Objectives" and "Goals" of the plan.
- **Detection**: Within the text under the "Overview" header (before the next header), look for keywords:
    - "Objective" or "Objectives"
    - "Goal" or "Goals"
- **Advisory**: 
    - If "Objectives" missing: "The Overview should explicitly mention the 'Objectives' of this plan."
    - If "Goals" missing: "The Overview should explicitly mention the 'Goals' for completion."

---

## Future Scope

While the initial version focuses on Plan Overviews, the architecture must support extensible "Polishers" for other artifact types and rules:

- **Requirements Docs**: Check for "Success Criteria", "User Stories".
- **Design Docs**: Check for "Alternatives Considered", "Risks".
- **Code Comments**: Check for "Args", "Returns" in docstrings (if not covered by other linters).

---

## Report Structure

The command should output a user-friendly list of suggestions.

### Output Format
- **Human-readable**: clearly grouped by file.
- **Severity**: "Suggestion" (default) or "Warning".
- **Actionable**: Clear instruction on how to fix (e.g., "Add '## Overview' to the top of the file").

Example Output:
```text
[SUGGESTION] plans/feature-x.md
  - Missing 'Overview' section.
    -> Add a section describing the high-level purpose.

[SUGGESTION] plans/feature-y.md
  - 'Overview' section is missing 'Goals'.
    -> Explicitly list what constitutes completion.
```

---

## CLI Surface

```bash
contextcore polish <target>
  target                (required)   File or directory to polish
  --fix                 (optional)   Attempt to auto-fix simple issues (future)
  --strict              (optional)   Exit with non-zero code if suggestions exist
  --format              (default: text)  Output format: text | json
```

## Non-Functional Requirements

- **Advisory by Default**: Must not break the build unless `--strict` is used.
- **Fast**: Should run almost instantly on typical markdown files.
- **Resilient**: Should handle malformed markdown gracefully without crashing.
