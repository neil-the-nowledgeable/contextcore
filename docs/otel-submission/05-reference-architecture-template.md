# OTel Reference Architecture Template

> **Target Repository**: `open-telemetry/sig-end-user`
> **Related Issue**: [#236 - Draft reference architecture template](https://github.com/open-telemetry/sig-end-user/issues/236)
> **Complements**: [#235 - Blueprint template](https://github.com/open-telemetry/sig-end-user/issues/235) (strategic guidance)
> **Based on**: [ContextCore reference architecture](https://github.com/neil-the-nowledgable/contextcore/blob/main/docs/blueprint-reference-architecture.md)

---

## How This Template Relates to Blueprints

Blueprints (issue #235) provide **environment-specific strategic guidance**: Diagnosis, Guiding Policies, and Coherent Actions following the Rumelt framework.

Reference architectures (this template, issue #236) provide **real-world case studies**: how a specific organization adopted these patterns, what worked, what didn't, and what they'd do differently.

```
Blueprint (strategic)          Reference Architecture (concrete)
─────────────────────          ──────────────────────────────────
"Here's what to do"     →      "Here's how we did it"
Environment-agnostic           Environment-specific
Challenges + policies          Implementation + results
Written by SIG                 Written by end-users
```

A blueprint may reference multiple reference architectures as evidence. A reference architecture should map back to the blueprint it implements.

---

## Template

Below is the generalized template. Sections marked **(required)** must be included. Sections marked **(recommended)** strengthen the document but may be omitted if not applicable.

---

### Title

```
Reference Architecture: [Domain/Problem Area] at [Organization]
```

*Example*: "Reference Architecture: Project Management Observability at ContextCore"

---

### Metadata (required)

| Field | Value |
|-------|-------|
| **Organization** | [Name or anonymized identifier] |
| **Industry** | [e.g., fintech, healthcare, SaaS, e-commerce] |
| **Scale** | [e.g., 50 engineers, 200 services, 10K spans/sec] |
| **Environment** | [e.g., Kubernetes, bare metal, hybrid cloud] |
| **OTel Components Used** | [e.g., SDK, Collector, Operator] |
| **Backend** | [e.g., Grafana stack, Datadog, Elastic, Splunk] |
| **Blueprint Implemented** | [Link to related blueprint, if applicable] |
| **Status** | [Production / Pilot / Proof of Concept] |

---

### 1. Summary (required)

A 2-3 paragraph overview covering:

- **Who**: Target audience personas and their pain points
- **What**: The OTel patterns adopted
- **Why**: The business or technical problem that motivated adoption
- **Outcome**: High-level result (quantified if possible)

#### Target Audience

> *A table mapping personas to their specific pain points and the value this architecture delivers to each.*

| Persona | Pain Point | Value Delivered |
|---------|------------|-----------------|
| [Role 1] | "[Pain in their words]" | [Specific benefit] |
| [Role 2] | "[Pain in their words]" | [Specific benefit] |
| [Role 3] | "[Pain in their words]" | [Specific benefit] |

#### Environment Scope

> *Describe the technical environment where this architecture applies.*

- Infrastructure: [Kubernetes, VMs, serverless, etc.]
- Telemetry backends: [Tempo, Jaeger, Prometheus, etc.]
- Integration points: [CI/CD, issue trackers, alerting, etc.]

---

### 2. Challenges Addressed (required)

> *For each challenge, describe the observable symptoms, their business/technical impact, and the root cause. This structure enables readers to recognize whether they face the same problems.*

#### Challenge 1: [Name]

**Symptoms**:
- [Observable problem 1]
- [Observable problem 2]

**Impact**:
- [Quantified cost or consequence]
- [Business or team effect]

**Root Cause**: [Why this challenge exists in your environment]

#### Challenge 2: [Name]

*[Repeat structure]*

---

### 3. Architecture (required)

> *Describe the OTel architecture adopted. Include diagrams where possible.*

#### Architecture Diagram

```
[ASCII or linked diagram showing data flow]

Example structure:
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│  Source   │────▶│  OTel Layer  │────▶│   Backend    │
│ (app/CI) │     │ (SDK/Coll.)  │     │ (storage/UI) │
└──────────┘     └──────────────┘     └──────────────┘
```

#### Components

| Component | Role | OTel Integration |
|-----------|------|-----------------|
| [Component 1] | [What it does] | [How OTel is used] |
| [Component 2] | [What it does] | [How OTel is used] |

#### Data Flow

> *Describe how telemetry flows through the system, including signal types (traces, metrics, logs), protocols (OTLP, Prometheus), and any transformations.*

1. [Step 1: Signal generation]
2. [Step 2: Collection/processing]
3. [Step 3: Export/storage]
4. [Step 4: Querying/visualization]

---

### 4. Semantic Conventions Used (required)

> *List the semantic conventions applied, including any custom attributes. This helps the SemConv SIG identify patterns that may warrant standardization.*

#### Standard OTel Conventions

| Attribute | Usage | Reference |
|-----------|-------|-----------|
| [e.g., `service.name`] | [How you use it] | [SemConv link] |

#### Custom/Extended Conventions

> *Attributes specific to your domain that may be candidates for future standardization.*

| Namespace | Attribute | Type | Description |
|-----------|-----------|------|-------------|
| [e.g., `project.*`] | `project.id` | string | [What it represents] |

---

### 5. Implementation (required)

> *Concrete steps taken to implement the architecture. Each action should reference which challenge it addresses.*

#### Action 1: [Name]

**Challenges Addressed**: [1, 2]

[Description of what was implemented, with code examples or configuration snippets]

```yaml
# Example configuration or code
```

#### Action 2: [Name]

*[Repeat structure]*

---

### 6. Dashboards and Queries (recommended)

> *Show how the telemetry is consumed. Include example queries and dashboard descriptions.*

#### Key Queries

| Purpose | Query Language | Query |
|---------|---------------|-------|
| [What it answers] | [TraceQL/PromQL/LogQL] | `[query]` |

#### Dashboards

| Dashboard | Audience | Key Panels |
|-----------|----------|------------|
| [Name] | [Who uses it] | [What it shows] |

---

### 7. Results (required)

> *Quantified outcomes from the implementation. This is what makes reference architectures valuable - evidence that the patterns work.*

#### Quantitative Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| [e.g., Time spent on X] | [Value] | [Value] | [% or absolute] |
| [e.g., Mean time to Y] | [Value] | [Value] | [% or absolute] |

#### Qualitative Results

- [Team feedback or behavioral change]
- [Process improvement observed]
- [Unexpected benefit discovered]

---

### 8. Lessons Learned (recommended)

> *What you'd do differently and what surprised you. Helps future adopters avoid pitfalls.*

#### What Worked Well

- [Pattern or decision that paid off]

#### What We'd Do Differently

- [Approach that was suboptimal and the better alternative]

#### Surprises

- [Unexpected outcome, positive or negative]

---

### 9. Value by Role (recommended)

> *Maps the architecture's value to specific personas. Useful for organizations evaluating adoption.*

| Role | Start Here | Quick Win | Full Value |
|------|------------|-----------|------------|
| [Role 1] | [First step] | [Early result] | [Mature state] |
| [Role 2] | [First step] | [Early result] | [Mature state] |

---

### 10. Try It Yourself (recommended)

> *A self-contained guide for reproducing the reference architecture locally. Lowers the barrier for others to validate the patterns.*

#### Prerequisites

```
- [Required tool 1]
- [Required tool 2]
```

#### Quick Start

```bash
# Step-by-step commands to get a working example
```

#### Explore

- [Key query or dashboard to look at first]
- [Second thing to explore]

#### Cleanup

```bash
# Commands to tear down the example environment
```

---

## Template Rationale

### Why These Sections?

| Section | Purpose | Maps to Blueprint |
|---------|---------|-------------------|
| **Summary** | Quickly assess relevance | - |
| **Challenges** | Pattern-match to reader's problems | Diagnosis |
| **Architecture** | Understand the technical approach | - |
| **Semantic Conventions** | Feed SemConv standardization | - |
| **Implementation** | Reproduce the solution | Coherent Actions |
| **Dashboards/Queries** | See how telemetry is consumed | - |
| **Results** | Evidence that it works | - |
| **Lessons Learned** | Avoid pitfalls | - |
| **Value by Role** | Build internal buy-in | - |
| **Try It Yourself** | Lower adoption barrier | - |

### Traceability Pattern

The template encourages **back-references** between sections:

```
Challenge 1 ──referenced by──▶ Action 2, Action 4
Challenge 2 ──referenced by──▶ Action 1, Action 3
```

This lets readers trace from a problem they recognize to the specific implementation that addresses it, without reading the entire document.

### Consistency with Blueprint Template

This template complements the blueprint template (issue #235) by:

1. **Sharing vocabulary**: Challenges here map to Diagnosis in blueprints
2. **Providing evidence**: Results section validates blueprint Guiding Policies
3. **Grounding abstraction**: Implementation section concretizes blueprint Actions
4. **Enabling discovery**: Semantic Conventions section surfaces standardization candidates

---

## Existing Reference Architecture

The ContextCore project has a reference architecture following this template structure:
[blueprint-reference-architecture.md](https://github.com/neil-the-nowledgable/contextcore/blob/main/docs/blueprint-reference-architecture.md)
