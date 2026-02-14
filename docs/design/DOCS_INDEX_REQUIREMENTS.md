# Documentation Index Requirements

Purpose: define the behavioral requirements for `contextcore docs index`, `contextcore docs show`, `contextcore docs audit`, and `contextcore docs curate` — the commands that generate, query, audit, and curate persona-specific catalogs from the programmatically derived documentation index. The documentation index tracks all documentation artifacts, their types, cross-references, capability linkage, and freshness. The audit command reverse-engineers the capability index to detect documentation gaps. The curate command maps documentation to user personas for onboarding and operations.

This document is intentionally living guidance. Update it as the commands evolve.

---

## Vision

ContextCore has 150+ documentation artifacts spread across `docs/` and `plans/`. Without a systematic index, documentation becomes invisible: requirements docs exist but aren't linked to capabilities, design docs reference each other but the dependency graph is implicit, and orphaned docs accumulate without detection.

The documentation index inverts the capability index's evidence pattern. Where capability YAMLs say "this capability is documented by X", the docs index says "this document governs capabilities X, Y, Z and depends on documents A, B, C." Both views are needed:

- **Capability-centric** (existing): "What evidence supports this capability?"
- **Document-centric** (this): "What does this document govern, reference, and depend on?"

**Core principle**: The docs index is programmatically derived, never hand-edited. Every field is computed from source data (capability index evidence entries, file system scan, git history, document content analysis). Re-run the generator to update.

---

## Relationship to Capability Index

The docs index is a **derived artifact** of the capability index, not a replacement:

```
capability index YAMLs ───┐
                           ├──► generate_docs_index.py ──► contextcore.docs.yaml
docs/ + plans/ directory ──┘
```

The generator reads:
1. `type: doc` evidence entries from `contextcore.agent.yaml`, `contextcore.user.yaml`, `contextcore.benefits.yaml`, `contextcore.pain_points.yaml`
2. All `.md` and `.yaml` files in `docs/` and `plans/`
3. Git commit history for freshness dates
4. Document content for type classification, title extraction, cross-references, and maturity signals

The output is `docs/capability-index/contextcore.docs.yaml`.

---

## CLI Commands

### `contextcore docs index`

#### Purpose

Generate or regenerate the documentation index from source data. This is the primary command.

#### Functional Requirements

##### Generation

| ID | Requirement |
|----|-------------|
| FR-D-001 | Read all capability index YAMLs from `docs/capability-index/` and extract `type: doc` evidence entries |
| FR-D-002 | Scan `docs/` and `plans/` directories recursively for `.md` and `.yaml` files |
| FR-D-003 | Classify each document into a type taxonomy: requirements, design, operational, adr, analysis, plan, reference, session, governance |
| FR-D-004 | Extract document title from first H1 markdown heading |
| FR-D-005 | Detect maturity signals from content: draft, stable, deprecated, active |
| FR-D-006 | Extract CLI command references (`contextcore <subcommand>`) and pipeline step references as scope keywords |
| FR-D-007 | Discover cross-document references by scanning markdown links, backtick paths, and plain-text file paths |
| FR-D-008 | Look up git last-modified date for each file via `git log` |
| FR-D-009 | Identify documents referenced by capability evidence vs. orphaned documents (not referenced by any capability) |
| FR-D-010 | Track evidence references that point outside scanned directories (external evidence refs) |
| FR-D-011 | Write output to `docs/capability-index/contextcore.docs.yaml` by default |

##### Output Schema

The generated YAML must include:

| Section | Contents |
|---------|----------|
| `manifest_id` | `contextcore.docs` |
| `version` | Semantic version of the index schema |
| `generated_at` | ISO date of generation |
| `generator` | Path to the generator script |
| `sources` | Which capability index files and directories were scanned |
| `document_types` | Taxonomy of document types with descriptions |
| `summary` | Counts: total, referenced, orphaned, by-type, external refs |
| `documents[]` | Array of document entries (see below) |
| `external_evidence_refs[]` | Evidence refs pointing outside scanned dirs |

Each document entry must include:

| Field | Required | Description |
|-------|----------|-------------|
| `doc_id` | yes | Semantic ID derived from path (`contextcore.docs.{path_segments}`) |
| `path` | yes | Relative path from repo root |
| `type` | yes | Document type from taxonomy |
| `maturity` | yes | draft, stable, deprecated, or active |
| `referenced` | yes | Boolean: is this doc referenced by any capability evidence? |
| `title` | if available | First H1 heading from content |
| `line_count` | if available | Non-empty line count |
| `scope_keywords` | if available | CLI commands and pipeline steps found in content |
| `governs_capabilities` | if referenced | Array of {capability_id, role} from evidence entries |
| `references` | if any | Cross-document references (paths to other docs in the index) |
| `last_modified` | if git available | ISO date from git log |

##### CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--output`, `-o` | PATH | `docs/capability-index/contextcore.docs.yaml` | Output file path |
| `--dry-run` | flag | false | Print to stdout instead of writing file |
| `--no-git` | flag | false | Skip git freshness lookup (faster) |
| `--format` | choice | `yaml` | Output format: `yaml` or `json` |

##### Behavior

| ID | Requirement |
|----|-------------|
| FR-D-020 | Resilient to YAML parse errors in capability index files (warn and skip, don't abort) |
| FR-D-021 | Cross-references only include paths that exist on disk (no dangling refs) |
| FR-D-022 | Idempotent: running twice with same inputs produces identical output (except `generated_at`) |
| FR-D-023 | Auto-header: output file begins with comment stating it is auto-generated and should not be hand-edited |
| FR-D-024 | Exit 0 on success, exit 1 on fatal error |

##### Next Steps Output

After successful generation, print summary:
```
Documentation index generated: docs/capability-index/contextcore.docs.yaml
  152 documents indexed (8 referenced, 144 orphaned)
  158 cross-references across 40 documents
  Type breakdown: plan (55), design (28), analysis (22), ...

Next steps:
  1. Review orphaned documents for capability linkage opportunities
  2. Run: contextcore docs show --orphaned     (list unreferenced docs)
  3. Run: contextcore docs show --type requirements  (list requirements docs)
```

---

### `contextcore docs show`

#### Purpose

Query the documentation index with filters. Read-only — does not modify the index.

#### Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-D-100 | Load `contextcore.docs.yaml` from default or specified path |
| FR-D-101 | Filter by document type: `--type requirements`, `--type design`, etc. |
| FR-D-102 | Filter orphaned documents: `--orphaned` (referenced=false) |
| FR-D-103 | Filter referenced documents: `--referenced` (referenced=true) |
| FR-D-104 | Filter by capability: `--capability contextcore.pipeline.check_pipeline` (docs governing that capability) |
| FR-D-105 | Show cross-reference graph for a specific document: `--refs-for docs/MANIFEST_EXPORT_REQUIREMENTS.md` |
| FR-D-106 | Show freshness report: `--stale-days 30` (docs not modified in N days) |
| FR-D-107 | Summary mode (default when no filters): show type breakdown and top-level stats |

##### CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--index-path` | PATH | `docs/capability-index/contextcore.docs.yaml` | Path to docs index |
| `--type` | choice | (none) | Filter by document type |
| `--orphaned` | flag | false | Show only unreferenced documents |
| `--referenced` | flag | false | Show only referenced documents |
| `--capability` | TEXT | (none) | Show docs governing a specific capability |
| `--refs-for` | PATH | (none) | Show cross-reference graph for a document |
| `--stale-days` | INT | (none) | Show documents not modified in N days |
| `--format` | choice | `text` | Output format: `text`, `json`, `yaml` |

##### Output

Text output should be a human-readable table. JSON/YAML output should be the filtered subset of documents suitable for programmatic consumption.

---

### `contextcore docs audit`

#### Purpose

Reverse-engineer the capability indexes (agent, user, benefits, roadmap) and the documentation index to identify documentation gaps — capabilities or capability clusters that should have specific document types but don't. Gaps are scored by a multi-dimensional importance model and consolidated by namespace cluster.

#### Importance Scoring Model

Each capability receives an importance score in [0, 1] computed from four weighted dimensions:

| Dimension | Weight | Signals |
|-----------|--------|---------|
| Maturity-Confidence Composite | 30% | `0.6 * maturity_weight + 0.4 * confidence` where stable=1.0, beta=0.7, draft=0.4 |
| Structural Complexity | 25% | Normalized: input properties + required fields + output properties + 2x anti_patterns + 3x risk_flags |
| Cross-Cutting Impact | 25% | Dependency fanout + persona count + 2x critical personas + category bonus (validate/integration = 0.3) |
| Benefit Linkage | 20% | Priority weight * persona breadth * delivery status weight. Orphan capabilities get 0.2 |

#### Expected Document Rules

| Rule | Condition | Expected Type |
|------|-----------|---------------|
| R1 | stable + (CLI command OR inputs >= 3 properties) | `requirements` |
| R2 | stable/beta + raw complexity > 10 | `design` |
| R3 | has CLI triggers in description or trigger phrases | `operational` |
| R4 | has anti_patterns OR risk_flags | `adr` |
| R5 | category=validate + stable | `requirements` |
| R6 | category=integration | `design` |
| R7 | delivers gap benefit with functional_requirements | `requirements` |
| R8 | stable + confidence >= 0.9 | `reference` |

#### Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-D-200 | Load all four capability index files (agent, user, benefits, roadmap) from `docs/capability-index/` |
| FR-D-201 | Load the documentation index (`contextcore.docs.yaml`) to determine actual doc coverage per capability |
| FR-D-202 | Compute importance score for each capability using the 4-dimension weighted model |
| FR-D-203 | Apply expected document rules to determine which doc types should exist per capability |
| FR-D-204 | Detect gaps: `expected - actual` doc types per capability |
| FR-D-205 | Consolidate gaps into namespace clusters (group by first two dotted segments of capability_id) |
| FR-D-206 | Compute cluster-level statistics: avg importance, max importance, highest capability |
| FR-D-207 | Suggest concrete filenames for each cluster gap (e.g., `docs/HANDOFF_REQUIREMENTS.md`) |
| FR-D-208 | Assign priority labels: high (avg importance >= 0.6), medium (>= 0.4), low (< 0.4) |
| FR-D-209 | Build human-readable rationale for each gap from capability signals |
| FR-D-210 | Filter gaps by minimum importance threshold (default 0.3) |
| FR-D-211 | Filter gaps by missing document type |
| FR-D-212 | Support verbose mode showing per-capability detail within each cluster |
| FR-D-213 | Resilient to YAML parse errors in capability index files (warn and skip) |

##### CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--index-path` | PATH | `docs/capability-index/contextcore.docs.yaml` | Path to docs index |
| `--min-importance` | FLOAT | 0.3 | Only report gaps above this importance threshold |
| `--type` | choice | (none) | Filter to show only gaps of a specific document type |
| `--format` | choice | `text` | Output format: `text`, `json`, `yaml` |
| `--verbose` | flag | false | Show per-capability detail within cluster summaries |

##### Output

Text output shows:
1. Summary header: capabilities analyzed, gap count, cluster count, priority breakdown
2. Missing doc type histogram across all gaps
3. Cluster gaps sorted by avg importance descending, with priority markers (high/medium/low)
4. Per-cluster: missing type, highest capability, rationale, suggested filename
5. Next steps guidance

JSON/YAML output includes full audit results: summary, clusters array, per-capability gaps array with importance detail.

---

### `contextcore docs curate`

#### Purpose

Generate persona-specific documentation catalogs by tracing persona-to-capability-to-document chains. Classifies each relevant document as onboarding or operations material and detects persona-specific documentation gaps.

#### Document Discovery Signals

Documents are discovered for each persona via three independent signals, merged by max relevance score:

| Signal | Score | Chain |
|--------|-------|-------|
| Capability Evidence | 0.9 | persona → capabilities (user.yaml) → evidence[type=doc] |
| Benefit-to-Capability | 0.7 | persona → benefits (benefits.yaml) → delivered_by → evidence[type=doc] |
| Document Type Affinity | 0.4 | persona role → matching document types (e.g., operator → operational, reference) |

#### Document Type Affinity Map

| Persona | Affinity Types |
|---------|---------------|
| developer | requirements, design, reference, operational |
| project_manager | plan, operational, analysis |
| engineering_leader | design, plan, analysis |
| operator | operational, reference |
| compliance | governance, reference, analysis |
| ai_agent | reference, design |

#### Onboarding vs Operations Classification

| Category | Matching Criteria |
|----------|-------------------|
| Onboarding | type=reference; type=operational with title matching: quickstart, getting-started, install, onboarding, harbor-tour, setup, tutorial |
| Operations | type=requirements, design, analysis, plan, adr, governance; type=operational with title matching: troubleshoot, runbook, known-issues, migration, incident |

#### Gap Detection Rules

| Rule | Condition | Gap Reported |
|------|-----------|-------------|
| G1 | No onboarding docs for persona | "No onboarding documentation" — suggested: `docs/onboarding/{persona}-quickstart.md` |
| G2 | No operations docs for persona | "No operations documentation" — suggested: `docs/operations/{persona}-guide.md` |
| G3 | Critical-importance benefit with undocumented delivering capabilities | Per-benefit gap with capability list |
| G4 | operator persona with no troubleshooting/runbook docs | "No troubleshooting/runbook documentation" |
| G5 | compliance persona with no governance docs | "No governance/audit procedure documentation" |

#### Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-D-300 | Load persona definitions from `contextcore.benefits.yaml` (name, description, goals) and `contextcore.user.yaml` (primary_value, pain_point) |
| FR-D-301 | Build persona-to-capability mapping from `user.yaml` capability `personas[]` arrays |
| FR-D-302 | Build persona-to-benefit mapping from `benefits.yaml` benefit `personas[].persona_id` with importance |
| FR-D-303 | Walk capability evidence chains: persona → capability → evidence[type=doc] → docs index (Signal 1, score 0.9) |
| FR-D-304 | Walk benefit-to-capability chains: persona → benefit → delivered_by → evidence[type=doc] → docs index (Signal 2, score 0.7) |
| FR-D-305 | Apply document type affinity matching per persona role (Signal 3, score 0.4) |
| FR-D-306 | Merge signals by max score per document-persona pair |
| FR-D-307 | Filter documents by minimum relevance threshold (default 0.4) |
| FR-D-308 | Classify each persona-relevant document as onboarding or operations |
| FR-D-309 | Detect persona-specific documentation gaps using rules G1-G5 |
| FR-D-310 | Support filtering by persona ID (show single persona catalog) |
| FR-D-311 | Support filtering by category (onboarding only or operations only) |
| FR-D-312 | Support gaps-only mode to show only documentation gaps |
| FR-D-313 | Report per-persona summary: capability count, benefit count, doc counts by category, gap count |
| FR-D-314 | Aggregate summary: personas analyzed, total gaps, high-priority gaps, avg docs per persona |

##### CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--index-path` | PATH | `docs/capability-index/contextcore.docs.yaml` | Path to docs index |
| `--persona` | TEXT | (none) | Show results for a single persona |
| `--category` | choice | (none) | Show only onboarding or operations docs |
| `--gaps-only` | flag | false | Only show documentation gaps |
| `--format` | choice | `text` | Output format: `text`, `json`, `yaml` |
| `--min-relevance` | FLOAT | 0.4 | Minimum document-persona relevance threshold |

##### Output

Text output shows per-persona sections with:
1. Header: persona name, capability count, benefit count
2. Pain point and goals from persona profile
3. Onboarding documents sorted by relevance score descending
4. Operations documents sorted by relevance score descending
5. Each document shows relevance score, path, and discovery signal (via)
6. Documentation gaps with priority and suggested filenames

JSON/YAML output includes full results: summary, per-persona array with onboarding/operations catalogs and gaps.

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-D-001 | `docs index` must complete in <10 seconds without git, <60 seconds with git for up to 500 documents |
| NFR-D-002 | `docs show` must complete in <1 second (reads a single YAML file) |
| NFR-D-003 | No external dependencies beyond PyYAML, Click, and Git (already in the project) |
| NFR-D-004 | Generator script (`scripts/generate_docs_index.py`) must remain independently runnable outside the CLI for CI integration |
| NFR-D-005 | Document type classification heuristics must be deterministic (same input always produces same type) |
| NFR-D-006 | `docs audit` must complete in <5 seconds (reads YAML files and computes scores in-memory) |
| NFR-D-007 | Importance scoring must be deterministic: same capability index inputs always produce same scores |
| NFR-D-008 | Expected document rules must be transparent: each rule is documented with its condition and expected type |
| NFR-D-009 | `docs curate` must complete in <5 seconds (reads YAML files and walks chains in-memory) |
| NFR-D-010 | Relevance scoring must be deterministic: same inputs always produce same scores |
| NFR-D-011 | Onboarding vs operations classification must be deterministic: same document always gets same category |

---

## Document Type Taxonomy

| Type | Description | Filename Signals | Content Signals |
|------|-------------|------------------|-----------------|
| `requirements` | Behavioral spec (FR/NFR, acceptance criteria) | `*_REQUIREMENTS*`, `*REQUIREMENTS*` | "functional requirement", "FR-\d", "acceptance criteria" |
| `design` | Architecture, schemas, contracts, patterns | `*design*`, `*schema*`, `*contract*`, `*pattern*` | "architecture", "data model", "sequence diagram" |
| `operational` | Guides, runbooks, setup, troubleshooting | `*guide*`, `*runbook*`, `*troubleshoot*`, `*installation*` | "step 1", "prerequisite", "configure" |
| `adr` | Architecture Decision Records | `docs/adr/*` | — |
| `analysis` | Gap assessments, comparisons, audits | `*analysis*`, `*audit*`, `*comparison*` | "gap analysis", "findings", "recommendation" |
| `plan` | Implementation plans, phases, checklists | `plans/*`, `*_PLAN*`, `*checklist*` | "phase \d", "milestone", "timeline" |
| `reference` | Conventions, specs, API reference | `*convention*`, `*reference*`, `*semantic*` | — |
| `session` | Session logs, meeting notes | `*session*`, `*_log*` | — |
| `governance` | Policies, licenses | `*license*`, `*policy*`, `*governance*` | — |

Classification priority: filename rules checked first (in order), then content signals. First match wins.

---

## Acceptance Criteria

- [ ] `contextcore docs index` generates `contextcore.docs.yaml` with all fields from the output schema
- [ ] `contextcore docs index --dry-run` prints to stdout without writing
- [ ] `contextcore docs index --no-git` skips git lookup and omits `last_modified`
- [ ] `contextcore docs show` displays summary when run without filters
- [ ] `contextcore docs show --type requirements` lists only requirements documents
- [ ] `contextcore docs show --orphaned` lists only unreferenced documents
- [ ] `contextcore docs show --capability contextcore.pipeline.check_pipeline` lists docs governing that capability
- [ ] `contextcore docs show --refs-for docs/MANIFEST_EXPORT_REQUIREMENTS.md` shows inbound and outbound cross-references
- [ ] `contextcore docs show --stale-days 30` lists documents not modified in 30+ days
- [ ] Re-running `contextcore docs index` produces valid YAML loadable by `docs show`
- [ ] Generator script remains independently runnable: `python3 scripts/generate_docs_index.py`
- [ ] `contextcore docs audit` reports documentation gaps sorted by importance
- [ ] `contextcore docs audit --min-importance 0.5` only shows high-importance gaps
- [ ] `contextcore docs audit --type requirements` only shows requirements gaps
- [ ] `contextcore docs audit --verbose` shows per-capability detail within clusters
- [ ] `contextcore docs audit --format json` produces machine-readable output
- [ ] Cluster consolidation groups capabilities by namespace (e.g., `contextcore.aos.*`)
- [ ] Each cluster gap includes a suggested filename and rationale
- [ ] Importance scoring uses all four dimensions: maturity-confidence, complexity, cross-cutting, benefit linkage
- [ ] `contextcore docs curate` shows per-persona documentation catalog with onboarding/operations split
- [ ] `contextcore docs curate --persona operator` filters to a single persona
- [ ] `contextcore docs curate --category onboarding` shows only onboarding documents
- [ ] `contextcore docs curate --gaps-only` shows only documentation gaps
- [ ] `contextcore docs curate --format json` produces machine-readable output
- [ ] `contextcore docs curate --min-relevance 0.7` filters to high-relevance documents
- [ ] Three discovery signals merge correctly: capability evidence (0.9), benefit chain (0.7), type affinity (0.4)
- [ ] Persona-specific gap detection reports missing onboarding and operations docs per persona

---

## Evidence

| Type | Reference | Description |
|------|-----------|-------------|
| code | `scripts/generate_docs_index.py` | Generator script (iteration 1-3) |
| code | `src/contextcore/cli/docs.py` | CLI command implementation |
| doc | `docs/capability-index/contextcore.docs.yaml` | Generated output |
| doc | `docs/DOCS_INDEX_REQUIREMENTS.md` | This requirements document |
