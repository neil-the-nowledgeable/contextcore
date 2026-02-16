# Context Correctness Extensions: Lessons from Agent Framework Comparison

**Status:** Active design document
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.88
**Prerequisite:** [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)

> *"Every framework we studied handles context flow. None of them treat context
> correctness as a first-class, verifiable property. The gap is not in the
> mechanisms — it's in the contracts."*

---

## Purpose

Extend the Context Correctness by Construction framework with five new
cross-cutting concerns and four enhanced theoretical concerns, all discovered
by systematic comparison of ContextCore's contract model against nine agent/LLM
frameworks: LangGraph, AutoGen, CrewAI, Semantic Kernel, LlamaIndex, Haystack,
OpenAI Agents SDK, DSPy, and Guidance/Outlines/Instructor.

The parent document ([CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md))
identifies eight concerns that silently degrade in distributed systems and
proposes a 7-layer defense-in-depth architecture. This document extends that
analysis with concerns that emerge specifically when agent/LLM pipelines
replace traditional service architectures.

## Audience

- System architects designing agent pipelines with context integrity requirements
- Contributors planning new contract layers beyond the current seven
- Teams evaluating ContextCore as a governance layer over LangGraph, AutoGen,
  CrewAI, or similar frameworks

---

## Method: How These Extensions Were Discovered

Between February 13-14, 2026, we conducted a systematic comparison of
ContextCore against nine frameworks, producing fifteen documents in
`docs/framework-comparisons/`. For each framework, we identified:

1. **What it does well** that ContextCore does not address
2. **What it does poorly** that ContextCore's contract model could improve
3. **What it does implicitly** that could be made explicit via contracts

The comparison documents focused on governance positioning — what ContextCore
adds *on top of* each framework without duplicating orchestration. This document
inverts the question: **what do those frameworks reveal about gaps in our
contract model?**

### Source Documents

| Document | Frameworks Covered |
|----------|-------------------|
| `FRAMEWORK_COMPARISON_LANGGRAPH_AUTOGEN_CREWAI.md` | LangGraph, AutoGen, CrewAI |
| `FRAMEWORK_COMPARISON_SK_LLAMA_HAYSTACK.md` | Semantic Kernel, LlamaIndex, Haystack |
| `FRAMEWORK_COMPARISON_NOTES.md` | OpenAI Agents SDK, DSPy, Guidance/Outlines/Instructor |
| `RUNTIME_SELECTION_MATRIX_FOR_CONTEXTCORE_USERS_PLATFORM_CHOICES.md` | All nine — ContextCore user lens |
| `RUNTIME_SELECTION_MATRIX_FOR_PLATFORM_USERS_CONTEXTCORE_BENEFITS.md` | All nine — platform user lens |
| Nine individual `*_VS_CONTEXTCORE.md` files | One-to-one deep comparisons |

---

## Part 1: Enhancements to Existing Theoretical Concerns

The parent document identifies Concerns 4-7 as "design only." The framework
comparison provides concrete implementation patterns for each.

### Concern 4: Causal Ordering — Enhanced with Temporal Staleness

**Parent document summary:** Event A must be processed before Event B, but
under load, B arrives first. Systems that depend on ordering produce incorrect
results silently.

**What the frameworks reveal:**

LangGraph's checkpoint/resume model introduces a *temporal dimension* to causal
ordering. When a workflow checkpoints at time T and resumes at time T+Delta, the
context snapshot from T may be stale. External data sources may have updated.
Model versions may have rotated. Configuration may have changed. The checkpoint
preserves context integrity *at T*, but resume at T+Delta may violate it.

AutoGen's conversational turn model shows that causal ordering is not just about
events — it's about **conversation coherence**. Turn N's output is input to turn
N+1. When agents negotiate asynchronously or when conversation history is
truncated, turns can effectively arrive "out of order" from the perspective of
context dependence.

**Enhancement:** `OrderingConstraintSpec` should include a `staleness_budget` per
field, declaring how long a context value remains valid after stamping:

```yaml
ordering_constraints:
  - constraint_id: "model_version_freshness"
    field: "model.version"
    staleness_budget_seconds: 86400  # 24 hours
    on_stale: WARNING
    description: "Model version must be re-validated if checkpoint pause exceeds 24h"

  - constraint_id: "retrieval_index_freshness"
    field: "rag.index_snapshot"
    staleness_budget_seconds: 3600  # 1 hour
    on_stale: BLOCKING
    description: "Index snapshot is stale after 1h; re-retrieval required"
```

The `BoundaryValidator` would check `current_time - field_provenance.set_at`
against the staleness budget at resume boundaries. This composes with Layer 1:
at resume time, re-run the entry validation of the next phase because context
that was valid at checkpoint time may no longer be valid.

**Framework evidence:**
- LangGraph: Checkpoint recovery creates temporal gaps where context staleness is unchecked
- AutoGen: Asynchronous turn delivery creates ordering ambiguity that degrades conversation quality

### Concern 5: Capability/Permission Propagation — Enhanced with Delegation Authority

**Parent document summary:** User has permission P in service A. Service A calls
service B on behalf of the user. Does B know about P?

**What the frameworks reveal:**

Three frameworks independently solve fragments of this problem:

- **AutoGen** uses role-based delegation. An "assistant" agent can delegate to a
  "code_executor" agent. But the delegation is implicit — there's no contract
  declaring which roles may delegate to which other roles, and no audit trail
  when delegation is rejected.

- **CrewAI** uses guardrails that check whether an agent is authorized for a task
  before execution. But guardrail failures are internal — they don't produce
  queryable evidence, and there's no standardized taxonomy of rejection reasons.

- **Semantic Kernel** maintains a capability registry with semantic descriptions.
  But the registry is runtime-focused — it tracks what capabilities exist, not
  what governance rules apply to them (risk tier, required gates, ownership).

- **OpenAI Agents SDK** controls tool access at the platform level. But this is
  platform-specific and doesn't compose with cross-boundary capability flow.

**Enhancement:** `CapabilityChainSpec` should include three additional constructs:

**Delegation authority contract** — declares which agents/roles may delegate
which capabilities:

```yaml
delegation_authority:
  - from_role: "orchestrator"
    to_roles: ["code_executor", "researcher", "reviewer"]
    capabilities: ["code_generation", "web_search", "code_review"]
    requires_approval: false

  - from_role: "researcher"
    to_roles: ["code_executor"]
    capabilities: ["code_generation"]
    requires_approval: true  # Researcher cannot delegate code gen without approval
    approval_policy: "human_or_orchestrator"
```

**Capability risk tier registry** — governance metadata separate from the
runtime registry:

```yaml
capability_risk_tiers:
  - capability_id: "code_generation"
    risk_tier: high
    required_gates: ["code_review", "test_pass"]
    owner: "platform-team"
    slo_handoff_success_rate: 0.95

  - capability_id: "web_search"
    risk_tier: low
    required_gates: []
    owner: "infrastructure-team"
    slo_handoff_success_rate: 0.99
```

**Rejection reason taxonomy** — standardized codes for delegation failures:

| Code | Meaning |
|------|---------|
| `unauthorized_role` | Delegating agent lacks authority for this capability |
| `capacity_exceeded` | Target agent is at capacity |
| `validation_failed` | Input failed pre-delegation schema validation |
| `timeout` | Delegation timed out |
| `policy_violation` | Delegation violates governance policy |
| `escalation_required` | Requires human or higher-authority approval |

**Framework evidence:**
- AutoGen: Implicit role-based delegation with no formal contract
- CrewAI: Guardrails enforce locally but failures are not auditable
- Semantic Kernel: Runtime capability registry lacks governance metadata
- OpenAI SDK: Platform-controlled tool access is not composable across boundaries

### Concern 6: SLO Budget Propagation — Generalized to Multi-Budget

**Parent document summary:** Service A has a 200ms p99 SLO. It calls B (50ms
budget), C (100ms budget), D (50ms budget). Budget doesn't propagate.

**What the frameworks reveal:**

Latency is not the only budget that silently exhausts. The frameworks reveal
three additional budget types:

- **Guidance/Instructor** have validation retry loops. Each retry consumes time
  and tokens. If a structured output takes 5 retries, downstream phases get less
  budget. Nobody tracks cumulative retry cost across the pipeline.

- **DSPy** optimization trials consume compute budget. If a pipeline burns its
  optimization budget in early phases, later phases can't tune. The budget is
  per-run, not per-pipeline, so early phases can starve later ones.

- **All frameworks** consume tokens at each phase. A verbose intermediate
  response reduces the token budget available for downstream processing,
  especially when context windows are finite. This is the token analog of
  latency budget exhaustion.

**Enhancement:** `BudgetPropagationSpec` should generalize beyond latency to
multiple budget dimensions:

```yaml
budget_propagation:
  budgets:
    - budget_id: "latency"
      total: 2000  # milliseconds
      unit: "ms"
      allocations:
        seed: 200
        plan: 500
        design: 300
        implement: 800
        validate: 200
      on_exceeded: WARNING

    - budget_id: "retry"
      total: 10  # maximum retries across pipeline
      unit: "retries"
      allocations:
        seed: 2
        plan: 2
        design: 2
        implement: 3
        validate: 1
      on_exceeded: BLOCKING

    - budget_id: "tokens"
      total: 100000
      unit: "tokens"
      allocations:
        seed: 5000
        plan: 20000
        design: 25000
        implement: 40000
        validate: 10000
      on_exceeded: WARNING

    - budget_id: "cost"
      total: 5.00  # USD
      unit: "usd"
      allocations:
        seed: 0.25
        plan: 1.00
        design: 1.25
        implement: 2.00
        validate: 0.50
      on_exceeded: ADVISORY
```

The tracker stamps `remaining_budget_{type}` at each boundary. DEGRADED status
fires when a hop consumes more than its allocation. BROKEN fires when the
remaining budget goes negative.

**Framework evidence:**
- Guidance/Instructor: Validation retries consume time/tokens with no pipeline-wide accounting
- DSPy: Optimization trials can starve downstream phases of compute budget
- All: Token consumption at each phase reduces available context for downstream processing

### Concern 7: Data Lineage — Enhanced with Version Lineage

**Parent document summary:** Track which data was used, which transformations
were applied, trace back to source when something goes wrong.

**What the frameworks reveal:**

- **LlamaIndex** retrieval results depend on which *index snapshot* was used.
  The same query against different index versions produces different results.
  But nobody records "this retrieval used index version X" — making results
  non-reproducible.

- **DSPy** prompt versions are lineage. An optimized prompt replaces an old
  one, but outputs generated by the old prompt are still in the pipeline.
  Nobody tracks which prompt version generated which output.

- **Guidance/Outlines** schema versions affect output structure. A schema
  change can alter the shape of generated outputs. If schema V1 outputs are
  consumed by a downstream phase expecting V2, the mismatch is silent.

**Enhancement:** `ProvenanceChainSpec` should include `configuration_lineage` —
tracking not just "this field was set by phase A" but "this field was set by
phase A using configuration version V":

```yaml
provenance_chains:
  - chain_id: "retrieval_to_generation"
    links:
      - phase: "retrieve"
        field: "retrieved_context"
        configuration_lineage:
          - key: "index_version"
            source: "rag.index_snapshot"
          - key: "embedding_model"
            source: "model.embedding.version"

      - phase: "generate"
        field: "generated_output"
        configuration_lineage:
          - key: "prompt_version"
            source: "prompt.template.hash"
          - key: "model_version"
            source: "model.generation.version"
```

This enables forensic queries: "this output was generated using prompt version
P with retrieval from index version I using embedding model E." When quality
degrades, the lineage identifies exactly which configuration changed.

**Framework evidence:**
- LlamaIndex: Index snapshot determines retrieval quality, not tracked
- DSPy: Prompt version determines output quality, not tracked alongside outputs
- Guidance/Outlines: Schema version affects output shape, not propagated to consumers

---

## Part 2: New Concerns Discovered via Framework Comparison

These concerns are not in the parent document. Each follows the same pathology:
information is produced at a source, flows through a channel, is consumed at a
sink, and silently degrades in the channel. Each fits the same four primitives
(Declare, Validate, Track, Emit).

### Concern 9: Intermediate Quality Propagation

**The problem:**

Context Propagation (Concern 1) checks that a field *exists* at each boundary.
Schema Evolution (Concern 2) checks that the field has the *right structure*.
Neither checks that the field's *value is good enough*.

A retrieval phase returns low-confidence results. The field exists (passes
propagation check). The structure is valid (passes schema check). But the
quality is poor, and the downstream generation phase produces subtly worse
output because it was given low-quality input.

This is the most literal instantiation of the design doc's core problem
statement: "no errors, reduced quality."

**Why it's hard:** Quality is subjective and domain-specific. A retrieval
confidence of 0.6 might be acceptable for a brainstorming task but disastrous
for a legal document. Traditional systems don't propagate quality metadata
alongside the data itself.

**What the frameworks do (and don't do):**

- **LlamaIndex** computes retrieval confidence scores and relevance metrics.
  But these are local to the retrieval step — they don't propagate as contracts
  to the generation step.

- **Haystack** components have quality thresholds. But thresholds are
  per-component configuration, not pipeline-wide contracts.

- **DSPy** optimizes for metrics (accuracy, coherence, cost). But the metrics
  are evaluation-time constructs, not boundary-time contracts.

All three frameworks *have* quality signals. None of them *propagate* quality
as a contract.

**ContextCore approach:** A `QualityPropagationSpec` that extends `FieldSpec`
with quality assertions:

```yaml
phases:
  retrieve:
    exit:
      required:
        - name: retrieved_context
          severity: BLOCKING
          quality:
            metric: retrieval_confidence
            threshold: 0.7
            on_below: WARNING
            description: "Retrieval confidence below 0.7 degrades generation quality"

        - name: coverage_score
          severity: BLOCKING
          quality:
            metric: topic_coverage
            threshold: 0.8
            on_below: BLOCKING
            description: "Topic coverage below 80% means generation will miss key topics"

  generate:
    exit:
      required:
        - name: generated_output
          severity: BLOCKING
          quality:
            metric: coherence_score
            threshold: 0.85
            on_below: WARNING
```

**Implementation fit:** The `BoundaryValidator` already validates field
presence. Quality validation extends this: after confirming the field exists,
check `context[quality_metric] >= threshold`. The quality metric can be stamped
by the producing phase (LlamaIndex stamps `retrieval_confidence` already) or
computed at the boundary.

**Composability:** Quality Propagation composes with every existing layer:
- Layer 1 + Quality: "Field exists AND is good enough"
- Layer 3 + Quality: "Field is named correctly AND is good enough"
- Layer 6 + Quality: "Alert when quality drops below threshold"
- Layer 7 + Quality: "Regression gate: quality must not decrease"

**The CS parallel:** This is **refinement types** in programming language
theory — types annotated with predicates. `int` says the value exists and is
an integer. `{x: int | x > 0}` says the value exists, is an integer, and is
positive. Quality propagation adds refinement predicates to context fields.

### Concern 10: Checkpoint Recovery Integrity

**The problem:**

When a long-running workflow checkpoints and resumes later, the context
snapshot from checkpoint time may be stale. External data sources may have
updated. Model versions may have rotated. Dependencies may have changed. The
checkpoint preserves context integrity *at checkpoint time*, but resume happens
in a different world.

This is a *temporal* variant of context propagation. In the standard model,
the "channel" is a sequence of phases. In checkpoint recovery, the "channel"
is the passage of time during a pause. Information doesn't flow through
intermediate services — it flows *through time*, and time degrades it.

**Why it's hard:** Checkpoints are designed for durability. The entire point
is that you can resume from the exact state you left. But "exact state" is
only the internal state — the external world has moved on. No checkpoint
system validates whether the internal state is still consistent with the
external world on resume.

**What the frameworks do (and don't do):**

- **LangGraph** provides durable checkpoints with state snapshots at each
  node. The checkpoint captures the full state graph. But on resume, no
  validation runs — the assumption is that the checkpoint is sufficient.

- **CrewAI** flows are resumable via state persistence. Same gap: resume
  trusts the persisted state without re-validation.

Neither framework checks: "is this checkpointed context still valid given that
time has passed?"

**ContextCore approach:** A `CheckpointIntegritySpec` that declares
per-checkpoint validation requirements:

```yaml
checkpoint_integrity:
  - checkpoint_id: "post_retrieval"
    phase: "retrieve"
    on_resume:
      revalidate_entry: true  # Re-run entry validation of next phase
      staleness_checks:
        - field: "rag.index_snapshot"
          max_age_seconds: 3600
          on_stale: BLOCKING
          recovery: "re_retrieve"

        - field: "model.version"
          max_age_seconds: 86400
          on_stale: WARNING
          recovery: "log_and_continue"

      approval_required: false

  - checkpoint_id: "post_generation"
    phase: "generate"
    on_resume:
      revalidate_entry: true
      staleness_checks:
        - field: "prompt.template.hash"
          max_age_seconds: 43200  # 12 hours
          on_stale: WARNING
          recovery: "re_generate_with_current_prompt"

      approval_required: true
      approval_policy: "human_or_orchestrator"
```

**Implementation fit:** On resume, the guard runs the staleness checks before
proceeding. This composes with Layer 4 (Runtime Boundary Checks): the resume
boundary is treated as a phase entry boundary with additional temporal
constraints.

**The CS parallel:** This is **temporal logic** applied to distributed state.
Specifically, it's the **validity interval** concept from temporal databases
— every fact has a time range during which it is valid. Context fields have
implicit validity intervals that are never checked.

### Concern 11: Prompt and Configuration Evolution

**The problem:**

Schema Evolution (Concern 2) handles data schema drift between services. But
agent pipelines have a parallel problem on the *control plane*: prompts,
configurations, model parameters, and system instructions evolve over time.
A prompt version change can silently degrade output quality. A model parameter
change can alter behavior. A system instruction edit can shift the agent's
decision-making.

None of this is tracked as schema evolution. The prompt is not a "schema" in
the traditional sense — it's a *behavior specification* that affects output
quality without affecting output structure. The output might parse correctly
(schema is fine) but be semantically worse (the prompt degraded).

**Why it's hard:** Prompts are often treated as configuration, not code. They
change frequently, are version-controlled inconsistently, and their effects
are difficult to measure without evaluation pipelines. A "small tweak" to a
prompt can have cascading quality effects downstream, and the causal link
between the tweak and the degradation is invisible.

**What the frameworks do (and don't do):**

- **DSPy** has signature versioning and optimization loops that track
  before/after metrics. But optimized prompts are promoted without formal
  gates — the optimization loop decides, not a governance system.

- **Guidance/Outlines** use schema versions to constrain output structure.
  But schema version changes are not tracked as evolution events with
  compatibility analysis.

- **LangGraph** state schemas can evolve between versions of a graph. But
  there is no contract declaring which schema versions are compatible with
  which graph versions.

**ContextCore approach:** A `ConfigurationEvolutionSpec` that applies the same
contract model as Schema Evolution, but to the control plane:

```yaml
configuration_evolution:
  schema_version: "1.0.0"
  contract_type: "configuration_evolution"

  configurations:
    - config_id: "generation_prompt"
      type: "prompt_template"
      current_version: "v3.2.1"
      version_history:
        - version: "v3.2.1"
          hash: "sha256:abc123..."
          deployed_at: "2026-02-15T10:00:00Z"
          change_description: "Added domain-specific constraints"
        - version: "v3.2.0"
          hash: "sha256:def456..."
          deployed_at: "2026-02-10T10:00:00Z"

    - config_id: "retrieval_parameters"
      type: "model_config"
      current_version: "v2.0.0"

  evolution_rules:
    - rule_id: "prompt_promotion"
      scope: "prompt_template"
      policy: "gated_promotion"
      requirements:
        - quality_threshold: 0.85
        - regression_check: true
        - human_approval: "optional"  # Required for high-risk prompts
      description: "Prompt changes must pass quality gate and regression check"

    - rule_id: "model_config_change"
      scope: "model_config"
      policy: "backward_compatible"
      requirements:
        - schema_compatible: true
        - output_quality_check: true
```

**Implementation fit:** This uses the same `EvolutionTracker` pattern from
Layer 2 (Schema Compatibility). The `RegressionGate` from Layer 7 can gate
prompt promotions: "completeness must not decrease AND output quality must not
decrease AND no breaking schema changes."

**The CS parallel:** This is **behavioral subtyping** (Liskov Substitution
Principle) applied to configurations. A new prompt version is a behavioral
subtype of the old one if it produces outputs that satisfy all downstream
expectations. The contract declares what "all downstream expectations" means.

### Concern 12: Graph Topology Correctness

**The problem:**

The parent design document assumes linear phase pipelines: seed -> plan ->
design -> implement -> validate. But LangGraph, Haystack, and CrewAI use
graph-based execution with branching, merging, and cycles. This introduces
failure modes that linear pipelines don't have:

- **Branch divergence:** A routing decision sends context down path A, which
  drops field X. Path B preserves field X. The merge point receives context
  from A (missing X) or B (has X) depending on which path was taken. The
  merge point's behavior is non-deterministic with respect to field X.

- **Merge conflict:** Two branches both modify field Y. At the merge point,
  which value wins? The answer is usually "last write wins" — but this
  silently discards one branch's contribution.

- **Cycle invariant violation:** A reasoning loop (agent -> tool -> agent)
  runs N iterations. Each iteration may modify context. After N iterations,
  which fields are guaranteed to still be present? No contract declares
  cycle invariants.

**Why it's hard:** Linear pipeline analysis walks a single path. Graph analysis
must walk *all possible paths* and verify that every path maintains context
integrity. The number of paths grows exponentially with branching depth. And
cycles make the path set infinite unless you bound the iteration count.

**What the frameworks do (and don't do):**

- **LangGraph** has conditional edges that route based on agent output. But
  there's no contract declaring "if we take this edge, these fields are
  preserved; if we take the other edge, these fields are lost."

- **Haystack** has directed multigraphs with typed component I/O. But the
  typing is per-component, not per-path. There's no pipeline-wide path
  analysis.

- **CrewAI** flows have router steps that dispatch to different sub-flows.
  But the router's context effects are implicit.

**ContextCore approach:** A `GraphTopologySpec` that declares path-aware
context contracts:

```yaml
graph_topology:
  graph_id: "retrieval_augmented_generation"

  nodes:
    classify:
      produces: ["domain", "complexity_tier"]
    retrieve_simple:
      requires: ["domain"]
      produces: ["retrieved_context"]
    retrieve_complex:
      requires: ["domain", "complexity_tier"]
      produces: ["retrieved_context", "retrieval_confidence"]
    generate:
      requires: ["retrieved_context"]
      optional: ["retrieval_confidence"]

  edges:
    - from: classify
      to: retrieve_simple
      condition: "complexity_tier == 'low'"
      preserves: ["domain"]
      drops: ["complexity_tier"]  # Not needed downstream

    - from: classify
      to: retrieve_complex
      condition: "complexity_tier in ['medium', 'high']"
      preserves: ["domain", "complexity_tier"]

  merge_points:
    - node: generate
      sources: [retrieve_simple, retrieve_complex]
      merge_policy:
        retrieved_context: "required_from_any"  # Must come from whichever branch ran
        retrieval_confidence: "optional"  # Only present from complex path

  cycle_invariants:
    - cycle_id: "reasoning_loop"
      nodes: ["reason", "tool_call", "evaluate"]
      max_iterations: 5
      invariant_fields: ["task_id", "project_id", "session_id"]
      description: "Core identity fields must survive all loop iterations"
```

**Implementation fit:** The static analyzer (Layer 2 in the implementation
stack) would walk all paths through the graph and verify that every path
satisfies its propagation chains. This is the graph-theoretic generalization
of "dangling reads" and "dead writes" detection. The `PreflightChecker`
(Layer 3) would verify that the graph topology is internally consistent before
any execution.

**The CS parallel:** This is **path-sensitive analysis** from compiler theory.
Linear analysis is "flow-insensitive" — it ignores control flow. Path-sensitive
analysis tracks different facts along different execution paths. Graph topology
contracts make path-sensitivity explicit in the contract language.

### Concern 13: Evaluation-Gated Propagation

**The problem:**

Some phase outputs need to be *evaluated* — by a model, a metric, or a
human — before they should propagate to the next phase. The output may exist
(passes propagation check), have valid structure (passes schema check), and
even have acceptable quality metrics (passes quality check). But it hasn't
been *judged*.

An un-evaluated output that propagates is a quality risk. The evaluation itself
is a signal: "a qualified observer has confirmed that this output is fit for
downstream use." Without that signal, the output is *assumed* fit — and
assumptions are where silent degradation lives.

**Why it's hard:** Evaluation adds latency and cost. Most systems skip it for
efficiency. When evaluation does happen, it's a local decision — the downstream
phase has no way to know whether the upstream output was evaluated or just
passed through.

**What the frameworks do (and don't do):**

- **OpenAI Agents SDK** has eval/trace grading hooks. But grading is optional,
  happens after execution, and doesn't gate propagation.

- **DSPy** has metric-driven validation during optimization. But the validation
  is during the optimization loop, not during production execution.

- **LlamaIndex** has evaluation patterns for retrieval quality. But evaluation
  is a separate pipeline step, not a boundary constraint.

All three frameworks *can* evaluate. None of them *require* evaluation as a
propagation precondition.

**ContextCore approach:** Extend `FieldSpec` with an `evaluation_required` flag
and evaluation policy:

```yaml
phases:
  generate:
    exit:
      required:
        - name: generated_code
          severity: BLOCKING
          evaluation:
            required: true
            policy: "score_threshold"
            threshold: 0.8
            evaluator: "code_review_agent"
            on_unevaluated: BLOCKING
            on_below_threshold: WARNING
            description: "Generated code must be reviewed before propagation"

        - name: generated_documentation
          severity: WARNING
          evaluation:
            required: true
            policy: "human_or_model"
            threshold: 0.7
            on_unevaluated: WARNING
            on_below_threshold: ADVISORY
            description: "Documentation should be reviewed; proceed with warning if not"
```

**Implementation fit:** The `BoundaryValidator` would check three things in
sequence:

1. Field exists (Concern 1: propagation)
2. Field structure is valid (Concern 2: schema)
3. Field has been evaluated AND evaluation passed (Concern 13: evaluation gate)

The evaluation result would be stamped in provenance:
`FieldProvenance(origin_phase, set_at, value_hash, evaluated_by, evaluation_score)`.

**Composability:**
- Layer 1 + Evaluation: "Field exists AND has been evaluated"
- Concern 9 + Evaluation: "Field quality is above threshold AND an evaluator confirmed it"
- Layer 7 + Evaluation: "Regression gate: evaluation pass rate must not decrease"

**The CS parallel:** This is **proof-carrying code** (Necula, 1997). In PCC, a
program carries a proof that it satisfies a safety policy. The runtime verifies
the proof rather than re-analyzing the code. Evaluation-gated propagation is
the same pattern: an output carries an evaluation proof (the score and
evaluator identity) that the next phase verifies.

---

## Unified Extension Map

### How the Extensions Relate to the Existing Layer Architecture

The parent document's implementation layers (1-7) are a defense-in-depth stack
from preventive to reactive. The extensions add new *contract types* that
plug into the existing layers:

```
Implementation Layer 7: Regression Prevention
  └── Gates: completeness, health, drift, quality regression,
             evaluation pass rate regression, budget regression
Implementation Layer 6: Observability & Alerting
  └── Alerts: quality thresholds, budget exhaustion, checkpoint
              staleness, evaluation failures, delegation rejections
Implementation Layer 5: Post-Execution Validation
  └── Checks: chain integrity, quality chain integrity,
              evaluation chain integrity, budget accounting
Implementation Layer 4: Runtime Boundary Checks
  └── Validates: field presence, quality metrics, evaluation
                 stamps, budget remaining, delegation authority,
                 checkpoint freshness
Implementation Layer 3: Pre-Flight Verification
  └── Checks: graph topology paths, quality thresholds
              achievable, budget allocations sum correctly,
              delegation authority declared
Implementation Layer 2: Static Analysis
  └── Analyzes: propagation graph + quality graph + budget
                graph + topology graph + configuration lineage
Implementation Layer 1: Context Contracts (Declarations)
  └── Declares: all of the above as YAML contracts
```

The extensions do NOT add new layers. They add new **contract types** that the
existing layers validate.

### Contract Type Summary

| # | Contract Type | New Spec | Fits Existing Layer(s) | Source Frameworks |
|---|---------------|----------|----------------------|-------------------|
| 4e | Temporal Staleness | `OrderingConstraintSpec` (enhanced) | L4 (boundary check on resume) | LangGraph, AutoGen |
| 5e | Delegation Authority | `CapabilityChainSpec` (enhanced) | L3 (preflight), L4 (runtime) | AutoGen, CrewAI, SK, OpenAI |
| 6e | Multi-Budget | `BudgetPropagationSpec` (enhanced) | L4 (boundary), L5 (post-exec), L6 (alerts) | Guidance, DSPy |
| 7e | Version Lineage | `ProvenanceChainSpec` (enhanced) | L5 (post-exec), L7 (regression) | LlamaIndex, DSPy, Guidance |
| 9 | Quality Propagation | `QualityPropagationSpec` (NEW) | L1 (declare), L4 (boundary), L6 (alert), L7 (gate) | LlamaIndex, Haystack, DSPy |
| 10 | Checkpoint Integrity | `CheckpointIntegritySpec` (NEW) | L3 (preflight), L4 (boundary on resume) | LangGraph, CrewAI |
| 11 | Config Evolution | `ConfigurationEvolutionSpec` (NEW) | L2 (static), L7 (regression gate) | DSPy, Guidance, LangGraph |
| 12 | Graph Topology | `GraphTopologySpec` (NEW) | L2 (static), L3 (preflight) | LangGraph, Haystack, CrewAI |
| 13 | Evaluation Gate | `FieldSpec.evaluation` (extension) | L4 (boundary), L5 (post-exec) | OpenAI SDK, DSPy, LlamaIndex |

### Shared Primitives

All extensions use the same four primitives from the parent document:

| Primitive | How Extensions Use It |
|-----------|----------------------|
| **Declare** | YAML contracts with new Spec types |
| **Validate** | `BoundaryValidator` extended with quality, evaluation, budget, staleness checks |
| **Track** | `PropagationTracker.stamp()` extended with quality metrics, evaluation stamps, budget remaining |
| **Emit** | `emit_*_result()` helpers for each new contract type |

All extensions use the same severity model: BLOCKING / WARNING / ADVISORY.

All extensions compose with existing layers without modifying them.

---

## Implementation Priority

### Tier 1: High Value, Low Complexity (Extend Existing Primitives)

These enhance existing contract types with minimal new code:

1. **Quality Propagation (Concern 9)** — Extend `FieldSpec` with optional
   `quality` block. Extend `BoundaryValidator._validate_field()` to check
   quality threshold. ~100 lines of new code + tests.

2. **Evaluation-Gated Propagation (Concern 13)** — Extend `FieldSpec` with
   optional `evaluation` block. Extend `BoundaryValidator._validate_field()`
   to check evaluation stamp. ~80 lines + tests.

3. **Multi-Budget Propagation (Concern 6e)** — New `BudgetPropagationSpec`
   model + `BudgetTracker` class. Stamps `remaining_budget` at boundaries.
   ~200 lines + tests.

### Tier 2: Medium Value, Medium Complexity (New Spec Types)

These add new contract types that plug into existing layers:

4. **Delegation Authority (Concern 5e)** — New fields on `CapabilityChainSpec`.
   New `DelegationAuthorityChecker` validates at boundary. ~250 lines + tests.

5. **Checkpoint Recovery Integrity (Concern 10)** — New
   `CheckpointIntegritySpec`. Validates staleness on resume. ~200 lines + tests.

6. **Configuration Evolution (Concern 11)** — Extend `SchemaCompatibilitySpec`
   or new `ConfigurationEvolutionSpec`. Uses existing `EvolutionTracker`
   pattern. ~200 lines + tests.

### Tier 3: High Value, High Complexity (Graph Analysis)

These require new analysis capabilities:

7. **Graph Topology Correctness (Concern 12)** — New `GraphTopologySpec` +
   path-sensitive analyzer. Requires graph walking with path enumeration.
   ~400 lines + tests.

8. **Temporal Staleness (Concern 4e)** — Extend `OrderingConstraintSpec` with
   staleness budgets. Requires timestamp comparison at resume boundaries.
   ~150 lines + tests. (Lower complexity but depends on checkpoint support.)

### Estimated Totals

| Tier | Concerns | Est. Implementation | Est. Tests |
|------|----------|-------------------|-----------|
| Tier 1 | 9, 13, 6e | ~380 lines | ~60 tests |
| Tier 2 | 5e, 10, 11 | ~650 lines | ~80 tests |
| Tier 3 | 12, 4e | ~550 lines | ~60 tests |
| **Total** | **9 extensions** | **~1,580 lines** | **~200 tests** |

---

## Design Principles (Inherited + Extended)

The parent document's six design principles apply unchanged. Two additional
principles emerge from the framework comparison:

### 7. Framework-Agnostic Contracts Over Framework-Specific Adapters

Contracts declare *what* must be true. They do not declare *how* the framework
achieves it. A `QualityPropagationSpec` works whether the runtime is LangGraph,
AutoGen, CrewAI, or a custom pipeline. Framework-specific adapters translate
framework events into contract validation calls, but the contracts themselves
are portable.

### 8. Governance Metadata Over Runtime Metadata

When frameworks already track something (LangGraph checkpoint IDs, AutoGen turn
numbers, CrewAI crew roles), ContextCore does not duplicate the runtime
metadata. Instead, it adds *governance metadata* on top: who approved the
checkpoint resume, which delegation policy was applied, what quality threshold
was required. The governance metadata is what makes the runtime metadata
auditable.

---

## References

### Framework Documentation

- LangChain/LangGraph. *StateGraph and Checkpointing*. https://python.langchain.com/docs/langgraph
- Microsoft. *AutoGen: Enabling Next-Gen LLM Applications*. https://microsoft.github.io/autogen/
- CrewAI. *Framework for Orchestrating Role-Playing AI Agents*. https://docs.crewai.com/
- Microsoft. *Semantic Kernel*. https://learn.microsoft.com/semantic-kernel/
- LlamaIndex. *Data Framework for LLM Applications*. https://docs.llamaindex.ai/
- deepset. *Haystack: Building NLP Pipelines*. https://docs.haystack.deepset.ai/
- OpenAI. *Agents SDK*. https://platform.openai.com/docs/agents
- Stanford NLP. *DSPy: Programming — not Prompting — Foundation Models*. https://dspy-docs.vercel.app/
- Microsoft. *Guidance: Constrained Generation*. https://github.com/guidance-ai/guidance

### Computer Science Theory

- Freeman, T. & Pfenning, F. (1991). *Refinement Types for ML*. PLDI.
  — Types annotated with predicates; theoretical basis for Quality Propagation.
- Necula, G.C. (1997). *Proof-Carrying Code*. POPL.
  — Programs carry proofs of safety; theoretical basis for Evaluation-Gated Propagation.
- Snodgrass, R.T. (1987). *The Temporal Query Language TQuel*. ACM TODS 12(2).
  — Temporal databases with validity intervals; theoretical basis for Checkpoint Recovery Integrity.
- Liskov, B. & Wing, J. (1994). *A Behavioral Notion of Subtyping*. ACM TOPLAS 16(6).
  — Behavioral subtyping; theoretical basis for Configuration Evolution contracts.
- Ball, T. & Rajamani, S.K. (2001). *Automatically Validating Temporal Safety Properties of Interfaces*. SPIN.
  — Path-sensitive verification; theoretical basis for Graph Topology Correctness.

### ContextCore

- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — Parent design document
- [Framework Comparison Notes](../framework-comparisons/FRAMEWORK_COMPARISON_NOTES.md) — OpenAI SDK, DSPy, Guidance analysis
- [LangGraph, AutoGen, CrewAI Comparison](../framework-comparisons/FRAMEWORK_COMPARISON_LANGGRAPH_AUTOGEN_CREWAI.md)
- [SK, LlamaIndex, Haystack Comparison](../framework-comparisons/FRAMEWORK_COMPARISON_SK_LLAMA_HAYSTACK.md)
- [Runtime Selection Matrix (ContextCore user lens)](../framework-comparisons/RUNTIME_SELECTION_MATRIX_FOR_CONTEXTCORE_USERS_PLATFORM_CHOICES.md)
- [Runtime Selection Matrix (Platform user lens)](../framework-comparisons/RUNTIME_SELECTION_MATRIX_FOR_PLATFORM_USERS_CONTEXTCORE_BENEFITS.md)
