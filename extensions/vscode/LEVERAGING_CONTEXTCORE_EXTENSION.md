# Leveraging the ContextCore VS Code Extension

## What the Extension Provides

The ContextCore VS Code extension (v0.2.0) surfaces project metadata — risks, criticality, SLO requirements, expansion packs, and design references — directly in the IDE. It loads context from three sources (local `.contextcore.yaml` > CLI > Kubernetes CRD) and maps it to individual files using risk scope glob patterns.

### Data Available at File Level

| Category | Fields | Example |
|----------|--------|---------|
| **Criticality** | `critical`, `high`, `medium`, `low` | Status bar color, model selection |
| **Risks** | type, priority (P1-P4), scope globs, mitigation, component | `src/auth/**` = security risk |
| **Requirements** | availability, latency P50/P99, throughput, error budget, SLO targets | `latencyP99: 500ms` |
| **Design** | ADR refs, API contracts, agent protocols, diagrams | Links to architecture docs |
| **Observability** | trace sampling, metrics interval, log level, alert channels, runbooks | `traceSampling: 1.0` |
| **Expansion Packs** | name, animal codename, purpose, status, dependencies | Fox (Alert Automation) |
| **Business** | owner, cost center, value description | Cost attribution |

### Current Capabilities

- **7 commands**: refresh, show risks, impact analysis, open dashboards (14 pre-built), manifest validate/show/fix
- **File-to-context mapping**: 3-tier priority (risk scope patterns > parent directory > workspace root)
- **Inline decorations**: criticality hint on first line of each file, color-coded
- **Side panel tree**: project metadata, nested risks with severity icons, SLO targets, expansion packs
- **Status bar**: criticality indicator with quick-action menu

---

## Value Proposition

### 1. Risk-Aware Code Generation (Artisan Contractor)

**Problem**: The 8-phase artisan pipeline treats all generated code equally. A utility helper and a payment processor get the same review depth, model selection, and test coverage.

**Value**: Project context transforms the pipeline from uniform to risk-proportional.

| Phase | Without Context | With Context |
|-------|----------------|--------------|
| PLAN | Uniform task decomposition | Tasks tagged with risk scope matches; P1 risks get dedicated sub-tasks |
| DESIGN | Same model for all designs | Critical-project designs routed to higher-capability models |
| IMPLEMENT | Standard code generation | Files in security risk scopes get additional constraints injected into prompts |
| INTEGRATE | Merge all staged files | Risk-scoped files get pre-merge validation against SLO requirements |
| TEST | Uniform test generation | P1/P2 risk areas get mandatory edge-case and failure-mode tests |
| REVIEW | Fixed pass threshold | `pass_threshold` scaled by criticality (0.9 for critical, 0.7 for low) |
| FINALIZE | Standard assembly | Risk assessment summary appended to final output |

**Estimated impact**: Reduces review rework on high-risk code by focusing LLM attention where it matters most. Avoids over-investing review cycles on low-risk utilities.

### 2. Cost-Efficient Model Routing (Prime Contractor)

**Problem**: Prime Contractor uses the same drafter/validator/reviewer model tier for all features in a batch, regardless of project importance.

**Value**: Criticality-based model selection routes expensive models to critical code and cheaper models to low-risk work.

```
critical → drafter: SONNET, reviewer: OPUS     (~$2.50/feature)
high     → drafter: SONNET, reviewer: SONNET   (~$1.20/feature)
medium   → drafter: HAIKU,  reviewer: SONNET   (~$0.45/feature)
low      → drafter: HAIKU,  reviewer: HAIKU    (~$0.15/feature)
```

For a 20-feature batch with mixed criticality, this could reduce costs 40-60% vs uniform SONNET routing while maintaining quality where it counts.

### 3. Scope-Driven Impact Analysis

**Problem**: When generating code that touches files in a risk scope, the pipeline doesn't know which other files share that risk context.

**Value**: Risk scope patterns (`src/auth/**`, `src/payments/**`) let the pipeline:
- Identify all files affected by a change in the same risk zone
- Auto-include related test files in the TEST phase
- Flag cross-scope changes for additional review (a change touching both `auth` and `payments` scopes triggers compound-risk handling)

### 4. SLO-Informed Test Generation

**Problem**: Generated tests validate correctness but not performance characteristics.

**Value**: SLO requirements from `.contextcore.yaml` can seed test assertions:
- `latencyP99: 500ms` → generate benchmark tests with 500ms threshold
- `availability: 99.9%` → generate resilience tests (retry, circuit breaker)
- `errorBudget: 0.1%` → generate error-rate monitoring assertions

### 5. Manifest Validation as Pipeline Gate

**Problem**: Code generation can drift from project context (e.g., adding a new service without updating risk scopes or SLO targets).

**Value**: `contextcore manifest validate` as a FINALIZE gate catches context drift before merge. The extension already provides this as a command; wiring it into the pipeline adds automated enforcement.

---

## Integration Paths

### Path A: Enriched Context Seed (Lowest Effort)

The artisan pipeline already consumes an enriched context seed JSON. Adding a `project_metadata` section from `.contextcore.yaml` requires:

1. **PlanIngestionWorkflow** reads `.contextcore.yaml` alongside the plan document
2. Emits `project_metadata`, `project_risks`, `project_criticality`, `project_slos` into seed
3. **PlanPhaseHandler** extracts these into the shared `context` dict (3 lines, matching existing pattern for `architectural_context`)
4. All downstream phases can optionally read the new keys

```
.contextcore.yaml ──→ PlanIngestionWorkflow ──→ enriched seed JSON
                                                    │
                                                    ├─ project_metadata: {...}
                                                    ├─ project_criticality: "high"
                                                    ├─ project_risks: [...]
                                                    └─ project_slos: {...}
                                                    │
                                              PlanPhaseHandler
                                                    │
                                              context["project_metadata"]
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                              DesignPhase    ImplementPhase    ReviewPhase
                              (adjust rigor) (inject constraints) (scale threshold)
```

**Changes required**: ~50 lines across 3 files. No handler signature changes. Purely additive.

### Path B: MCP Server (Medium Effort, Broad Value)

Extract the extension's `ContextProvider` + `ContextMapper` logic into an MCP server that Claude Code, Cursor, and other AI tools can query.

**Tools to expose**:
- `contextcore:get-file-context` — returns ProjectContext for a file path
- `contextcore:list-risks` — returns all risks with scope patterns
- `contextcore:check-risk-scope` — checks if a file falls within any risk scope
- `contextcore:get-slo-targets` — returns SLO requirements for the project

**Value**: Any AI coding tool gains project awareness without extension-specific integration. Claude Code could proactively check risk scopes before editing files.

### Path C: Preflight Rule Plugin (Targeted)

Register a ContextCore-aware preflight rule via the existing `startd8.preflight_rules` entry point:

```python
# contextcore_preflight.py
class ContextCoreRiskRule(PreflightRule):
    """Block code generation in P1 risk scopes without mitigation plan."""

    def check(self, task, context):
        risks = context.get("project_risks", [])
        for risk in risks:
            if risk["priority"] == "P1" and not risk.get("mitigation"):
                return PreflightResult.FAIL(
                    f"P1 risk '{risk['type']}' in scope {risk['scope']} "
                    f"has no mitigation plan"
                )
        return PreflightResult.PASS()
```

**Changes required**: Single new file + entry point registration. No existing code modified.

### Path D: Quality Gate Parameterization (Surgical)

Extend `QualitySpec` in `gate_contracts.py` to accept criticality-based overrides:

```yaml
# artisan-pipeline.contract.yaml
phases:
  REVIEW:
    quality:
      default:
        pass_threshold: 0.75
      by_criticality:
        critical: { pass_threshold: 0.95, require_security_review: true }
        high: { pass_threshold: 0.85 }
```

**Changes required**: ~30 lines in `gate_contracts.py` + contract YAML update.

---

## Recommended Adoption Order

| Priority | Path | Effort | Value |
|----------|------|--------|-------|
| 1 | **A: Enriched seed** | Low (~50 lines) | Foundation — all other paths build on this |
| 2 | **C: Preflight rule** | Low (~1 file) | Immediate safety gate for P1 risks |
| 3 | **D: Quality gate params** | Low (~30 lines) | Criticality-proportional review |
| 4 | **B: MCP server** | Medium (~500 lines) | Ecosystem-wide AI tool integration |

---

## What Changes in Developer Experience

### Before (Current State)

```
Developer opens file → edits code → runs tests → commits
                       ↕
                  No awareness of:
                  - Which risk zone this file belongs to
                  - What SLO requirements apply
                  - Whether changes impact other risk-scoped files
                  - What criticality level governs review depth
```

### After (With Integration)

```
Developer opens file → extension shows criticality + risks inline
    ↓
AI tool queries context → risk-aware code generation
    ↓
Pipeline adjusts: model tier, review depth, test coverage
    ↓
Preflight blocks P1-risk changes without mitigation
    ↓
Quality gates scale by criticality
    ↓
Manifest validation catches context drift at FINALIZE
```

### For AI-Assisted Workflows Specifically

The extension's data model answers questions that LLMs currently can't infer from code alone:

- **"How careful should I be with this file?"** → criticality + risk scope match
- **"What non-functional requirements apply?"** → SLO targets from requirements
- **"What else might break?"** → risk scope patterns identify co-risk files
- **"Who cares about this?"** → business owner, cost center
- **"What design decisions govern this area?"** → ADR and API contract references

These are exactly the inputs that improve code generation quality in the artisan DESIGN and REVIEW phases — context that no amount of code reading can replace.
