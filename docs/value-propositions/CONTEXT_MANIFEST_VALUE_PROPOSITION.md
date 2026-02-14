# Context Manifest: Value Proposition

> Generated using the `capability-value-promoter` skill framework.
> This document articulates the value of the Context Manifest pattern for multiple personas.

---

## Document Overview

This document is organized into the following sections to help you quickly find the information most relevant to your role:

| Section | Description | Best For |
|---------|-------------|----------|
| **[Executive Summary](#executive-summary)** | One-paragraph overview and the core value proposition | Quick understanding |
| **[Pain Points by Persona](#the-problem-space-pain-points-by-persona)** | Detailed friction points organized by role (Developer, Operator, Manager) | Identifying your pain points |
| **[Capabilities](#the-solution-context-manifest-capabilities)** | How each manifest capability solves specific problems | Technical evaluation |
| **[Friction Eliminated](#friction-eliminated-summary-table)** | Before/after comparison table | Quick impact assessment |
| **[Value Quantification](#value-quantification)** | Time savings and risk reduction metrics | ROI justification |
| **[Creator's Reflection](#audience-of-1-creators-value-reflection)** | Why this pattern was built and what it gives the creator | Motivation/context |
| **[The Real ROI](#the-real-roi)** | Philosophical summary of the pattern's value | Executive pitch |
| **[Next Steps](#next-steps)** | How to get started | Implementation |
| **[Addendum 1: Systematic Improvements](#addendum-systematic-improvements-recommendations)** | 10 specific schema/tooling recommendations | Schema architects |
| **[Addendum 2: Implementation Patterns](#addendum-part-2-implementation-patterns--concrete-examples)** | Code examples for implementing recommendations | Developers |
| **[Addendum 3: Lessons Learned](#addendum-part-3-patterns-from-lessons-learned)** | Patterns from past development work | Best practices |
| **[Addendum 4: Manifest v2.0 Vision](#addendum-part-4-synthesis--future-proofing-manifest-v20-vision)** | Future direction and governance schema | Roadmap planning |
| **[Addendum 5: Post‑v1.1 Improvements](#addendum-part-5-post-v11-systematic-improvements)** | Next incremental upgrades after v1.1 | Maintainers |
| **[Appendix: Changes Applied](#appendix-a-changes-applied-from-recommendations)** | What was implemented from this document | Implementation tracking |
| **[Appendix: Rejected Suggestions](#appendix-b-rejected-suggestions-and-rationale)** | Suggestions not implemented and why | Future consideration |

---

## Executive Summary

The **Context Manifest** is a portable, tool-agnostic file (`.contextcore.yaml`) that serves as the single source of truth for a project's business context, strategic objectives, and derived insights. It enables programmatic extraction of metadata from codebases and project management tools while preventing "context stuffing" in Kubernetes CRDs.

**One-liner:** Stop losing business context between your roadmap, your code, and your cluster.

---

## The Problem Space: Pain Points by Persona

### 🧑‍💻 Developer Pain Points

| Pain Point | Severity | Frequency |
|------------|----------|-----------|
| **Context Lost in Handoffs**: "Why was this built? What's the business goal?" | High | Every PR review |
| **Tribal Knowledge**: Critical context lives only in someone's head | Critical | Onboarding, attrition |
| **Config Drift**: CRD in cluster differs from intent in design doc | Medium | Monthly |
| **Manual Status Reporting**: "What's the current state of project X?" | High | Weekly standups |
| **No Traceability**: Can't link a deployment to the strategy that drove it | Medium | Post-mortems |

### 👷 Operator / SRE Pain Points

| Pain Point | Severity | Frequency |
|------------|----------|-----------|
| **Missing Business Context in Alerts**: "Is this service critical?" | Critical | Every incident |
| **Over-instrumented CRDs**: Bloated YAML with data the controller never uses | Medium | Every deployment |
| **No Derivation Logic**: SLOs, sampling rates manually guessed instead of derived | High | Initial setup |
| **Shadow Configs**: Multiple sources of truth for the same service | High | Deployment failures |

### 📊 Engineering Manager / Product Owner Pain Points

| Pain Point | Severity | Frequency |
|------------|----------|-----------|
| **Roadmap Disconnection**: Strategy docs don't connect to actual code/infra | High | Quarterly planning |
| **Invisible Progress**: Can't see how tactics translate to deployed capabilities | High | Sprint reviews |
| **Manual Aggregation**: Assembling status from 5 different tools | Critical | Weekly reporting |
| **Risk Blindness**: Security/dependency risks discovered only at deploy time | Critical | CVE announcements |

---

## The Solution: Context Manifest Capabilities

### Capability 1: Unified Source of Truth

**Technical Description:**
A single `.contextcore.yaml` file that contains both operational spec (K8s-bound) and strategic context (business-bound).

**Value Proposition by Persona:**

| Persona | Benefit | Time Savings |
|---------|---------|--------------|
| **Developer** | One file to understand the "why" behind any service | 15-30 min/PR saved on context gathering |
| **Operator** | Confidence that CRD reflects current business intent | Eliminates config drift debugging |
| **Manager** | Single place to see strategy → tactics → code linkage | 1-2 hours/week on status aggregation |

---

### Capability 2: Distillation (CRD Generation)

**Technical Description:**
The manifest's `spec` section is automatically extracted and applied to Kubernetes as a lightweight `ProjectContext` CRD, keeping the cluster lean.

**Value Proposition by Persona:**

| Persona | Pain Point Eliminated | Benefit |
|---------|-----------------------|---------|
| **Developer** | "Why is this field in the CRD?" | Only operational data in cluster |
| **Operator** | Bloated CRDs slow kubectl, confuse controllers | 60-80% smaller CRDs |
| **Platform Team** | CRD versioning hell from strategic fields | Stable operational schema |

**Before & After:**

```yaml
# BEFORE: Overloaded CRD (❌)
spec:
  project:
    id: checkout
    roadmapUrl: https://...        # ← Strategic, not needed in cluster
    quarterlyGoals: [...]          # ← Strategic
    teamSlackChannel: "#checkout"  # ← Organizational
  business:
    criticality: critical          # ← Needed for derivation
    fullBusinessCase: |            # ← Too verbose for CRD
      ... 500 words ...

# AFTER: Lean CRD (✅)
spec:
  project:
    id: checkout
  business:
    criticality: critical
  requirements:
    availability: "99.99"
```

---

### Capability 3: Automated Insight Generation

**Technical Description:**
Scanners harvest metadata from code (dependencies, APIs), Git (churn, authors), and PM tools (Jira, GitHub Issues) to populate the `insights` section automatically.

**Value Proposition by Persona:**

| Persona | Pain Point Eliminated | Benefit |
|---------|-----------------------|---------|
| **Developer** | "I didn't know that dependency was deprecated" | Risks surfaced proactively |
| **Security** | Manual vulnerability scanning, report chasing | Automated dependency risk flags |
| **Manager** | "What risks are we carrying?" | Aggregated risk view per project |

**Example Derived Insights:**

```yaml
insights:
  - type: "risk"
    summary: "Dependency 'payment-sdk-v1' deprecated, EOL in 90 days"
    confidence: 1.0
    source: "scanner:dependency-check"

  - type: "pattern"
    summary: "High code churn (15 commits/week) in checkout/cart module"
    confidence: 0.85
    source: "scanner:git-analyzer"

  - type: "opportunity"
    summary: "3 services share identical retry logic—candidate for shared library"
    confidence: 0.78
    source: "scanner:code-duplication"
```

---

### Capability 4: Strategy-to-Execution Linkage

**Technical Description:**
The manifest includes `objectives`, `strategies`, and `tactics` sections that explicitly link business goals to technical implementations.

**Value Proposition by Persona:**

| Persona | Pain Point Eliminated | Benefit |
|---------|-----------------------|---------|
| **Developer** | "Why are we prioritizing this?" | Clear link from task to strategy |
| **Manager** | "Is this tactic actually executing our strategy?" | Traceable OKR → Task mapping |
| **Executive** | "What's the ROI on this engineering investment?" | Strategy execution visibility |

**Example:**

```yaml
objectives:
  - id: "OBJ-BLACK-FRIDAY"
    description: "Achieve 99.99% availability for Black Friday"
    metric: "availability"
    target: "99.99%"

strategies:
  - id: "STRAT-ASYNC"
    horizon: "now"
    description: "Move to async payment processing"
    rationale: "Sync calls to PaymentX cause latency spikes"
    tactics:
      - id: "TAC-KAFKA"
        description: "Implement Kafka queue for payment events"
        status: "in_progress"
        owner: "backend-team"

spec:
  risks:
    - type: "dependency"
      description: "Payment Gateway latency spikes"
      mitigation: "STRAT-ASYNC"   # ← Links back to strategy!
```

---

## Friction Eliminated: Summary Table

| Friction | Before Context Manifest | After Context Manifest |
|----------|------------------------|------------------------|
| **Context Discovery** | Grep Slack, read old PRs, ask around | Read one file |
| **CRD Bloat** | 200+ line CRDs with strategic data | 50-line operational CRDs |
| **Config Drift** | Manual sync between docs and cluster | Manifest is source, CRD is derived |
| **Risk Visibility** | Discovered at deploy time | Surfaced continuously by scanners |
| **Status Reporting** | Manual aggregation from 5 tools | Query the manifest or its telemetry |
| **Roadmap-to-Code Gap** | Strategy docs disconnected from infra | Explicit `objective → strategy → tactic → spec` chain |
| **Onboarding** | "Ask Sarah, she knows the history" | Self-documenting projects |

---

## Value Quantification

### Time Savings (Estimated)

| Activity | Before | After | Savings |
|----------|--------|-------|---------|
| Context gathering for PR review | 20 min | 5 min | 15 min/PR |
| Weekly status reporting | 2 hours | 30 min | 1.5 hr/week |
| Onboarding to new project | 1-2 days | 2-4 hours | 80% reduction |
| Post-mortem context assembly | 1 hour | 10 min | 50 min/incident |
| Risk identification | Ad-hoc | Continuous | Proactive vs. reactive |

### Risk Reduction

| Risk Category | Mitigation |
|---------------|------------|
| **Tribal Knowledge Loss** | Context persisted in version-controlled file |
| **Config Drift** | Single source of truth with derived CRDs |
| **Compliance Gaps** | Explicit risk tracking with mitigations linked |
| **Deployment Failures** | Dependencies validated before deploy |

---

## Audience of 1: Creator's Value Reflection

> For the creator (you) who built this capability—here's why it matters.

### Why I Built This

**The Trigger:** Watching engineers spend 30 minutes in every PR review trying to understand "why does this service exist?" and "what's the business goal?"

**The Frustration:** Context scattered across Notion, Slack threads, Jira epics, and someone's head. Kubernetes CRDs becoming dumping grounds for every piece of metadata.

**The Vision:** What if there was ONE file that answered "what is this project trying to achieve, and why?" that was both human-readable AND machine-processable?

### What It Gives Me

**Time Reclaimed:**
- **Per use:** 15-30 minutes saved on context gathering
- **Frequency:** Every PR review, every onboarding, every planning session
- **Annual impact:** 50-100 hours/year for a typical team

**Mental Space Freed:**
- Don't have to remember which Notion page has the roadmap
- Don't have to ask "who knows the history of this service?"
- Don't have to reconcile conflicting sources of truth

**Problems Solved:**
- No more "the CRD says X but the design doc says Y"
- No more tribal knowledge walking out the door
- No more strategic context lost between planning and execution

### Ripple Effects

**For My Team:**
- Faster onboarding (days → hours)
- Clearer PR reviews (context is right there)
- Better incident response (business criticality is known)

**For the Organization:**
- Strategy execution becomes visible
- Risk management becomes proactive
- Compliance becomes auditable

**For the Community:**
- A pattern others can adopt
- Bridges the gap between "business observability" and "infrastructure observability"
- Demonstrates that context is infrastructure

---

## The Real ROI

> "The Context Manifest eliminates the most expensive form of technical debt: **lost context**. Every hour spent re-discovering 'why' is an hour not spent on 'what's next.' This pattern pays for itself the first time it prevents a post-mortem question of 'why didn't we know this service was critical?'"

---

## Next Steps

1. **Adopt the schema:** Use `src/contextcore/models/manifest.py` to validate your manifests
2. **Create your first manifest:** Start with `examples/context_manifest_example.yaml` as a template
3. **Integrate scanners:** Build automated insight generation from your CI pipeline
4. **Derive CRDs:** Extract only the `spec` section for your Kubernetes deployments

---

*Generated by `capability-value-promoter` skill — bridging technical capabilities to human value.*

---

## Addendum: Systematic Improvements (Recommendations)

This addendum proposes systematic improvements to make the Context Manifest more **operationally reliable**, **toolable**, and **adoptable** across teams. Each item includes the rationale and the benefits for both business and technical users.

### 1) Resolve `.contextcore.yaml` schema collisions with `kind` + `apiVersion` + namespacing

- **What to change**: Add top-level identifiers and make the file explicitly multi-purpose without ambiguity.
  - `apiVersion: contextcore.io/v1alpha1`
  - `kind: ContextManifest`
  - `metadata: { name, owners, lastUpdated, links }`
  - Keep `spec:` as the CRD-distillable operational block.
  - Treat other top-level sections (`persistence`, `dependencies`, etc.) as **namespaced modules** or separate `kind`s (multi-document YAML is also viable).
- **Rationale / pain points addressed**:
  - The repo already uses `.contextcore.yaml` for **persistence config** (`src/contextcore/persistence/__init__.py`) and some docs show a **different top-level schema** (e.g., operational fields at root rather than under `spec`).
  - Without a discriminator, humans and agents will "successfully parse the wrong thing" and silently ignore fields.
- **Benefits**:
  - **Business**: Higher trust—"this file means one thing" in every repo; fewer adoption failures caused by confusion.
  - **Technical**: Deterministic parsing, easier migrations, safer automation (validators can enforce structure per `kind`).

### 2) Make IDs and cross-references first-class (integrity + traceability)

- **What to change**:
  - Enforce ID patterns and uniqueness for `objectives[*].id`, `strategies[*].id`, `tactics[*].id`.
  - Add explicit reference fields:
    - `strategy.objectives: [OBJ-...]` (which objectives this strategy supports)
    - `tactic.strategy: STRAT-...` (optional backref for flat lists, or keep nested but still referenceable)
    - `spec.risks[*].mitigationRef: STRAT-...|TAC-...` (typed reference, not free-form string)
  - Add validation that referenced IDs exist (Pydantic-level validation).
- **Rationale / pain points addressed**:
  - The example already demonstrates the *idea* of linkability (risk mitigation referencing strategy), but it's currently "stringly typed," so links can rot.
- **Benefits**:
  - **Business**: Reliable "why are we doing this?" chains (OKR → strategy → tactic → risk mitigated) that stay correct over time.
  - **Technical**: Enables tooling to compute coverage, find orphan tactics, and prevent drift in CI.

### 3) Add lifecycle semantics for tactics/objectives (so "planned vs done" becomes queryable)

- **What to change**:
  - Replace free-form `status: str` with an enum (e.g., `planned`, `in_progress`, `blocked`, `done`, `cancelled`) and add optional lifecycle fields:
    - `startDate`, `dueDate`, `completedDate`
    - `blockedReason` (when `status=blocked`)
    - `progress` (0–1 or 0–100)
- **Rationale / pain points addressed**:
  - Managers need consistent rollups; engineers need consistent filters; agents need stable states for reasoning and telemetry.
- **Benefits**:
  - **Business**: Less manual aggregation and fewer "status meetings" because progress is computable and comparable.
  - **Technical**: Enables derived metrics (cycle time, lead time, staleness) and better dashboarding without brittle string parsing.

### 4) Make objective metrics structured (to remove ambiguity and enable automation)

- **What to change**: Replace `Objective.metric`/`Objective.target` free-text with a structured "key result" shape:
  - `metricKey` (canonical key, e.g., `availability`, `latency.p99`)
  - `unit` (e.g., `%`, `ms`, `rps`)
  - `window` (e.g., `30d`, `7d`)
  - `baseline` + `target` (typed values)
  - `dataSource` (where the number comes from: Grafana panel, PromQL, TraceQL query reference, etc.)
- **Rationale / pain points addressed**:
  - "<200ms" is human-friendly but not machine-actionable; teams will otherwise reinvent parsing and disagree on meaning.
- **Benefits**:
  - **Business**: KPIs become auditable and consistently interpreted across orgs.
  - **Technical**: Dashboards, alerts, and reports can be generated and validated from the manifest.

### 5) Upgrade `Insight` into an actionable signal (evidence, impact, expiry)

- **What to change**:
  - Add optional fields: `id`, `severity/priority`, `observedAt`, `expiresAt`, `impact`, `evidence` (URLs, query refs, file paths), `recommendedActions`.
  - Add "decay" semantics: scanners should set `expiresAt` so stale insights don't linger forever.
- **Rationale / pain points addressed**:
  - Current `Insight` is informative but not decision-grade—teams need to know "how serious is this, and what do we do?"
- **Benefits**:
  - **Business**: Faster risk response; clearer prioritization when tradeoffs are needed.
  - **Technical**: Better incident/PR automation (route to right team, open ticket, enforce gates) based on severity + evidence.

### 6) Standardize ownership/contact fields (make "who owns this?" unmissable)

- **What to change**: Promote ownership to a structured shape (even if it duplicates some `spec.business.owner` semantics at the strategic layer):
  - `owners: [{ team, slack, oncall, email }]`
  - `stakeholders` as typed contacts
- **Rationale / pain points addressed**:
  - During incidents and escalations, "owner as a string" is rarely enough; operators need working contact paths.
- **Benefits**:
  - **Business**: Reduced mean time to coordinate and recover in high-impact events.
  - **Technical**: Enables routing automation (alerts, tickets, PR reviewers) without bespoke per-org conventions.

### 7) Add artifact linkage so progress can be derived (not self-reported)

- **What to change**:
  - Let tactics reference artifacts: `issues`, `prs`, `commits`, `deployments`, `dashboards`, `runbooks`.
  - Prefer stable identifiers (URLs + canonical IDs) and keep them optional to reduce upfront burden.
- **Rationale / pain points addressed**:
  - The framework's promise is "no manual status reporting." That requires linking work to observable artifacts.
- **Benefits**:
  - **Business**: Real progress visibility tied to real outputs; less reporting overhead.
  - **Technical**: Agents/scanners can update statuses automatically from Git/CI/CD events.

### 8) Ship "manifest UX": formatter, linter, validator, and migration tooling

- **What to change**:
  - CLI subcommands (or equivalent) for:
    - `contextcore manifest validate` (schema + cross-ref integrity)
    - `contextcore manifest format` (canonical ordering/formatting)
    - `contextcore manifest distill-crd` (extract `spec` reliably)
    - `contextcore manifest migrate` (version-to-version transforms)
  - Add CI gates + pre-commit checks (fast feedback).
- **Rationale / pain points addressed**:
  - A schema without ergonomic tooling becomes shelfware; validation needs to happen where changes occur (local + CI).
- **Benefits**:
  - **Business**: Higher adoption rate; fewer rollout stalls caused by inconsistent files.
  - **Technical**: Prevents broken links and malformed manifests from ever landing on `main`.

### 9) Define governance rules so the manifest stays trusted over time

- **What to change**:
  - Lightweight policy guidance:
    - Who owns strategic vs operational sections
    - Required review for changes to criticality/SLOs/risk priorities
    - "No secrets" policy (explicitly)
  - Optional: `CODEOWNERS` suggestions keyed to sections.
- **Rationale / pain points addressed**:
  - Single-source-of-truth only works if edits are reliable and socially maintainable.
- **Benefits**:
  - **Business**: Reduced "metadata debt" and fewer costly misconfigurations.
  - **Technical**: Prevents drift and inconsistent semantics across teams.

### 10) Align the manifest to telemetry (so it becomes queryable and comparable)

- **What to change**:
  - Specify a mapping from manifest fields to OTel attributes/events (including GenAI migration where relevant).
  - Emit deltas (change events) rather than only the latest snapshot.
- **Rationale / pain points addressed**:
  - The real leverage comes when manifests are queryable across portfolios (Tempo/Loki/Mimir), not only readable in Git.
- **Benefits**:
  - **Business**: Portfolio-level visibility and governance (risks, objectives, progress) without tool lock-in.
  - **Technical**: Enables dashboards/alerts to use consistent semantics without bespoke integrations.

### Suggested rollout path (minimize disruption)

1. **Immediate (safe)**: Add `kind/apiVersion/metadata` and keep existing fields; add validator warnings (not errors) for missing lifecycle/links.
2. **Short-term**: Add cross-reference validation + status enums; introduce structured metrics shape while supporting legacy strings.
3. **Medium-term**: Add artifact linkage + insight evidence/expiry; wire scanners to populate/refresh insights automatically.
4. **Long-term**: Multi-kind `.contextcore.yaml` (or multi-doc YAML) with formal migrations; emit manifest deltas as telemetry for portfolio queries.

---

## Addendum Part 2: Implementation Patterns & Concrete Examples

This section provides **concrete implementation guidance** building on the systematic improvements above, with code examples aligned to existing ContextCore patterns.

### Implementation Pattern 1: Cross-Reference Validation (Building on Existing Validators)

**Context**: ContextCore already uses `field_validator` patterns (see `src/contextcore/models/core.py` lines 84-88) and has a validator infrastructure (`src/contextcore/contracts/validators.py`).

**Implementation Example**:

```python
# src/contextcore/models/manifest.py (additions)

from pydantic import BaseModel, Field, model_validator
from typing import Set

class ContextManifest(BaseModel):
    # ... existing fields ...
    
    @model_validator(mode='after')
    def validate_cross_references(self):
        """Validate that all referenced IDs exist."""
        errors = []
        
        # Collect all valid IDs
        objective_ids = {obj.id for obj in self.objectives}
        strategy_ids = {strat.id for strat in self.strategies}
        tactic_ids = {
            tactic.id 
            for strat in self.strategies 
            for tactic in strat.tactics
        }
        
        # Validate strategy → objective references
        for strat in self.strategies:
            if hasattr(strat, 'objective_refs'):
                for obj_ref in strat.objective_refs:
                    if obj_ref not in objective_ids:
                        errors.append(
                            f"Strategy {strat.id} references unknown objective: {obj_ref}"
                        )
        
        # Validate risk → strategy/tactic mitigation references
        for risk in self.spec.risks:
            if risk.mitigation:
                # Check if it's a strategy or tactic ID
                if risk.mitigation.startswith('STRAT-'):
                    if risk.mitigation not in strategy_ids:
                        errors.append(
                            f"Risk references unknown strategy: {risk.mitigation}"
                        )
                elif risk.mitigation.startswith('TAC-'):
                    if risk.mitigation not in tactic_ids:
                        errors.append(
                            f"Risk references unknown tactic: {risk.mitigation}"
                        )
        
        if errors:
            raise ValueError("Cross-reference validation failed:\n" + "\n".join(errors))
        
        return self
```

**Pain Point Quantified**: 
- **Current**: Broken references discovered only at runtime or during manual review (estimated 15-30 min per incident)
- **With validation**: Fail-fast at `contextcore manifest validate` (saves 15-30 min × N incidents per quarter)

**Business Benefit**: Prevents "orphaned" risks that reference non-existent strategies, reducing confusion during incident response and planning reviews.

---

### Implementation Pattern 2: Structured Metrics with Existing Validator Infrastructure

**Context**: ContextCore already has `duration_validator`, `percentage_validator`, `throughput_validator` (see `src/contextcore/contracts/validators.py`).

**Implementation Example**:

```python
# src/contextcore/models/manifest.py (additions)

from contextcore.contracts.validators import (
    duration_validator,
    percentage_validator,
    throughput_validator,
)
from pydantic import field_validator

class KeyResult(BaseModel):
    """Structured key result metric (replaces free-form metric/target)."""
    metric_key: str = Field(..., description="Canonical metric key (e.g., 'availability', 'latency.p99')")
    unit: str = Field(..., description="Unit: '%', 'ms', 'rps', 'count', etc.")
    window: Optional[str] = Field(None, description="Time window: '30d', '7d', '1h'")
    baseline: Optional[float] = Field(None, description="Current/baseline value")
    target: float = Field(..., description="Target value")
    data_source: Optional[str] = Field(None, description="PromQL/TraceQL query or Grafana panel ID")
    
    @field_validator('unit')
    def validate_unit(cls, v):
        valid_units = {'%', 'ms', 's', 'rps', 'rpm', 'count', 'ratio'}
        if v not in valid_units:
            raise ValueError(f"Unit must be one of {valid_units}, got {v}")
        return v
    
    @field_validator('target', 'baseline')
    def validate_numeric(cls, v, info):
        if v is None:
            return v
        # Use existing validators based on unit
        unit = info.data.get('unit', '')
        if unit == '%':
            return float(percentage_validator(str(v)))
        elif unit in ('ms', 's'):
            duration_validator(f"{v}{unit}")
        elif unit in ('rps', 'rpm'):
            throughput_validator(f"{v}{unit.replace('ps', 'rps').replace('pm', 'rpm')}")
        return float(v)

class Objective(BaseModel):
    id: str = Field(..., description="Unique objective ID")
    description: str = Field(..., description="The objective statement")
    # Legacy support: keep metric/target for backward compatibility
    metric: Optional[str] = Field(None, description="[DEPRECATED] Use key_results instead")
    target: Optional[str] = Field(None, description="[DEPRECATED] Use key_results instead")
    # New structured approach
    key_results: List[KeyResult] = Field(default_factory=list, description="Structured key results")
```

**Pain Point Quantified**:
- **Current**: Teams interpret "<200ms" differently (P50? P99? Average? Over what window?) → leads to misaligned expectations (estimated 2-4 hours per quarter resolving disputes)
- **With structured metrics**: Unambiguous interpretation, auto-generated dashboard queries, consistent SLO tracking

**Technical Benefit**: Enables `contextcore manifest generate-dashboard` to auto-create Grafana panels from manifest key results, eliminating manual dashboard maintenance.

---

### Implementation Pattern 3: Lifecycle Enums Aligned to Existing Task Status Patterns

**Context**: ContextCore already defines task status enums (see `src/contextcore/contracts/types.py` for `TASK_STATUS_VALUES`).

**Implementation Example**:

```python
# src/contextcore/models/manifest.py (additions)

from enum import Enum
from datetime import datetime
from typing import Optional

class TacticStatus(str, Enum):
    """Execution status for tactics (aligned with task.status semantics)."""
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"

class Tactic(BaseModel):
    id: str = Field(..., description="Unique tactic ID")
    description: str = Field(..., description="What we are doing")
    # Replace free-form status with enum
    status: TacticStatus = Field(TacticStatus.PLANNED, description="Execution status")
    owner: Optional[str] = Field(None, description="Who is responsible")
    
    # Lifecycle fields
    start_date: Optional[datetime] = Field(None, description="When work started")
    due_date: Optional[datetime] = Field(None, description="Target completion date")
    completed_date: Optional[datetime] = Field(None, description="Actual completion date")
    blocked_reason: Optional[str] = Field(None, description="Why blocked (required if status=blocked)")
    progress: Optional[float] = Field(None, ge=0.0, le=100.0, description="Completion percentage")
    
    @model_validator(mode='after')
    def validate_blocked_reason(self):
        """Require blocked_reason when status is BLOCKED."""
        if self.status == TacticStatus.BLOCKED and not self.blocked_reason:
            raise ValueError(f"Tactic {self.id} is blocked but missing blocked_reason")
        return self
    
    @model_validator(mode='after')
    def validate_lifecycle_dates(self):
        """Validate date ordering."""
        if self.completed_date and self.start_date:
            if self.completed_date < self.start_date:
                raise ValueError(f"Tactic {self.id}: completed_date < start_date")
        return self
```

**Pain Point Quantified**:
- **Current**: Status strings like "in progress", "in-progress", "In Progress" treated as different → aggregation fails, dashboards show incorrect counts (estimated 30-60 min per sprint fixing status inconsistencies)
- **With enums**: Consistent status values enable reliable aggregation, cycle time calculation, and stale task detection

**Business Benefit**: Enables automated "stale tactic" alerts (e.g., "Tactic TAC-QUEUE has been IN_PROGRESS for 30+ days"), reducing project drift.

---

### Implementation Pattern 4: Telemetry Emission from Manifest (Following Existing Emitter Patterns)

**Context**: ContextCore already emits manifests as telemetry (see `src/contextcore/knowledge/emitter.py`, `src/contextcore/value/emitter.py` for patterns).

**Implementation Example**:

```python
# src/contextcore/manifest/emitter.py (new file)

from contextcore.agent.insights import InsightEmitter
from contextcore.models.manifest import ContextManifest
from opentelemetry import trace

class ManifestEmitter:
    """Emit Context Manifest changes as OTel spans (following KnowledgeEmitter pattern)."""
    
    def __init__(self, project_id: str, agent_id: str = "manifest-scanner"):
        self.project_id = project_id
        self.agent_id = agent_id
        self.tracer = trace.get_tracer("contextcore.manifest")
    
    def emit_manifest_delta(
        self,
        manifest: ContextManifest,
        previous_manifest: Optional[ContextManifest] = None,
    ) -> str:
        """Emit manifest changes as a span with events for each delta."""
        
        with self.tracer.start_as_current_span(
            "manifest.updated",
            attributes={
                "project.id": self.project_id,
                "manifest.version": manifest.version,
                "manifest.objective_count": len(manifest.objectives),
                "manifest.strategy_count": len(manifest.strategies),
                "manifest.insight_count": len(manifest.insights),
            }
        ) as span:
            
            # Emit objective changes
            if previous_manifest:
                prev_obj_ids = {obj.id for obj in previous_manifest.objectives}
                new_obj_ids = {obj.id for obj in manifest.objectives}
                
                for obj_id in new_obj_ids - prev_obj_ids:
                    span.add_event("objective.added", attributes={
                        "objective.id": obj_id,
                        "objective.description": next(
                            obj.description for obj in manifest.objectives 
                            if obj.id == obj_id
                        ),
                    })
            
            # Emit strategy status changes
            for strat in manifest.strategies:
                for tactic in strat.tactics:
                    if previous_manifest:
                        prev_tactic = self._find_tactic(
                            previous_manifest, 
                            strat.id, 
                            tactic.id
                        )
                        if prev_tactic and prev_tactic.status != tactic.status:
                            span.add_event("tactic.status_changed", attributes={
                                "tactic.id": tactic.id,
                                "tactic.status.old": prev_tactic.status.value,
                                "tactic.status.new": tactic.status.value,
                                "strategy.id": strat.id,
                            })
            
            # Emit insight additions
            if previous_manifest:
                prev_insight_ids = {
                    getattr(ins, 'id', f"{ins.type}:{ins.summary[:20]}")
                    for ins in previous_manifest.insights
                }
                for insight in manifest.insights:
                    insight_id = getattr(insight, 'id', f"{insight.type}:{insight.summary[:20]}")
                    if insight_id not in prev_insight_ids:
                        span.add_event("insight.added", attributes={
                            "insight.type": insight.type,
                            "insight.confidence": insight.confidence,
                            "insight.source": insight.source,
                        })
            
            trace_id = format(span.get_span_context().trace_id, "032x")
        
        return trace_id
```

**Pain Point Quantified**:
- **Current**: Manifest changes are only visible in Git history → no real-time portfolio visibility, no alerting on critical changes (estimated 4-8 hours per quarter manually aggregating status from Git)
- **With telemetry emission**: Portfolio dashboards update in real-time, alerts fire on criticality changes, traceable audit trail in Tempo

**Business Benefit**: Enables "portfolio health" queries like "Which projects have objectives without active strategies?" or "Which tactics have been blocked >7 days?" without manual Git archaeology.

---

### Implementation Pattern 5: ID Pattern Validation (Preventing Ambiguity)

**Implementation Example**:

```python
# src/contextcore/models/manifest.py (additions)

import re
from pydantic import field_validator

# ID patterns aligned to common conventions
OBJECTIVE_ID_PATTERN = re.compile(r'^OBJ-[A-Z0-9-]+$')
STRATEGY_ID_PATTERN = re.compile(r'^STRAT-[A-Z0-9-]+$')
TACTIC_ID_PATTERN = re.compile(r'^TAC-[A-Z0-9-]+$')

class Objective(BaseModel):
    id: str = Field(..., description="Unique objective ID (e.g., OBJ-1)")
    
    @field_validator('id')
    def validate_id_format(cls, v):
        if not OBJECTIVE_ID_PATTERN.match(v):
            raise ValueError(
                f"Objective ID must match pattern OBJ-*, got {v}. "
                f"Examples: OBJ-RELIABILITY, OBJ-1, OBJ-Q4-2024"
            )
        return v

class Strategy(BaseModel):
    id: str = Field(..., description="Strategy ID")
    
    @field_validator('id')
    def validate_id_format(cls, v):
        if not STRATEGY_ID_PATTERN.match(v):
            raise ValueError(
                f"Strategy ID must match pattern STRAT-*, got {v}. "
                f"Examples: STRAT-ASYNC, STRAT-1"
            )
        return v

class Tactic(BaseModel):
    id: str = Field(..., description="Unique tactic ID")
    
    @field_validator('id')
    def validate_id_format(cls, v):
        if not TACTIC_ID_PATTERN.match(v):
            raise ValueError(
                f"Tactic ID must match pattern TAC-*, got {v}. "
                f"Examples: TAC-QUEUE, TAC-1"
            )
        return v
```

**Pain Point Quantified**:
- **Current**: Inconsistent IDs ("obj-1", "OBJ-1", "objective-1") break cross-references and make queries brittle (estimated 1-2 hours per quarter fixing ID mismatches)
- **With pattern validation**: Consistent IDs enable reliable reference resolution and tooling (e.g., `contextcore manifest find-references OBJ-RELIABILITY`)

**Technical Benefit**: Enables ID-based lookups in telemetry queries (e.g., `{span.objective.id = "OBJ-RELIABILITY"}`) without regex ambiguity.

---

### Implementation Pattern 6: Artifact Linkage with URL Validation

**Implementation Example**:

```python
# src/contextcore/models/manifest.py (additions)

from pydantic import HttpUrl, field_validator
from typing import List, Optional

class ArtifactReference(BaseModel):
    """Reference to an external artifact (PR, issue, deployment, etc.)."""
    type: str = Field(..., description="Artifact type: 'issue', 'pr', 'commit', 'deployment', 'dashboard', 'runbook'")
    id: str = Field(..., description="Artifact identifier (e.g., 'PROJ-123', 'pr-456', 'abc123def')")
    url: Optional[HttpUrl] = Field(None, description="Canonical URL to artifact")
    title: Optional[str] = Field(None, description="Human-readable title")
    
    @field_validator('type')
    def validate_type(cls, v):
        valid_types = {'issue', 'pr', 'commit', 'deployment', 'dashboard', 'runbook', 'adr'}
        if v not in valid_types:
            raise ValueError(f"Artifact type must be one of {valid_types}, got {v}")
        return v

class Tactic(BaseModel):
    # ... existing fields ...
    artifacts: List[ArtifactReference] = Field(
        default_factory=list,
        description="Linked artifacts (PRs, issues, deployments)"
    )
```

**Pain Point Quantified**:
- **Current**: "Is TAC-QUEUE actually done?" requires manual checking of Jira/GitHub → 10-15 min per status review × weekly reviews = 40-60 min/month
- **With artifact linkage**: `contextcore manifest status TAC-QUEUE` shows linked PRs/issues automatically, scanners can update status from artifact state

**Business Benefit**: Enables "derived status" where tactic status is computed from artifact state (e.g., "TAC-QUEUE is DONE because linked PR #456 is merged and deployed"), eliminating manual status updates.

---

### Quantified Impact Summary

| Improvement | Time Saved (per quarter) | Risk Reduction | Adoption Friction Reduction |
|-------------|-------------------------|----------------|----------------------------|
| Cross-reference validation | 1-2 hours (prevent broken links) | High (prevents orphaned risks) | Medium (fail-fast feedback) |
| Structured metrics | 2-4 hours (eliminate interpretation disputes) | Medium (consistent SLO tracking) | Low (backward compatible) |
| Lifecycle enums | 2-3 hours (fix status inconsistencies) | Medium (reliable aggregation) | Low (enum migration is straightforward) |
| Telemetry emission | 4-8 hours (eliminate manual Git archaeology) | High (real-time portfolio visibility) | Medium (requires emitter setup) |
| ID pattern validation | 1-2 hours (fix ID mismatches) | Low (prevents ambiguity) | Low (pattern is simple) |
| Artifact linkage | 2-3 hours (automated status derivation) | High (eliminates manual status updates) | Medium (requires scanner integration) |

**Total Estimated Time Savings**: 12-22 hours per quarter per team adopting the manifest pattern.

**ROI Calculation**: If a team spends 2-4 hours/week on status reporting and context gathering, the manifest pattern (with these improvements) reduces that to ~30 min/week → **saves 6-14 hours/month per team** → **18-42 hours/quarter per team**.

---

### Migration Example: Gradual Adoption Path

**Phase 1: Add metadata without breaking changes** (Week 1)

```yaml
# .contextcore.yaml (backward compatible)
apiVersion: contextcore.io/v1alpha1
kind: ContextManifest
metadata:
  name: checkout-service
  lastUpdated: "2026-01-28T10:00:00Z"

version: "1.0"
# ... rest of existing manifest unchanged ...
```

**Phase 2: Add structured fields alongside legacy** (Week 2-4)

```yaml
objectives:
  - id: "OBJ-RELIABILITY"
    description: "Achieve 99.99% availability"
    # Legacy (still supported)
    metric: "availability"
    target: "99.99%"
    # New structured approach (optional)
    key_results:
      - metric_key: "availability"
        unit: "%"
        window: "30d"
        baseline: 99.95
        target: 99.99
        data_source: "promql:avg_over_time(availability[30d])"
```

**Phase 3: Enforce new patterns, deprecate legacy** (Month 2-3)

- Validator warnings for legacy `metric`/`target` fields
- CLI migration tool: `contextcore manifest migrate --to v1.1`

**Phase 4: Remove legacy support** (Month 4+)

- Schema version bump to `v1.1` (legacy fields removed)
- Migration guide with automated tooling

---

*This enhanced addendum provides concrete implementation guidance aligned to existing ContextCore patterns, enabling iterative adoption with minimal disruption.*

---

## Addendum Part 3: Patterns from Lessons Learned

This section incorporates **validated patterns and anti-patterns** from past development work that directly improve Context Manifest reliability, maintainability, and adoption.

### Pattern 1: Changelog Table for Manifest Evolution (from Knowledge Management Lessons)

**Source**: [Knowledge Management Leg 7 #1](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/knowledge_management/lessons/07-maintenance-evolution.md)

**Application to Context Manifest**: Add a changelog section to `.contextcore.yaml` metadata to track evolution:

```yaml
# .contextcore.yaml
apiVersion: contextcore.io/v1alpha1
kind: ContextManifest
metadata:
  name: checkout-service
  changelog:
    - date: "2026-01-28"
      version: "1.1.0"
      actor: "human:neil"
      summary: "Added structured key_results to OBJ-RELIABILITY"
    - date: "2026-01-27"
      version: "1.0.0"
      actor: "agent:claude-code"
      summary: "Initial manifest creation"
```

**Pain Point Addressed**: Without changelog, it's impossible to know when objectives changed, who made strategic pivots, or what version introduced breaking changes. This compounds the "lost context" problem the manifest is meant to solve.

**Business Benefit**: Audit trail for strategic decisions. When asked "why did we change OBJ-RELIABILITY target from 99.9% to 99.99%?", the changelog provides the answer with date and actor.

**Technical Benefit**: Enables migration tooling (`contextcore manifest migrate --from 1.0 --to 1.1`) to apply version-specific transforms based on changelog history.

---

### Pattern 2: Independent Count Verification After Multi-Step Updates (from Knowledge Management Lessons)

**Source**: [Knowledge Management Leg 4 #5](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/knowledge_management/lessons/04-organization-indexing.md)

**Application to Context Manifest**: When updating summary counts (e.g., `total_objectives`, `active_strategies`), always recount from source data:

```python
# src/contextcore/models/manifest.py (additions)

@model_validator(mode='after')
def verify_summary_counts(self):
    """Verify that summary counts match actual data."""
    errors = []
    
    # Recalculate from source
    actual_objectives = len(self.objectives)
    actual_strategies = len(self.strategies)
    actual_tactics = sum(len(s.tactics) for s in self.strategies)
    
    # Compare to metadata if present
    if hasattr(self.metadata, 'summary'):
        if self.metadata.summary.get('total_objectives') != actual_objectives:
            errors.append(
                f"Summary claims {self.metadata.summary['total_objectives']} objectives, "
                f"but found {actual_objectives}"
            )
    
    if errors:
        raise ValueError("Summary count verification failed:\n" + "\n".join(errors))
    
    return self
```

**Pain Point Quantified**: 
- **Current**: Summary counts drift silently when objectives/strategies are added/removed across sessions (estimated 15-30 min per quarter fixing incorrect counts)
- **With verification**: Fail-fast at validation time, prevents misleading summaries

**Business Benefit**: Prevents "we have 7 objectives" when the manifest actually has 6—this kind of drift erodes trust in the manifest as source of truth.

**Technical Benefit**: Enables automated summary generation (`contextcore manifest summarize`) that always produces correct counts.

---

### Pattern 3: Incremental Verification Ladder (from SDK Testing Patterns)

**Source**: [SDK Leg 9 #2](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/lessons/09-testing-patterns.md), [Knowledge Management Leg 7 #2](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/knowledge_management/lessons/07-maintenance-evolution.md)

**Application to Context Manifest**: Validate manifests in stages, catching different error classes at each step:

```python
# src/contextcore/cli/manifest.py (additions)

def validate_manifest_ladder(manifest_path: Path) -> ValidationResult:
    """Validate manifest using incremental verification ladder."""
    errors = []
    warnings = []
    
    # Step 1: Syntax check (YAML parsing)
    try:
        with open(manifest_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return ValidationResult(errors=[f"YAML syntax error: {e}"])
    
    # Step 2: Schema validation (Pydantic)
    try:
        manifest = ContextManifest(**data)
    except ValidationError as e:
        return ValidationResult(errors=[f"Schema validation failed: {e}"])
    
    # Step 3: Cross-reference integrity
    ref_errors = manifest.validate_cross_references()
    if ref_errors:
        errors.extend(ref_errors)
    
    # Step 4: Count verification
    count_errors = manifest.verify_summary_counts()
    if count_errors:
        errors.extend(count_errors)
    
    # Step 5: Business logic validation (optional, warnings)
    if manifest.objectives and not manifest.strategies:
        warnings.append("Manifest has objectives but no strategies—consider adding strategies")
    
    return ValidationResult(errors=errors, warnings=warnings)
```

**Pain Point Quantified**:
- **Current**: All validation errors surface at once, making it hard to prioritize fixes (estimated 5-10 min per validation cycle debugging which errors are blocking)
- **With ladder**: Syntax errors caught first (fastest to fix), then schema, then logic—each step builds on previous success

**Business Benefit**: Faster feedback loop. Developers fix syntax errors immediately, then schema, then logic—rather than fixing everything at once.

**Technical Benefit**: Enables `contextcore manifest validate --stop-on-first-error` for CI pipelines where fast feedback matters.

---

### Pattern 4: Summary+Evidence Pattern for Token Efficiency (from Observability Lessons)

**Source**: [Observability Leg 5 #2](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/observability/lessons/05-tracing.md)

**Application to Context Manifest**: When emitting manifest data as telemetry, store summaries in span attributes and full content as evidence events:

```python
# src/contextcore/manifest/emitter.py (additions)

def emit_manifest_summary(self, manifest: ContextManifest) -> str:
    """Emit manifest summary as span, full content as evidence events."""
    
    with self.tracer.start_as_current_span(
        "manifest.snapshot",
        attributes={
            "manifest.version": manifest.version,
            "manifest.objective_count": len(manifest.objectives),
            "manifest.strategy_count": len(manifest.strategies),
            # Summaries (queryable, low token cost)
            "manifest.objectives_summary": ", ".join(
                obj.id for obj in manifest.objectives[:5]  # First 5 only
            ),
            "manifest.strategies_summary": ", ".join(
                s.id for s in manifest.strategies[:5]
            ),
        }
    ) as span:
        
        # Full content as evidence events (0 tokens in span, loaded on demand)
        for obj in manifest.objectives:
            span.add_event("objective.evidence", attributes={
                "objective.id": obj.id,
                "evidence.ref": f".contextcore.yaml#objectives[{obj.id}]",
                "evidence.tokens": estimate_tokens(obj.model_dump_json()),
            })
        
        trace_id = format(span.get_span_context().trace_id, "032x")
    
    return trace_id
```

**Pain Point Quantified**:
- **Current**: Loading full manifest into agent context costs ~2000-5000 tokens even when only checking "how many objectives?"
- **With summary+evidence**: Query summaries (~200 tokens), load full content only when needed (~87% token reduction)

**Business Benefit**: Enables portfolio-level queries ("which projects have >5 objectives?") without loading every manifest fully. Critical for multi-project governance.

**Technical Benefit**: Aligns with ContextCore's existing telemetry patterns (see `src/contextcore/skill/emitter.py` for similar summary+evidence implementation).

---

### Pattern 5: Disambiguation Layer for Multi-Environment Manifests (from Knowledge Management Lessons)

**Source**: [Knowledge Management Leg 4 #3](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/knowledge_management/lessons/04-organization-indexing.md)

**Application to Context Manifest**: When manifests exist in multiple locations (local `.contextcore.yaml`, GitOps repo, K8s cluster), create a disambiguation layer:

```yaml
# contextcore-manifest-registry.yaml (new file)
apiVersion: contextcore.io/v1alpha1
kind: ManifestRegistry
metadata:
  name: project-manifests

spec:
  canonical_locations:
    - component: "local-development"
      path: ".contextcore.yaml"
      status: ACTIVE
      description: "Source of truth for local development"
    
    - component: "gitops-repo"
      path: "gitops/projects/{project_id}/contextcore.yaml"
      status: ACTIVE
      description: "Synced from local, used for cluster deployment"
    
    - component: "k8s-cluster"
      path: "kubectl get projectcontext {project_id} -o yaml"
      status: DERIVED
      description: "Auto-generated from gitops repo, read-only"

  sync_rules:
    - from: local-development
      to: gitops-repo
      trigger: "git commit"
      transform: "distill_crd"  # Only spec section
    
    - from: gitops-repo
      to: k8s-cluster
      trigger: "ArgoCD sync"
      transform: "none"  # Direct apply
```

**Pain Point Quantified**:
- **Current**: Developers don't know which `.contextcore.yaml` is authoritative when multiple exist (local vs GitOps vs cluster). Leads to "which file do I edit?" confusion (estimated 10-15 min per developer per quarter resolving conflicts)
- **With disambiguation layer**: Single source of truth documented, sync rules explicit, drift detection automated

**Business Benefit**: Prevents "the cluster says X but my local file says Y" confusion. Clear ownership and sync semantics.

**Technical Benefit**: Enables `contextcore manifest sync --check-drift` to detect when local/GitOps/cluster manifests diverge.

---

### Pattern 6: Addendum Pattern for Manifest Version Migrations (from Knowledge Management Lessons)

**Source**: [Knowledge Management Leg 7 #5](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/knowledge_management/lessons/07-maintenance-evolution.md)

**Application to Context Manifest**: When migrating manifests to new schema versions, preserve old versions with addendum headers:

```yaml
# .contextcore.yaml.v1.0 (archived after migration)
> **STATUS: MIGRATED (2026-01-28)**
>
> This manifest was migrated to v1.1. See `.contextcore.yaml` for current version.
>
> **Migration changes:**
> - Replaced `metric`/`target` strings with structured `key_results` array
> - Added `status` enum to tactics (was free-form string)
> - Added `metadata.changelog` section
>
> **Migration command used:**
> `contextcore manifest migrate --from 1.0 --to 1.1 --input .contextcore.yaml.v1.0 --output .contextcore.yaml`
>
> This file is preserved for audit purposes.
>
> ---

version: "1.0"
# ... original content preserved below ...
```

**Pain Point Quantified**:
- **Current**: Migrated manifests lose history—can't answer "what was OBJ-RELIABILITY target before migration?" (estimated 20-30 min per migration session reconstructing history from Git)
- **With addendum**: Full audit trail preserved, migration changes documented, rollback possible

**Business Benefit**: Enables "why did we change this?" queries even after schema migrations. Critical for compliance and governance.

**Technical Benefit**: Enables `contextcore manifest migrate --rollback` to restore previous version if migration causes issues.

---

### Pattern 7: Benefit-Driven Filtering for Manifest Roadmap Items (from Knowledge Management Lessons)

**Source**: [Knowledge Management Leg 4 #4](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/knowledge_management/lessons/04-organization-indexing.md)

**Application to Context Manifest**: When adding "next steps" to manifest, classify as benefit-delivering vs operational task:

```yaml
# .contextcore.yaml (additions)
metadata:
  next_steps:
    # Benefit-delivering (belongs in roadmap)
    - id: "NS-001"
      type: "benefit"
      benefit_id: "visibility.agent_insights"
      description: "Add agent insights dashboard"
      persona: "engineering_manager"
      pain_point: "Can't see what agents learned across sessions"
    
    # Operational task (belongs in .contextcore.yaml only, not roadmap)
    - id: "NS-002"
      type: "operational"
      description: "Update Grafana plugin versions"
      reason: "Maintenance task, no user-facing benefit"
```

**Pain Point Quantified**:
- **Current**: Roadmaps become "task grab-bags" mixing user benefits with internal plumbing (estimated 1-2 hours per quarter cleaning up roadmap priorities)
- **With benefit filtering**: Roadmaps stay focused on user value, operational tasks tracked separately

**Business Benefit**: Clearer prioritization. "What should we build next?" answered by benefit impact, not task completion.

**Technical Benefit**: Enables `contextcore manifest roadmap --benefits-only` to generate user-facing roadmaps without operational noise.

---

### Pattern 8: Path Normalization for Flexible Manifest Discovery (from SDK Lessons)

**Source**: [SDK Leg 9 #4](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/lessons/09-testing-patterns.md), [Knowledge Management Leg 7 #4](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/knowledge_management/lessons/07-maintenance-evolution.md)

**Application to Context Manifest**: When searching for manifests, handle both absolute and relative paths:

```python
# src/contextcore/manifest/loader.py (additions)

def find_manifest(project_root: Path, manifest_name: str = ".contextcore.yaml") -> Optional[Path]:
    """Find manifest with flexible path matching."""
    candidates = [
        project_root / manifest_name,  # Relative to project root
        Path(manifest_name),  # Absolute path if provided
        Path.cwd() / manifest_name,  # Current directory
    ]
    
    for candidate in candidates:
        # Normalize and check
        normalized = candidate.resolve()
        if normalized.exists():
            return normalized
    
    return None

def load_manifest_flexible(path_input: str | Path) -> ContextManifest:
    """Load manifest handling both string paths and Path objects."""
    if isinstance(path_input, str):
        # Handle both absolute and relative
        if path_input.startswith('/') or path_input.startswith('~'):
            path = Path(path_input).expanduser()
        else:
            path = Path.cwd() / path_input
    else:
        path = path_input
    
    return ContextManifest.parse_file(path)
```

**Pain Point Quantified**:
- **Current**: `contextcore manifest load .contextcore.yaml` fails if called from different directory, or if path is absolute vs relative (estimated 5-10 min per developer debugging path issues)
- **With normalization**: Works regardless of current directory or path format

**Business Benefit**: More reliable CLI experience. Developers don't need to `cd` to project root before running commands.

**Technical Benefit**: Enables `contextcore manifest load` to work in CI/CD pipelines where working directory varies.

---

### Pattern 9: Semantic Validation Beyond Syntax (from SDK Multi-Agent Workflows)

**Source**: [SDK Leg 11 #5](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/lessons/11-multi-agent-workflows.md)

**Application to Context Manifest**: Validate that values match their semantic context, not just schema types:

```python
# src/contextcore/models/manifest.py (additions)

@model_validator(mode='after')
def validate_semantic_context(self):
    """Validate that values match their semantic meaning."""
    errors = []
    
    # Validate objective metrics match their domain
    for obj in self.objectives:
        if obj.key_results:
            for kr in obj.key_results:
                # Metric key should match unit
                if kr.metric_key == "availability" and kr.unit != "%":
                    errors.append(
                        f"Objective {obj.id}: availability metric should use '%' unit, got '{kr.unit}'"
                    )
                if kr.metric_key.startswith("latency.") and kr.unit not in ("ms", "s"):
                    errors.append(
                        f"Objective {obj.id}: latency metric should use 'ms' or 's', got '{kr.unit}'"
                    )
    
    # Validate tactic status matches lifecycle dates
    for strat in self.strategies:
        for tactic in strat.tactics:
            if tactic.status == TacticStatus.DONE and not tactic.completed_date:
                errors.append(
                    f"Tactic {tactic.id}: status is DONE but missing completed_date"
                )
            if tactic.status == TacticStatus.BLOCKED and not tactic.blocked_reason:
                errors.append(
                    f"Tactic {tactic.id}: status is BLOCKED but missing blocked_reason"
                )
    
    if errors:
        raise ValueError("Semantic validation failed:\n" + "\n".join(errors))
    
    return self
```

**Pain Point Quantified**:
- **Current**: Schema validation passes (`unit: str` is valid) but values are semantically wrong (`availability` with unit `"rps"`). Discovered only at runtime (estimated 15-30 min per incident debugging why dashboards show wrong units)
- **With semantic validation**: Fail-fast at manifest validation time, prevents runtime confusion

**Business Benefit**: Prevents "the manifest says availability is 1000 rps" confusion. Values match their domain semantics.

**Technical Benefit**: Enables `contextcore manifest validate --semantic` to catch domain-specific errors that Pydantic can't detect.

---

### Pattern 10: Copy-Then-Archive for Manifest Schema Migrations (from Knowledge Management Lessons)

**Source**: [Knowledge Management Leg 1 #11](file:///Users/neilyashinsky/Documents/craft/Lessons_Learned/knowledge_management/lessons/01-document-architecture.md)

**Application to Context Manifest**: When migrating manifests to new schema, copy to new version, validate, then archive old:

```python
# src/contextcore/cli/manifest.py (additions)

def migrate_manifest(
    input_path: Path,
    from_version: str,
    to_version: str,
    output_path: Optional[Path] = None,
) -> MigrationResult:
    """Migrate manifest using copy-then-archive pattern."""
    
    # Phase 1: Load and validate source
    source = ContextManifest.parse_file(input_path)
    if source.version != from_version:
        raise ValueError(f"Source manifest version {source.version} != {from_version}")
    
    # Phase 2: Copy to new version (transform in memory)
    migrated = transform_manifest(source, from_version, to_version)
    
    # Phase 3: Validate migrated version
    migrated.validate()  # Schema + cross-refs + semantic
    
    # Phase 4: Write new version
    output = output_path or input_path.with_suffix(f'.v{to_version}.yaml')
    migrated.write_file(output)
    
    # Phase 5: Archive old version (add addendum header)
    archive_path = input_path.with_suffix(f'.v{from_version}.archived.yaml')
    add_addendum_header(input_path, archive_path, from_version, to_version)
    
    return MigrationResult(
        migrated_path=output,
        archived_path=archive_path,
        changes=compute_changes(source, migrated)
    )
```

**Pain Point Quantified**:
- **Current**: Migrations overwrite files, losing ability to rollback or audit changes (estimated 30-60 min per migration session manually backing up and documenting changes)
- **With copy-then-archive**: Non-destructive migration, full audit trail, rollback possible

**Business Benefit**: Enables "what changed in the migration?" queries and safe rollback if migration causes issues.

**Technical Benefit**: Enables `contextcore manifest migrate --dry-run` to preview changes before applying.

---

### Summary: Lessons Learned Patterns Applied

| Pattern | Source | Pain Point Addressed | Time Saved |
|---------|--------|---------------------|------------|
| Changelog Table | KM Leg 7 #1 | No audit trail for strategic changes | 20-30 min/quarter |
| Independent Count Verification | KM Leg 4 #5 | Summary counts drift silently | 15-30 min/quarter |
| Incremental Verification Ladder | SDK Leg 9 #2 | All errors surface at once | 5-10 min/validation |
| Summary+Evidence Telemetry | O11y Leg 5 #2 | Full manifest loading wastes tokens | 87% token reduction |
| Disambiguation Layer | KM Leg 4 #3 | Multiple manifest locations cause confusion | 10-15 min/dev/quarter |
| Addendum Pattern | KM Leg 7 #5 | Migrated manifests lose history | 20-30 min/migration |
| Benefit-Driven Filtering | KM Leg 4 #4 | Roadmaps become task grab-bags | 1-2 hours/quarter |
| Path Normalization | SDK Leg 9 #4 | Path format issues break CLI | 5-10 min/dev |
| Semantic Validation | SDK Leg 11 #5 | Schema-valid but semantically wrong values | 15-30 min/incident |
| Copy-Then-Archive | KM Leg 1 #11 | Migrations lose audit trail | 30-60 min/migration |

**Total Estimated Time Savings**: 3-6 hours per quarter per team adopting these patterns.

**ROI Calculation**: These patterns prevent the "death by a thousand papercuts" problem—small friction points that compound over time. The manifest pattern already saves 12-22 hours/quarter; adding these patterns saves an additional 3-6 hours by preventing common failure modes.

---

*This addendum incorporates validated patterns from 90+ lessons learned across knowledge management, SDK development, and observability work, ensuring the Context Manifest recommendations are battle-tested and production-ready.*

---

## Addendum Part 4: Synthesis & Future-Proofing (Manifest v2.0 Vision)

This final addendum synthesizes the systematic improvements, implementation patterns, and lessons learned into a unified vision for **Context Manifest v2.0**. It addresses a critical gap identified during review: `agentGuidance` (constraints, focus, questions) is read by agents but currently missing from the core `ProjectContextSpec` schema.

### 1. The Gap: Missing Governance Schema

**Diagnosis**: The runtime `GuidanceReader` reads `spec.agentGuidance` from the Kubernetes CRD, but the `ProjectContextSpec` Pydantic model does not define this field. This means developers using the SDK cannot validate or author guidance natively in the manifest.

**Solution**: Elevate `agentGuidance` to a first-class citizen in the Manifest v2.0 schema.

```python
# src/contextcore/models/manifest_v2.py (Vision)

class AgentGuidanceSpec(BaseModel):
    """Directives for AI agents working on this project."""
    focus: Optional[Focus] = Field(None, description="Current priority focus areas")
    constraints: List[Constraint] = Field(default_factory=list, description="Hard rules agents must follow")
    preferences: List[Preference] = Field(default_factory=list, description="Preferred patterns/styles")
    questions: List[Question] = Field(default_factory=list, description="Open questions for agents to answer")

class ContextManifestV2(BaseModel):
    """
    Manifest v2.0: The Active Control Plane.
    Synthesizes operational spec, strategic context, and agent governance.
    """
    apiVersion: str = "contextcore.io/v1alpha2"
    kind: str = "ContextManifest"
    metadata: ManifestMetadata  # Includes name, changelog, owners, links
    
    # 1. Operational Context (The "What" - Synced to K8s)
    spec: ProjectContextSpec
    
    # 2. Strategic Context (The "Why" - Roadmap & Execution)
    strategy: StrategySpec  # Objectives, KeyResults, Tactics (Structured)
    
    # 3. Governance Context (The "How" - Agent Directives)
    guidance: AgentGuidanceSpec  # Constraints, Focus, Questions (NEW)
    
    # 4. Ephemeral Context (The "Now" - Insights & State)
    insights: List[Insight]  # Derived signals
    state: Optional[ManifestState]  # Last sync time, derived counters
```

### 2. The Shift: From "Passive Config" to "Active Control Plane"

The Manifest v2.0 is not just a config file you read; it is a shared state object that humans and agents collaborate on.

| Aspect | Manifest v1.0 (Current) | Manifest v2.0 (Vision) |
|--------|-------------------------|------------------------|
| **Role** | Static configuration file | Active control plane |
| **Agent Interaction** | Read-only context | Read/Write (Answers questions, updates status) |
| **Guidance** | Implicit / scattered | Explicit `guidance` section |
| **Metrics** | Free-text strings | Structured `KeyResults` with automated queries |
| **Evolution** | Manual edits | Automated evolution via `next_steps` and `insights` |

### 3. Unified "Manifest v2.0" Schema Reference

This consolidated schema integrates all patterns from Addendums 1-3 into a single cohesive structure.

```yaml
# .contextcore.yaml (v2.0 Vision)
apiVersion: contextcore.io/v1alpha2
kind: ContextManifest
metadata:
  name: checkout-service
  owners: 
    - team: "checkout-squad"
      slack: "#checkout-dev"
  changelog:
    - date: "2026-02-05"
      version: "2.0.0"
      summary: "Adopted v2 schema with guidance and structured metrics"

# 1. STRATEGY (Objectives & Execution)
strategy:
  objectives:
    - id: "OBJ-RELIABILITY"
      description: "Achieve 99.99% availability for Black Friday"
      key_results:
        - key: "availability"
          target: 99.99
          unit: "%"
          window: "30d"
  
  tactics:
    - id: "TAC-QUEUE"
      description: "Implement Kafka queue"
      status: "in_progress"
      linked_objectives: ["OBJ-RELIABILITY"]
      artifacts:
        - type: "pr"
          url: "https://github.com/org/repo/pull/123"

# 2. GOVERNANCE (Agent Directives)
guidance:
  focus:
    areas: ["reliability", "performance"]
    reason: "Preparing for Black Friday load test"
    until: "2026-11-01"
  
  constraints:
    - id: "C-NO-AWS-SDK"
      rule: "Do not use boto3 directly; use internal wrapper"
      severity: "blocking"
  
  questions:
    - id: "Q-LATENCY-SPIKE"
      question: "What caused the P99 latency spike yesterday?"
      status: "open"
      priority: "high"

# 3. OPERATIONAL SPEC (K8s CRD Source)
spec:
  project:
    id: "checkout-service"
  business:
    criticality: "critical"
  observability:
    traceSampling: 1.0

# 4. INSIGHTS (Automated Feedback Loop)
insights:
  - type: "risk"
    summary: "Constraint C-NO-AWS-SDK violated in PR #123"
    confidence: 1.0
    source: "governance-scanner"
```

### 4. Implementation Roadmap for v2.0

1.  **Update Core Models**: Modify `ProjectContextSpec` or create a wrapper `ContextManifest` model that includes `AgentGuidanceSpec`.
2.  **Update GuidanceReader**: Deprecate reading from `spec.agentGuidance` (K8s specific) in favor of a unified reader that can parse local `.contextcore.yaml` v2 files.
3.  **Agent Write-Back**: Implement `GuidanceResponder` capability to update the local `.contextcore.yaml` file (e.g., marking questions as answered), closing the loop between human intent and agent action.
4.  **Migration Tooling**: Ship `contextcore manifest upgrade` to auto-convert v1 manifests to v2 structure, moving `objectives` to `strategy.objectives` and preserving history.

### Conclusion

The Context Manifest pattern transforms project metadata from "documentation" into "infrastructure." By adopting the **v2.0 Active Control Plane** model, you enable a new class of AI-assisted engineering where agents don't just write code—they understand strategy, respect governance, and actively participate in project management.

---

## Addendum Part 5: Post‑v1.1 Systematic Improvements

These are **next-step improvements** based on the current v1.1 implementation in `src/contextcore/models/manifest.py` and `examples/context_manifest_example.yaml`. They are intentionally scoped to avoid the rejection principles in Appendix B (no premature abstractions, no redundant drift-prone fields, adoption-first).

### 1) Version consistency policy: align `version` with `metadata.changelog`

- **What to improve**: Define and enforce a simple rule such as “`manifest.version` must equal the latest `metadata.changelog[*].version` major.minor (or full SemVer).”
- **Rationale / pain points addressed**:
  - Right now the example uses `version: "1.1"` while the changelog uses `1.1.0`. This is easy for humans to misread and hard for tooling to reason about.
- **Benefits**:
  - **Business**: Reduces “which schema are we on?” confusion during audits and cross-team handoffs.
  - **Technical**: Enables reliable migrations and validators that can select rules based on a single version source.

### 2) Backward-compatible YAML loader for v1.0 manifests (accept old shape safely)

- **What to improve**: Add a loader that can parse v1.0-style manifests that lack `apiVersion/kind/metadata`, and **upgrade in-memory** to v1.1 defaults.
- **Rationale / pain points addressed**:
  - Adoption friction shows up most often at the first upgrade. Teams with existing `.contextcore.yaml` v1.0 files shouldn’t need manual edits to “get back to green.”
- **Benefits**:
  - **Business**: Faster rollout across teams (less “migration tax”).
  - **Technical**: One validator path; fewer special cases in calling code.

### 3) Tighten example validity via CI (schema test for `examples/context_manifest_example.yaml`)

- **What to improve**: Add a tiny test (or CI step) that loads the example YAML and validates it against `ContextManifest`.
- **Rationale / pain points addressed**:
  - Example files drift over time and silently become misleading; catching it early prevents broken copy/paste onboarding.
- **Benefits**:
  - **Business**: New adopters get a working template the first time.
  - **Technical**: Prevents regressions when schema changes (fast feedback loop).

### 4) Make `distill_crd()` namespace configurable (without adding schema bloat)

- **What to improve**: Change `distill_crd()` to accept `namespace` as a parameter (and optionally labels/annotations), instead of hardcoding `"default"`.
- **Rationale / pain points addressed**:
  - Hardcoding is a hidden footgun for GitOps and multi-namespace clusters.
- **Benefits**:
  - **Business**: Fewer deployment mistakes when rolling out to production namespaces.
  - **Technical**: Cleaner GitOps integration; avoids patching derived YAML post-generation.

### 5) Reduce enum duplication: prefer canonical `Priority` for insight severity (or map explicitly)

- **What to improve**: Either reuse `contextcore.contracts.types.Priority` directly for `Insight.severity`, or add an explicit mapping and remove unused imports.
- **Rationale / pain points addressed**:
  - Duplicate “same meaning, different enum” structures create long-term drift risk.
- **Benefits**:
  - **Business**: Consistent severity language across dashboards, alerts, and manifests.
  - **Technical**: One canonical vocabulary; less conversion glue code.

### 6) Add `targetOperator` (or “direction”) to `KeyResult` to remove ambiguity

- **What to improve**: Add a field like `operator: gte|lte` (or `targetOperator`) to `KeyResult`.
- **Rationale / pain points addressed**:
  - Availability targets are “≥”, latency targets are “≤”. A numeric `target` alone is not enough to auto-generate alerts or evaluate success consistently.
- **Benefits**:
  - **Business**: Clearer OKR interpretation (“did we hit it?” becomes deterministic).
  - **Technical**: Enables automated dashboards/alerts without metric-specific heuristics.

### 7) Decide on one casing convention for YAML examples (and document it)

- **What to improve**: Codify whether YAML should prefer camelCase (K8s-style: `apiVersion`, `keyResults`) or snake_case (Python-friendly), then keep examples + docs consistent.
- **Rationale / pain points addressed**:
  - Mixed casing is a slow, recurring papercut for humans and tools.
- **Benefits**:
  - **Business**: Easier adoption and training (“write it like this everywhere”).
  - **Technical**: Fewer alias corner cases and fewer formatter/validator surprises.

---

## Appendix A: Changes Applied from Recommendations

This section documents which recommendations from the addendums were implemented in the codebase.

### Applied to `src/contextcore/models/manifest.py` (Schema v1.1)

| Recommendation | Section | Status | Notes |
|----------------|---------|--------|-------|
| Add `apiVersion`, `kind`, `metadata` | Addendum 1, Item 1 | ✅ Applied | Added K8s-like structure with `ManifestMetadata` |
| ID pattern validation (OBJ-, STRAT-, TAC-) | Addendum 1, Item 2 | ✅ Applied | Added regex patterns and field validators |
| Cross-reference validation | Addendum 1, Item 2 | ✅ Applied | `model_validator` checks objective/strategy/tactic refs |
| `TacticStatus` enum | Addendum 1, Item 3 | ✅ Applied | Aligned with `TaskStatus` from contracts/types.py |
| Lifecycle fields (dates, progress, blocked_reason) | Addendum 1, Item 3 | ✅ Applied | Added to `Tactic` model |
| Structured `KeyResult` model | Addendum 1, Item 4 | ✅ Applied | Replaces free-form metric/target with typed fields |
| Legacy metric/target support | Addendum 1, Item 4 | ✅ Applied | Kept for backward compatibility with deprecation note |
| Enhanced `Insight` (severity, expiry, evidence) | Addendum 1, Item 5 | ✅ Applied | Added `InsightSeverity` enum and evidence fields |
| Structured `Owner` model | Addendum 1, Item 6 | ✅ Applied | Team, slack, email, oncall fields |
| `ArtifactReference` model | Addendum 1, Item 7 | ✅ Applied | For linking PRs, issues, deployments to tactics |
| Changelog in metadata | Addendum 3, Pattern 1 | ✅ Applied | `ChangelogEntry` model in `ManifestMetadata` |
| Semantic validation (metric-unit consistency) | Addendum 3, Pattern 9 | ✅ Applied | `KeyResult.validate_metric_unit_consistency()` |
| `distill_crd()` helper method | Addendum 1, Item 8 | ✅ Applied | Extracts only `spec` for K8s CRD |
| Backward-compatible factory function | Migration | ✅ Applied | `create_manifest_v1()` for simple use cases |
| Backward-compatible YAML loader | Addendum 5, Item 2 | ✅ Applied | `load_context_manifest()` with legacy upgrade |
| `distill_crd()` namespace configurable | Addendum 5, Item 4 | ✅ Applied | Added `namespace` and `name` parameters |
| `TargetOperator` enum for `KeyResult` | Addendum 5, Item 6 | ✅ Applied | `gte`/`lte`/`eq` with auto-inference |
| `KeyResult.get_operator()` method | Addendum 5, Item 6 | ✅ Applied | Infers operator from metric_key |
| `KeyResult.evaluate()` method | Addendum 5, Item 6 | ✅ Applied | Evaluates actual vs target |

### Applied to `examples/context_manifest_example.yaml`

| Change | Status | Notes |
|--------|--------|-------|
| Added `apiVersion`, `kind`, `metadata` | ✅ Applied | Full K8s-like structure |
| Added structured `keyResults` to objectives | ✅ Applied | With data sources |
| Added `objectiveRefs` to strategy | ✅ Applied | Cross-references validated |
| Added lifecycle fields to tactics | ✅ Applied | startDate, dueDate, progress |
| Added artifacts to tactics | ✅ Applied | PR and issue links |
| Enhanced insights with severity, evidence | ✅ Applied | Full v1.1 insight structure |
| Added changelog in metadata | ✅ Applied | Version history |
| Added structured owners | ✅ Applied | Team, slack, email |
| Added `targetOperator` to key results | ✅ Applied | `gte` for availability, `lte` for latency |

### Applied to `tests/test_manifest.py`

| Change | Status | Notes |
|--------|--------|-------|
| `test_example_manifest_comprehensive_validation` | ✅ Applied | Validates all v1.1 sections (Addendum 5, Item 3) |
| `test_keyresult_explicit_operator` | ✅ Applied | Tests explicit operator usage |
| `test_keyresult_infers_gte_for_availability` | ✅ Applied | Tests gte inference |
| `test_keyresult_infers_lte_for_latency` | ✅ Applied | Tests lte inference |
| `test_keyresult_infers_lte_for_error_metrics` | ✅ Applied | Tests lte for error metrics |
| `test_keyresult_default_infers_gte` | ✅ Applied | Tests default gte inference |

---

## Appendix B: Rejected Suggestions and Rationale

This section documents suggestions that were **not** implemented and explains the reasoning to prevent similar suggestions in the future.

### 1. Multi-Document YAML / Multi-Kind `.contextcore.yaml`

**Suggestion (Addendum 1, Item 1)**: Use multi-document YAML (`---` separators) or multiple `kind` values within a single file for namespaced modules.

**Rejection Rationale**:
- **Complexity vs. Value**: Multi-document YAML adds parsing complexity without clear value for most use cases.
- **Tooling Fragmentation**: Most YAML editors and linters don't handle multi-document well.
- **Simpler Alternative**: The single-document approach with clear sections (`spec`, `objectives`, `strategies`, `insights`) achieves the same separation without the overhead.

**Future Consideration**: May revisit for v2.0 if users need truly separate `kind`s (e.g., `ContextManifest` + `ManifestRegistry`).

---

### 2. `tactic.strategy` Backref Field

**Suggestion (Addendum 1, Item 2)**: Add `tactic.strategy: STRAT-...` backref for flat tactic lists.

**Rejection Rationale**:
- **Redundancy**: Tactics are nested under strategies, so the relationship is implicit.
- **Maintenance Burden**: Backref must be kept in sync, adding validation complexity.
- **Current Design**: `Strategy.tactics` already establishes the relationship; adding backref creates dual sources of truth.

**Future Consideration**: If we move to flat tactic lists (outside strategies), backref would be necessary.

---

### 3. `stakeholders` as Separate Typed Contacts

**Suggestion (Addendum 1, Item 6)**: Add `stakeholders: List[Contact]` separate from `owners`.

**Rejection Rationale**:
- **Scope Creep**: Stakeholders are typically managed in PM tools (Jira, Confluence), not in the manifest.
- **Simplicity**: The `metadata.owners` array is sufficient for operational routing.
- **Duplicate Data**: Stakeholder information would drift between manifest and PM tools.

**Future Consideration**: May add if PM tool integration requires stakeholder mapping.

---

### 4. `CODEOWNERS` Suggestions Keyed to Sections

**Suggestion (Addendum 1, Item 9)**: Generate `CODEOWNERS` entries per manifest section.

**Rejection Rationale**:
- **GitHub-Specific**: `CODEOWNERS` is GitHub-specific; doesn't apply to GitLab, Bitbucket, etc.
- **Out of Scope**: Ownership is better handled in `metadata.owners`; `CODEOWNERS` is a repo-level concern.
- **Complexity**: Section-level ownership adds granularity most teams don't need.

**Future Consideration**: Could be a separate tooling feature (`contextcore codeowners generate`).

---

### 5. Manifest Registry (Multi-Location Disambiguation)

**Suggestion (Addendum 3, Pattern 5)**: Create a `ManifestRegistry` kind to track canonical locations.

**Rejection Rationale**:
- **Premature Abstraction**: Most projects have one manifest location; multi-location is an edge case.
- **Complexity**: Registry introduces another file to maintain and sync.
- **GitOps Pattern**: In GitOps, the manifest source is always the Git repo; cluster state is derived.

**Future Consideration**: May implement if multi-environment manifest management becomes common.

---

### 6. `next_steps` in Manifest Metadata

**Suggestion (Addendum 3, Pattern 7)**: Add `metadata.next_steps` with benefit-driven filtering.

**Rejection Rationale**:
- **Roadmap Belongs Elsewhere**: Next steps are better tracked in PM tools or separate roadmap files.
- **Scope**: The manifest is for current state, not future planning.
- **Maintenance**: Next steps go stale quickly; embedding in manifest adds noise.

**Future Consideration**: May add a `roadmap` section in v2.0 if tightly coupled to strategic context.

---

### 7. Summary Counts in Metadata

**Suggestion (Addendum 3, Pattern 2)**: Add `metadata.summary.total_objectives`, etc.

**Rejection Rationale**:
- **Derived, Not Stored**: Counts can be computed from the manifest; storing them creates drift risk.
- **Complexity**: Requires validation to keep counts in sync.
- **API Pattern**: Better to have a `manifest.summarize()` method than store counts.

**Future Consideration**: Could add as a computed property (not stored field).

---

### 8. Strict `DONE` Requires `completed_date` Validation

**Suggestion (Addendum 2, Pattern 3)**: Require `completed_date` when `status=done`.

**Rejection Rationale**:
- **Adoption Friction**: Many teams don't track completion dates; strict validation would block adoption.
- **Soft Warning**: The current implementation allows DONE without `completed_date` to reduce friction.

**Future Consideration**: Make configurable via `contextcore manifest validate --strict`.

---

### 9. Telemetry Emission from Manifest (ManifestEmitter)

**Suggestion (Addendum 2, Pattern 4)**: Add `ManifestEmitter` to emit changes as OTel spans.

**Rejection Rationale**:
- **Separate Concern**: Telemetry emission is a feature, not a schema change.
- **Not Yet Prioritized**: The core schema improvements were prioritized over emitter.

**Future Implementation**: Will be implemented as a separate module (`src/contextcore/manifest/emitter.py`), not in this schema update.

---

### 10. `AgentGuidanceSpec` in v1.1

**Suggestion (Addendum 4)**: Add `guidance` section with constraints, focus, questions.

**Rejection Rationale**:
- **v2.0 Feature**: This is a significant addition better suited for the v2.0 schema.
- **Scope**: v1.1 focused on making existing features more robust (validation, structure).
- **Stability**: Adding guidance changes the manifest's role from "config" to "control plane"; needs careful design.

**Future Implementation**: Planned for Context Manifest v2.0 (Active Control Plane model).

---

### 11. Reduce Enum Duplication (`InsightSeverity` vs `Priority`)

**Suggestion (Addendum 5, Item 5)**: Reuse `contextcore.contracts.types.Priority` directly for `Insight.severity`, or add an explicit mapping to eliminate duplicate enums.

**Rejection Rationale**:
- **Different Semantic Purposes**: `InsightSeverity` includes `INFO` level for informational insights (e.g., "FYI: new dependency detected"). `Priority` is for task/alert prioritization and doesn't have an `INFO` level.
- **Domain-Specific Vocabulary**: Insights describe observations with varying importance (critical risk vs. informational pattern). Tasks/alerts have urgency-based priority (P1 vs P4).
- **Merge Would Lose Expressiveness**: Removing `INFO` from insights would force all observations to have "priority-like" semantics, which is conceptually wrong.

**Future Consideration**: Could add explicit mapping methods (`InsightSeverity.to_priority()`) if cross-domain queries become common, but keeping separate enums is the correct design.

---

### 12. Version Consistency Policy (Documentation Only)

**Suggestion (Addendum 5, Item 1)**: Enforce that `manifest.version` must equal the latest `metadata.changelog[*].version`.

**Rejection Rationale**:
- **Low Impact**: This is a documentation/convention issue, not a code change.
- **Adoption Friction**: Strict validation would reject valid manifests where changelog uses different versioning.
- **Human Preference**: Some teams prefer `version: "1.1"` while changelog uses `1.1.0` for more detail.

**Resolution**: Documented as a **recommended convention** rather than enforced validation. Teams can opt into stricter validation via `contextcore manifest validate --strict`.

---

### 13. Casing Convention (Documentation Only)

**Suggestion (Addendum 5, Item 7)**: Codify whether YAML should prefer camelCase or snake_case.

**Rejection Rationale**:
- **Already Follows K8s Convention**: The manifest already uses camelCase for YAML fields (`apiVersion`, `keyResults`, `metricKey`) with `alias` for Python compatibility.
- **Documentation, Not Code**: This is a style guide issue, not a schema change.

**Resolution**: The existing pattern (camelCase in YAML, snake_case in Python with `alias`) is the established convention and is already consistently applied.

---

### Summary: Rejection Principles

1. **Avoid Premature Abstraction**: Don't add complexity for edge cases.
2. **Single Source of Truth**: Don't create redundant fields that drift.
3. **Adoption First**: Don't add strict validation that blocks adoption.
4. **Scope Discipline**: Keep the manifest focused on its core purpose.
5. **Version Appropriately**: Save breaking/significant changes for major versions.
6. **Preserve Domain Semantics**: Don't merge enums with different semantic purposes.
7. **Prefer Documentation Over Enforcement**: Style conventions should be documented, not forcibly validated.

---

*Generated by `capability-value-promoter` skill — bridging technical capabilities to human value.*
