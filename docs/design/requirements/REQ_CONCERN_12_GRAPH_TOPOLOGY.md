# REQ-12: Graph Topology Correctness

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Priority Tier:** Tier 3 (High Value, High Complexity)
**Companion Document:** [Context Correctness Extensions](../CONTEXT_CORRECTNESS_EXTENSIONS.md), Concern 12
**Parent Document:** [Context Correctness by Construction](../CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)
**CS Parallel:** Path-sensitive analysis (Ball & Rajamani, 2001)
**Estimated Implementation:** ~400 lines + tests

---

## Problem Statement

The Context Correctness by Construction framework assumes linear phase pipelines
(seed -> plan -> design -> implement -> validate). The `ContextContract` model
declares phases as an ordered dict, and the `PreflightChecker` walks a single
`phase_order` list to detect dangling reads and dead writes.

But LangGraph, Haystack, and CrewAI use **graph-based execution** with
branching, merging, and cycles. This introduces three failure modes that linear
pipelines do not have:

### Branch Divergence

A routing decision sends context down path A (drops field X) vs path B
(preserves field X). The merge point's behavior is non-deterministic with
respect to field X. No contract declares which fields survive which path.

```
classify ──[low]──> retrieve_simple ──> generate
         ──[high]─> retrieve_complex ──>
```

If `retrieve_simple` drops `complexity_tier` but `retrieve_complex` preserves
it, then `generate` may or may not have `complexity_tier` depending on which
branch executed. A contract that declares `complexity_tier` as required on
`generate` will fail on the simple path. A contract that declares it as
optional loses the guarantee on the complex path. Neither option is correct
-- the right answer is a **merge policy** that declares the field's status
per-source.

### Merge Conflict

Two branches both modify field Y. At the merge point, which value wins? The
answer is usually "last write wins," but this silently discards one branch's
contribution. No contract declares merge semantics.

### Cycle Invariant Violation

A reasoning loop (agent -> tool -> agent) runs N iterations. Each iteration
may modify context. After N iterations, which fields are guaranteed to still
be present? No contract declares cycle invariants, so identity fields
(`task_id`, `project_id`, `session_id`) may be silently corrupted by a tool
call that overwrites them.

### Why Linear Analysis Is Insufficient

The existing `PreflightChecker._check_phase_graph()` walks a single ordered
list. It detects dangling reads and dead writes along that one path. Graph
execution creates an exponentially larger set of possible paths. A field may
be reachable on 3 of 4 paths but unreachable on the 4th. Linear analysis
either misses the unreachable path or over-reports by treating all paths as
one.

---

## Requirements

### Data Models

#### REQ-12-001: GraphNode Model

**Priority:** P1
**Description:** Define a `GraphNode` Pydantic v2 model representing a single
node in a graph topology. Each node declares the context fields it requires as
input, the fields it produces as output, and optional fields it may consume
but does not require.

**Acceptance Criteria:**
- Model has fields: `node_id` (str, required), `requires` (list[str]),
  `produces` (list[str]), `optional` (list[str], default empty),
  `description` (Optional[str])
- Uses `ConfigDict(extra="forbid")` per project convention
- `node_id` has `min_length=1`
- Rejects duplicate field names within `requires`, `produces`, or `optional`
  via model validator
- Serializes to/from YAML round-trip correctly

**Affected Files:**
- `src/contextcore/contracts/topology/schema.py` (new)


#### REQ-12-002: GraphEdge Model

**Priority:** P1
**Description:** Define a `GraphEdge` Pydantic v2 model representing a
directed edge between two nodes. Each edge declares a routing condition
(string expression), which fields the edge preserves from the source node's
output, and which fields the edge explicitly drops.

**Acceptance Criteria:**
- Model has fields: `from_node` (str, required, serialized as `from` in YAML),
  `to_node` (str, required, serialized as `to` in YAML), `condition`
  (Optional[str], the routing expression), `preserves` (list[str], default
  empty), `drops` (list[str], default empty), `description` (Optional[str])
- Uses `ConfigDict(extra="forbid")`
- A field cannot appear in both `preserves` and `drops` (model validator)
- `from_node` and `to_node` have `min_length=1`

**Affected Files:**
- `src/contextcore/contracts/topology/schema.py`


#### REQ-12-003: MergePolicy Enum

**Priority:** P1
**Description:** Define a `MergePolicy` string enum that declares how a
merge point resolves conflicting or divergent field values from multiple
source branches.

**Acceptance Criteria:**
- Enum values:
  - `required_from_any` -- field must be present from at least one source
    branch; uses the value from whichever branch executed
  - `required_from_all` -- field must be present from ALL source branches;
    validation fails if any branch omits it
  - `prefer_latest` -- if multiple branches provide the field, use the value
    with the most recent provenance timestamp
  - `union_all` -- merge list/set values from all branches (for collection
    fields)
- Enum is a `str, Enum` subclass per `contracts/types.py` convention
- Added to `contracts/types.py` alongside existing enums

**Affected Files:**
- `src/contextcore/contracts/types.py`


#### REQ-12-004: MergePoint Model

**Priority:** P1
**Description:** Define a `MergePoint` Pydantic v2 model representing a
node where multiple execution branches converge. Declares which source
nodes may feed into the merge point and a per-field merge policy.

**Acceptance Criteria:**
- Model has fields: `node` (str, required -- the node_id of the merge point),
  `sources` (list[str], min 2 -- the node_ids of converging branches),
  `merge_policy` (dict[str, MergePolicy], required -- maps field name to
  policy), `description` (Optional[str])
- Uses `ConfigDict(extra="forbid")`
- Validates that `sources` has at least 2 entries
- `merge_policy` keys must be non-empty strings

**Affected Files:**
- `src/contextcore/contracts/topology/schema.py`


#### REQ-12-005: CycleInvariant Model

**Priority:** P1
**Description:** Define a `CycleInvariant` Pydantic v2 model representing
invariant constraints on a cycle (loop) in the graph. Declares which nodes
form the cycle, the maximum iteration count, and which fields must survive
all iterations unchanged.

**Acceptance Criteria:**
- Model has fields: `cycle_id` (str, required), `nodes` (list[str], min 2 --
  the ordered node_ids forming the cycle), `max_iterations` (int, required,
  ge=1), `invariant_fields` (list[str], required -- fields that must not be
  dropped or modified during iteration), `description` (Optional[str])
- Uses `ConfigDict(extra="forbid")`
- `cycle_id` has `min_length=1`
- `max_iterations` must be >= 1

**Affected Files:**
- `src/contextcore/contracts/topology/schema.py`


#### REQ-12-006: GraphTopologySpec Top-Level Model

**Priority:** P1
**Description:** Define a `GraphTopologySpec` Pydantic v2 model as the
root model for a graph topology contract. Aggregates nodes, edges, merge
points, and cycle invariants. This model is the graph-aware analog of
`ContextContract`, which models linear pipelines.

**Acceptance Criteria:**
- Model has fields: `graph_id` (str, required), `description`
  (Optional[str]), `nodes` (dict[str, GraphNode], required -- keyed by
  node_id), `edges` (list[GraphEdge], required), `merge_points`
  (list[MergePoint], default empty), `cycle_invariants`
  (list[CycleInvariant], default empty)
- Uses `ConfigDict(extra="forbid")`
- `graph_id` has `min_length=1`
- `edges` must reference only node_ids that exist in `nodes` (model
  validator)
- `merge_points[].node` must reference a node_id in `nodes` (model
  validator)
- `merge_points[].sources` must reference node_ids in `nodes` (model
  validator)
- `cycle_invariants[].nodes` must reference node_ids in `nodes` (model
  validator)
- Serializes to/from YAML round-trip correctly

**Affected Files:**
- `src/contextcore/contracts/topology/schema.py`


#### REQ-12-007: ContextContract Extension for Optional Graph Topology

**Priority:** P2
**Description:** Extend the existing `ContextContract` model with an
optional `graph_topology` field of type `GraphTopologySpec`. When present,
the contract describes a graph-based pipeline. When absent, the contract
describes a linear pipeline (backward compatible).

**Acceptance Criteria:**
- `ContextContract` gains `graph_topology: Optional[GraphTopologySpec] =
  None`
- Existing contracts without `graph_topology` continue to parse and
  validate identically (no regression)
- When `graph_topology` is present, the `PreflightChecker` delegates to
  the `GraphTopologyAnalyzer` for graph-aware analysis instead of linear
  `_check_phase_graph()`
- The `phases` dict and `graph_topology.nodes` dict can coexist; nodes
  provide graph structure while phases provide boundary contracts

**Affected Files:**
- `src/contextcore/contracts/propagation/schema.py`
- `src/contextcore/contracts/preflight/checker.py`


### Analysis Engine

#### REQ-12-008: GraphTopologyAnalyzer Class

**Priority:** P1
**Description:** Implement a `GraphTopologyAnalyzer` class that performs
static analysis on a `GraphTopologySpec`. This is the graph-aware
counterpart to the linear `_check_phase_graph()` in `PreflightChecker`.

**Acceptance Criteria:**
- Class accepts a `GraphTopologySpec` in its constructor
- Provides `analyze() -> GraphAnalysisResult` method that runs all checks
- Runs path enumeration, per-path propagation verification, merge conflict
  detection, and cycle invariant verification
- Does not execute any workflow -- purely static analysis of the contract
- Follows the class pattern of `PreflightChecker` (stateless, result model)

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py` (new)


#### REQ-12-009: Path Enumeration with Branching

**Priority:** P1
**Description:** The `GraphTopologyAnalyzer` must enumerate all possible
execution paths through the graph, including branching paths created by
conditional edges. Each path is a sequence of node_ids from an entry node
(a node with no incoming edges) to a terminal node (a node with no
outgoing edges).

**Acceptance Criteria:**
- Entry nodes are automatically identified (nodes with no incoming edges)
- Terminal nodes are automatically identified (nodes with no outgoing edges)
- Branching edges from the same source node create separate paths
- Cycles are bounded by `CycleInvariant.max_iterations` (if declared) or a
  configurable default (e.g., 10) to prevent infinite enumeration
- The result includes the list of all enumerated paths as
  `list[list[str]]` (each path is a list of node_ids)
- Path count is logged at INFO level; if the path count exceeds a
  configurable threshold (default 1000), the analyzer emits a WARNING and
  truncates

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py`


#### REQ-12-010: Per-Path Propagation Chain Verification

**Priority:** P1
**Description:** For each enumerated path, the analyzer must verify that
every node's `requires` fields are satisfied by the combination of: (a)
fields produced by earlier nodes on that path, and (b) fields preserved by
the edges along that path. This is the path-sensitive generalization of
`PreflightChecker._check_phase_graph()`.

**Acceptance Criteria:**
- For each path, walk the node sequence and accumulate available fields:
  - Start with fields produced by the entry node
  - At each edge, apply `preserves` and `drops` to filter the available
    set: fields explicitly in `drops` are removed; if `preserves` is
    non-empty, only those fields (plus newly produced fields) are kept
  - At each node, check that all `requires` fields are in the available set
- A field that fails on ANY path is reported as a violation
- Violations include the specific path on which the field is missing
- Violation severity is BLOCKING for `requires` fields and WARNING for
  `optional` fields that the node declares but no path provides

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py`


#### REQ-12-011: Merge Conflict Detection

**Priority:** P1
**Description:** For each `MergePoint` in the topology, the analyzer must
detect fields that are produced by more than one source branch and verify
that the declared `merge_policy` for each such field is consistent with
the field's semantics.

**Acceptance Criteria:**
- Identify all fields produced by each source branch of a merge point
- A "merge conflict" is a field produced by 2+ sources with no merge policy
  declared -- reported as severity WARNING
- A field produced by 2+ sources WITH a merge policy declared is
  considered resolved (no violation)
- A `merge_policy` referencing a field that no source branch produces is
  reported as an ADVISORY (dead policy)
- A field declared as `required_from_all` that is only produced by some
  source branches is a BLOCKING violation
- Results include the list of conflicting fields, which branches produce
  them, and the resolved/unresolved status

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py`


#### REQ-12-012: Cycle Invariant Verification

**Priority:** P1
**Description:** For each `CycleInvariant` in the topology, the analyzer
must verify that the declared `invariant_fields` are not dropped or
overwritten by any node or edge within the cycle.

**Acceptance Criteria:**
- Walk the cycle's nodes in declared order
- For each node in the cycle, check that no `produces` field overwrites an
  invariant field (unless the node also `requires` it, indicating
  intentional pass-through)
- For each edge within the cycle, check that no invariant field appears in
  `drops`
- Violations are BLOCKING severity
- Verification reports: cycle_id, which invariant field is violated, which
  node or edge causes the violation, and the iteration at which the
  violation would first manifest (always iteration 1 for static analysis)

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py`


#### REQ-12-013: GraphAnalysisResult Model

**Priority:** P1
**Description:** Define a `GraphAnalysisResult` Pydantic v2 model that
aggregates the output of all graph topology analysis checks.

**Acceptance Criteria:**
- Model has fields:
  - `passed` (bool) -- True if no BLOCKING violations
  - `graph_id` (str)
  - `paths_enumerated` (int) -- number of distinct paths found
  - `paths` (list[list[str]]) -- the actual path sequences
  - `path_violations` (list[PathViolation]) -- per-path propagation
    failures
  - `merge_conflicts` (list[MergeConflict]) -- merge point issues
  - `cycle_violations` (list[CycleViolation]) -- cycle invariant failures
  - `nodes_analyzed` (int)
  - `edges_analyzed` (int)
- `PathViolation` sub-model: `path` (list[str]), `node` (str),
  `missing_field` (str), `severity` (ConstraintSeverity), `message` (str)
- `MergeConflict` sub-model: `merge_node` (str), `field` (str),
  `sources` (list[str]), `has_policy` (bool), `severity`
  (ConstraintSeverity), `message` (str)
- `CycleViolation` sub-model: `cycle_id` (str), `invariant_field` (str),
  `violating_element` (str -- node_id or edge description),
  `violation_type` (str -- "dropped" or "overwritten"), `severity`
  (ConstraintSeverity), `message` (str)
- Uses `ConfigDict(extra="forbid")`
- Properties: `critical_violations`, `warnings`, `advisories` (filtering
  across all violation lists by severity)

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py`


### Integration Points

#### REQ-12-014: Layer 2 Static Analysis Integration

**Priority:** P2
**Description:** The `GraphTopologyAnalyzer` integrates with Layer 2
(Schema Compatibility) by extending the linear "dangling reads / dead
writes" analysis to graph-aware path analysis. When a `ContextContract`
includes a `graph_topology`, the Layer 2 static analysis should use
`GraphTopologyAnalyzer` instead of the linear `_check_phase_graph()`.

**Acceptance Criteria:**
- `PreflightChecker._check_phase_graph()` detects when
  `contract.graph_topology` is not None and delegates to
  `GraphTopologyAnalyzer.analyze()`
- The `PreflightResult` includes graph-specific violation details when
  graph topology is present
- Linear contracts (no `graph_topology`) continue to use existing analysis
  unchanged
- No new dependencies introduced beyond existing contract infrastructure

**Affected Files:**
- `src/contextcore/contracts/preflight/checker.py`
- `src/contextcore/contracts/topology/analyzer.py`


#### REQ-12-015: Layer 3 Preflight Integration

**Priority:** P2
**Description:** The `PreflightChecker` must include graph topology
consistency checks when a `graph_topology` is present on the contract.
These checks run before any execution and verify that the graph structure
itself is valid.

**Acceptance Criteria:**
- Preflight verifies that all edges reference valid nodes
- Preflight verifies that merge point sources are reachable from entry
  nodes
- Preflight verifies that cycle invariant nodes form actual cycles in
  the edge graph (not just a declared list)
- Preflight verifies that every terminal node is reachable from at least
  one entry node
- Preflight detects disconnected subgraphs (nodes unreachable from any
  entry node) and reports as WARNING
- Results are merged into the existing `PreflightResult` model

**Affected Files:**
- `src/contextcore/contracts/preflight/checker.py`


#### REQ-12-016: Graceful Fallback for Linear Pipelines

**Priority:** P2
**Description:** Graph topology analysis must be entirely optional. When
`graph_topology` is absent from a `ContextContract`, all existing behavior
is preserved unchanged. No code path outside the topology module should
fail or behave differently when graph topology is not configured.

**Acceptance Criteria:**
- `ContextContract` without `graph_topology` parses identically to before
- `PreflightChecker.check()` produces identical results for linear
  contracts
- No import errors if `topology/` module files are missing (lazy import
  or guarded import)
- Existing 62 propagation tests and all preflight tests pass without
  modification

**Affected Files:**
- `src/contextcore/contracts/propagation/schema.py`
- `src/contextcore/contracts/preflight/checker.py`


### OTel Emission

#### REQ-12-017: OTel Span Events for Topology Analysis

**Priority:** P2
**Description:** Emit OTel span events for graph topology analysis
results, following the `_HAS_OTEL` guard and `_add_span_event()` pattern
established in `propagation/otel.py`.

**Acceptance Criteria:**
- `emit_graph_analysis_result(result: GraphAnalysisResult)` emits a
  summary span event with attributes:
  - `context.graph.graph_id`
  - `context.graph.paths_enumerated`
  - `context.graph.path_violations_count`
  - `context.graph.merge_conflicts_count`
  - `context.graph.cycle_violations_count`
  - `context.graph.passed`
- `emit_path_violation(violation: PathViolation)` emits per-violation
  events with the path, node, and missing field
- `emit_merge_conflict(conflict: MergeConflict)` emits per-conflict events
- `emit_cycle_violation(violation: CycleViolation)` emits per-violation
  events
- All functions are guarded by `_HAS_OTEL` and degrade to logging when
  OTel is not installed
- Event names follow the `context.graph.*` namespace

**Affected Files:**
- `src/contextcore/contracts/topology/otel.py` (new)


#### REQ-12-018: OTel Attributes for Graph Topology

**Priority:** P3
**Description:** Define semantic convention attributes for graph topology
analysis results. These attributes enable TraceQL queries for topology
violations.

**Acceptance Criteria:**
- Attributes follow existing `context.*` namespace in
  `docs/semantic-conventions.md`
- Defined attributes:
  - `context.graph.graph_id` (string) -- the graph topology identifier
  - `context.graph.path_count` (int) -- number of enumerated paths
  - `context.graph.merge_point_count` (int) -- number of merge points
  - `context.graph.cycle_count` (int) -- number of declared cycles
  - `context.graph.analysis_passed` (bool) -- overall pass/fail
  - `context.graph.violation_type` (string) -- "path" | "merge" | "cycle"
  - `context.graph.violation_path` (string) -- comma-separated node_ids
    of the violating path
- TraceQL example queries documented:
  ```
  { span.context.graph.analysis_passed = false }
  { span.context.graph.violation_type = "merge" }
  ```

**Affected Files:**
- `docs/semantic-conventions.md`
- `src/contextcore/contracts/topology/otel.py`


### Edge Cases and Robustness

#### REQ-12-019: Diamond Dependency Handling

**Priority:** P2
**Description:** Handle diamond-shaped subgraphs where two paths diverge
from a common ancestor and reconverge at a common descendant. The analyzer
must correctly track field availability along both branches and apply
merge policies at the reconvergence point.

**Acceptance Criteria:**
- Diamond pattern (A -> B, A -> C, B -> D, C -> D) is correctly enumerated
  as two paths: A-B-D and A-C-D
- Fields produced by A are available on both paths (unless dropped by an
  edge)
- Fields produced by B are only available on the A-B-D path
- Fields produced by C are only available on the A-C-D path
- Node D's `requires` are checked against the merge policy if D is a
  declared merge point
- If D is NOT a declared merge point but has multiple incoming edges, the
  analyzer emits a WARNING suggesting a merge point declaration

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py`


#### REQ-12-020: Nested Cycle Detection

**Priority:** P2
**Description:** Handle graphs containing cycles within cycles (nested
loops). Each cycle level must have its own invariant declaration. The
analyzer must track which cycle scope applies at each depth.

**Acceptance Criteria:**
- Cycles are detected using topological sort failure or back-edge
  detection in DFS
- Declared `CycleInvariant` entries are matched to detected cycles
- A detected cycle without a matching `CycleInvariant` is reported as a
  WARNING (undeclared cycle)
- Invariant fields from an outer cycle are implicitly invariant in inner
  cycles (invariant inheritance)
- The analyzer reports cycle nesting depth in the analysis result

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py`


#### REQ-12-021: Path Explosion Mitigation

**Priority:** P2
**Description:** Graphs with high branching factors can produce an
exponential number of paths. The analyzer must handle this gracefully
without exhausting memory or CPU.

**Acceptance Criteria:**
- Configurable `max_paths` parameter on `GraphTopologyAnalyzer` (default
  1000)
- When path count exceeds `max_paths`, the analyzer:
  1. Logs a WARNING with the actual path count and the limit
  2. Analyzes only the first `max_paths` paths (deterministic ordering by
     path length, then lexicographic node_id order)
  3. Sets a `paths_truncated` flag on the `GraphAnalysisResult`
  4. Reports an ADVISORY violation indicating incomplete analysis
- Time complexity for path enumeration is O(paths * path_length), not
  O(2^n) for worst case -- achieved by bounding cycle unrolling and using
  max_paths cutoff

**Affected Files:**
- `src/contextcore/contracts/topology/analyzer.py`

---

## Contract Schema

The full YAML contract schema for graph topology, embedded within a
`ContextContract`:

```yaml
schema_version: "0.2.0"
pipeline_id: "retrieval_augmented_generation"
description: "RAG pipeline with complexity-based routing"

# Standard linear phase contracts (coexist with graph topology)
phases:
  classify:
    description: "Classify input domain and complexity"
    exit:
      required:
        - name: domain
          severity: blocking
        - name: complexity_tier
          severity: blocking

  retrieve_simple:
    description: "Simple keyword-based retrieval"
    entry:
      required:
        - name: domain
          severity: blocking
    exit:
      required:
        - name: retrieved_context
          severity: blocking

  retrieve_complex:
    description: "Multi-hop retrieval with confidence scoring"
    entry:
      required:
        - name: domain
          severity: blocking
        - name: complexity_tier
          severity: blocking
    exit:
      required:
        - name: retrieved_context
          severity: blocking
        - name: retrieval_confidence
          severity: warning

  generate:
    description: "Generate output from retrieved context"
    entry:
      required:
        - name: retrieved_context
          severity: blocking
      enrichment:
        - name: retrieval_confidence
          severity: advisory

# Graph topology overlay (NEW)
graph_topology:
  graph_id: "retrieval_augmented_generation"
  description: "RAG pipeline with complexity-based branching"

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
      drops: ["complexity_tier"]

    - from: classify
      to: retrieve_complex
      condition: "complexity_tier in ['medium', 'high']"
      preserves: ["domain", "complexity_tier"]

    - from: retrieve_simple
      to: generate
      preserves: ["retrieved_context"]

    - from: retrieve_complex
      to: generate
      preserves: ["retrieved_context", "retrieval_confidence"]

  merge_points:
    - node: generate
      sources: [retrieve_simple, retrieve_complex]
      merge_policy:
        retrieved_context: "required_from_any"
        retrieval_confidence: "optional"

  cycle_invariants:
    - cycle_id: "reasoning_loop"
      nodes: ["reason", "tool_call", "evaluate"]
      max_iterations: 5
      invariant_fields: ["task_id", "project_id", "session_id"]
      description: "Core identity fields must survive all loop iterations"

# Standard propagation chains (can reference graph nodes)
propagation_chains:
  - chain_id: "domain_to_generation"
    source:
      phase: classify
      field: domain
    destination:
      phase: generate
      field: domain
    severity: warning
```

---

## Integration Points

### How Graph Topology Fits the Existing 7-Layer Architecture

Graph topology does NOT add a new layer. It adds a new **contract type**
that plugs into existing Layers 2 and 3.

```
Layer 7: Regression Prevention
  |   (no change -- regression gates can use graph analysis results)
Layer 6: Observability & Alerting
  |   (alerts on graph.analysis_passed = false)
Layer 5: Post-Execution Validation
  |   (no change -- post-exec can validate field presence on actual path)
Layer 4: Runtime Boundary Checks
  |   (merge policy enforcement at runtime merge points)
Layer 3: Pre-Flight Verification          <-- EXTENDED
  |   (graph topology consistency checks before execution)
Layer 2: Static Analysis                  <-- EXTENDED
  |   (path-sensitive propagation analysis replaces linear analysis)
Layer 1: Context Contracts (Declarations) <-- EXTENDED
  |   (GraphTopologySpec as optional field on ContextContract)
```

### Relationship to Existing Components

| Component | Integration |
|-----------|-------------|
| `ContextContract` | Gains optional `graph_topology` field |
| `PreflightChecker` | Delegates to `GraphTopologyAnalyzer` when graph present |
| `BoundaryValidator` | Unchanged -- validates per-phase boundaries regardless of topology |
| `PropagationTracker` | Unchanged -- tracks field provenance regardless of topology |
| `PropagationChainSpec` | Can reference graph nodes as source/destination phases |
| `emit_*_result()` | New `emit_graph_analysis_result()` follows same pattern |

### Relationship to Other Concerns

| Concern | Composability |
|---------|--------------|
| Concern 9 (Quality) | Quality thresholds can vary per-path; merge policy can include quality preference |
| Concern 10 (Checkpoint) | Checkpoint/resume at a graph node must validate incoming edges, not just phase order |
| Concern 11 (Config Evolution) | Graph structure itself can evolve; node/edge addition is additive, removal is breaking |
| Concern 13 (Evaluation Gate) | Evaluation can be required at merge points before propagation continues |

---

## Test Requirements

### Unit Tests

| Test Category | Count | Description |
|---------------|-------|-------------|
| GraphNode model | 5 | Validation, forbid extra, duplicate field rejection, serialization |
| GraphEdge model | 5 | Validation, preserves/drops conflict, from/to aliases |
| MergePolicy enum | 2 | All values present, string serialization |
| MergePoint model | 4 | Validation, min sources, policy field validation |
| CycleInvariant model | 4 | Validation, min nodes, max_iterations >= 1 |
| GraphTopologySpec model | 6 | Validation, node reference checks, YAML round-trip |
| ContextContract extension | 3 | With/without graph_topology, backward compat |
| Path enumeration | 8 | Linear, branching, diamond, cycle with bound, disconnected, entry/terminal detection |
| Per-path propagation | 6 | All fields available, missing on one path, edge drops, edge preserves filter |
| Merge conflict detection | 5 | No conflict, conflict without policy, conflict with policy, dead policy, required_from_all failure |
| Cycle invariant verification | 5 | Invariant preserved, dropped by node, dropped by edge, overwritten by node, nested cycles |
| OTel emission | 4 | With OTel, without OTel, summary event, per-violation event |
| Path explosion | 3 | Under limit, at limit, over limit with truncation |
| Integration with PreflightChecker | 4 | Linear fallback, graph delegation, mixed violations, empty graph |
| **Total** | **~64** | |

### Integration Tests

- End-to-end: load YAML with graph topology, run preflight, verify
  graph-aware violations are detected
- Backward compatibility: load YAML without graph topology, verify
  existing preflight behavior is unchanged
- Mixed mode: load YAML with both phases and graph topology, verify both
  are analyzed

### Property-Based Tests (Optional)

- Generate random graph topologies with Hypothesis; verify that the
  analyzer always terminates, never raises unhandled exceptions, and
  produces a valid `GraphAnalysisResult`

---

## Non-Requirements

The following are explicitly out of scope for Concern 12:

1. **Runtime graph execution** -- Graph topology analysis is static
   (design-time / preflight). Runtime execution of graph-based workflows
   is the responsibility of the orchestration framework (LangGraph,
   Haystack, CrewAI). ContextCore validates the contract, not the
   execution.

2. **Condition expression evaluation** -- Edge conditions (e.g.,
   `"complexity_tier == 'low'"`) are treated as opaque strings for
   documentation purposes. The analyzer does NOT evaluate conditions to
   determine which paths are feasible. All paths are assumed feasible.

3. **Dynamic graph modification** -- The graph topology is declared
   statically in YAML. Runtime graph mutations (adding/removing nodes or
   edges during execution) are not modeled.

4. **Weighted path analysis** -- No probability or frequency weighting
   on edges. All paths are treated as equally likely for analysis purposes.

5. **Cross-graph propagation** -- Propagation between two separate graph
   topologies (e.g., a pipeline that calls a sub-pipeline) is not
   addressed. Cross-graph contracts are a future concern.

6. **Merge value resolution** -- The `MergePolicy` declares the
   *strategy* for resolving merge conflicts. The actual value resolution
   (choosing which branch's value wins) is a runtime concern handled by
   the orchestration framework. The analyzer only verifies that a policy
   IS declared, not that it produces correct values.

7. **Graph visualization** -- Rendering the graph topology as a visual
   diagram is not in scope. The contract is YAML; visualization is a
   separate tooling concern.

8. **Backward edge analysis for data flow** -- The analyzer walks
   forward from entry to terminal nodes. Backward analysis (e.g., "which
   nodes can influence this field?") is not implemented in the initial
   version.

---

## References

- Ball, T. & Rajamani, S.K. (2001). *Automatically Validating Temporal
  Safety Properties of Interfaces*. SPIN. -- Path-sensitive verification
- [Context Correctness by Construction](../CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)
  -- Parent design document
- [Context Correctness Extensions](../CONTEXT_CORRECTNESS_EXTENSIONS.md)
  -- Concern 12 definition
- [LangGraph, AutoGen, CrewAI Comparison](../../framework-comparisons/FRAMEWORK_COMPARISON_LANGGRAPH_AUTOGEN_CREWAI.md)
  -- Framework evidence for graph execution patterns
- [Propagation Schema](../../../src/contextcore/contracts/propagation/schema.py)
  -- Existing `ContextContract` model to extend
- [Preflight Checker](../../../src/contextcore/contracts/preflight/checker.py)
  -- Existing `PreflightChecker` to integrate with
