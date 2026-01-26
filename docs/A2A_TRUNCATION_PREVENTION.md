# A2A Truncation Prevention via Span-Based Coordination

*Design document for preventing LLM output truncation through ContextCore span-based communication.*

## Problem Statement

When Agent A requests code generation from Agent B (via handoff), the generated code may be silently truncated due to LLM token limits. Current validation happens **after generation** when damage may already be done.

**Current Flow (Reactive):**
```
Agent A → Handoff Request → Agent B → Generate → [TRUNCATION] → Integrate → Validate → FAIL
                                                    ↑
                                               Too late!
```

**Desired Flow (Proactive):**
```
Agent A → Handoff Request → Agent B → Validate Size → [TOO BIG] → Decompose → Generate Chunks → Verify → Complete
                                         ↓
                                    [OK SIZE] → Generate → Verify → Complete
```

## Design: Span-Based Generation Contracts

### 1. Extended ExpectedOutput with Size Constraints

Add size estimation and verification to handoff contracts:

```python
@dataclass
class ExpectedOutput:
    """Expected response format for a handoff."""
    type: str
    fields: list[str]

    # NEW: Size constraints
    max_lines: Optional[int] = None        # Max lines of code (150 = safe)
    max_tokens: Optional[int] = None       # Max token estimate
    completeness_markers: list[str] = None # Required markers (e.g., ["__all__", "def main"])

    # NEW: Chunking support
    allows_chunking: bool = True           # Can response be split?
    chunk_correlation_id: Optional[str] = None  # Parent for correlated chunks
```

### 2. Pre-Generation Validation Span

Before generating, the receiving agent emits a validation span:

```python
class CodeGenerationReceiver:
    def process_handoff(self, handoff: Handoff):
        with self.tracer.start_as_current_span("code_generation.preflight") as span:
            # Estimate output size
            estimated_lines = self._estimate_lines(handoff.task, handoff.inputs)
            estimated_tokens = estimated_lines * 3  # ~3 tokens per line

            span.set_attribute("gen_ai.code.estimated_lines", estimated_lines)
            span.set_attribute("gen_ai.code.estimated_tokens", estimated_tokens)
            span.set_attribute("gen_ai.code.max_lines_allowed", handoff.expected_output.max_lines or 500)

            # Decision: Generate or Decompose?
            if estimated_lines > (handoff.expected_output.max_lines or 150):
                span.set_attribute("gen_ai.code.action", "decompose")
                span.add_event("preflight_decision", {
                    "decision": "DECOMPOSE_REQUIRED",
                    "reason": f"Estimated {estimated_lines} lines exceeds safe limit",
                    "suggested_chunks": self._suggest_decomposition(handoff)
                })
                return self._request_decomposition(handoff)
            else:
                span.set_attribute("gen_ai.code.action", "generate")
                return self._generate_code(handoff)
```

### 3. Chunked Generation with Span Correlation

When decomposition is needed, emit correlated spans:

```python
class ChunkedCodeGenerator:
    def generate_chunked(self, handoff: Handoff, chunks: list[ChunkSpec]) -> str:
        parent_trace_id = trace.get_current_span().get_span_context().trace_id
        chunk_results = []

        for i, chunk in enumerate(chunks):
            with self.tracer.start_as_current_span(f"code_generation.chunk_{i}") as span:
                span.set_attribute("gen_ai.code.chunk_index", i)
                span.set_attribute("gen_ai.code.chunk_total", len(chunks))
                span.set_attribute("gen_ai.code.chunk_target", chunk.target_file)
                span.set_attribute("gen_ai.code.parent_handoff", handoff.id)

                result = self._generate_chunk(chunk)

                # Verify chunk completeness
                issues = detect_incomplete_file(result.content, chunk.target_file)
                if issues:
                    span.set_status(StatusCode.ERROR, f"Chunk truncated: {issues}")
                    span.set_attribute("gen_ai.code.truncated", True)
                    raise ChunkTruncationError(chunk.target_file, issues)

                span.set_attribute("gen_ai.code.truncated", False)
                span.set_attribute("gen_ai.code.actual_lines", result.line_count)
                chunk_results.append(result)

        return self._assemble_chunks(chunk_results)
```

### 4. Completion Verification Protocol

Both parties verify completeness before marking COMPLETED:

```yaml
# Handoff completion verification (as span events)

# Agent B (generator) emits:
- event: "generation.complete"
  attributes:
    gen_ai.code.actual_lines: 142
    gen_ai.code.exports_defined: ["Foo", "Bar", "baz"]
    gen_ai.code.completeness_check: "PASSED"
    gen_ai.code.checksum: "sha256:abc123..."

# Agent A (requester) verifies before accepting:
- event: "verification.complete"
  attributes:
    gen_ai.code.exports_expected: ["Foo", "Bar", "baz"]
    gen_ai.code.exports_found: ["Foo", "Bar", "baz"]
    gen_ai.code.syntax_valid: true
    gen_ai.code.verification_result: "ACCEPTED"
```

### 5. TraceQL Queries for Monitoring

**Find truncated generations:**
```traceql
{ span.gen_ai.code.truncated = true }
| select(
    resource.project.id,
    span.gen_ai.code.estimated_lines,
    span.gen_ai.code.actual_lines,
    span.handoff.capability_id
)
```

**Find handoffs that required decomposition:**
```traceql
{ span.gen_ai.code.action = "decompose" }
| select(
    span.handoff.id,
    span.gen_ai.code.estimated_lines,
    span.gen_ai.code.suggested_chunks
)
```

**Track chunk completion rates:**
```traceql
{ name =~ "code_generation.chunk_.*" }
| by(span.gen_ai.code.parent_handoff)
| select(
    count(),
    max(span.gen_ai.code.chunk_total),
    sum(span.gen_ai.code.truncated)
)
```

---

## Implementation: CodeGenerationHandoff Protocol

### New Handoff Type for Code Generation

```python
from dataclasses import dataclass
from typing import Optional
from contextcore.agent.handoff import HandoffManager, ExpectedOutput, Handoff

@dataclass
class CodeGenerationSpec:
    """Specification for code generation handoff."""
    target_file: str
    description: str
    context_files: list[str]  # Files to read for context

    # Size constraints
    max_lines: int = 150
    max_tokens: int = 500

    # Completeness requirements
    required_exports: Optional[list[str]] = None
    required_imports: Optional[list[str]] = None
    must_have_docstring: bool = True

    # Chunking
    allows_decomposition: bool = True


class CodeGenerationHandoff:
    """
    Handoff manager specialized for code generation with truncation prevention.

    Example:
        handoff = CodeGenerationHandoff(project_id="myproject", agent_id="orchestrator")

        result = handoff.request_code(
            to_agent="code-generator",
            spec=CodeGenerationSpec(
                target_file="src/mymodule.py",
                description="Implement the FooBar class with methods x, y, z",
                max_lines=150,
                required_exports=["FooBar"],
            )
        )

        if result.status == HandoffStatus.COMPLETED:
            # Code verified as complete
            pass
        elif result.decomposition_required:
            # Agent suggested decomposition - handle chunks
            pass
    """

    def __init__(self, project_id: str, agent_id: str, **kwargs):
        self._manager = HandoffManager(project_id, agent_id, **kwargs)
        self.tracer = trace.get_tracer("contextcore.code_generation")

    def request_code(
        self,
        to_agent: str,
        spec: CodeGenerationSpec,
        priority: HandoffPriority = HandoffPriority.NORMAL,
        timeout_ms: int = 60000,
    ) -> "CodeGenerationResult":
        """
        Request code generation with proactive truncation prevention.
        """
        with self.tracer.start_as_current_span("code_generation.request") as span:
            span.set_attribute("gen_ai.code.target_file", spec.target_file)
            span.set_attribute("gen_ai.code.max_lines", spec.max_lines)
            span.set_attribute("gen_ai.code.allows_decomposition", spec.allows_decomposition)

            expected_output = ExpectedOutput(
                type="code",
                fields=["content", "exports", "imports"],
                max_lines=spec.max_lines,
                max_tokens=spec.max_tokens,
                completeness_markers=spec.required_exports or [],
                allows_chunking=spec.allows_decomposition,
            )

            result = self._manager.create_and_await(
                to_agent=to_agent,
                capability_id="generate_code",
                task=spec.description,
                inputs={
                    "target_file": spec.target_file,
                    "context_files": spec.context_files,
                    "required_exports": spec.required_exports,
                    "required_imports": spec.required_imports,
                    "must_have_docstring": spec.must_have_docstring,
                },
                expected_output=expected_output,
                priority=priority,
                timeout_ms=timeout_ms,
            )

            return CodeGenerationResult.from_handoff_result(result)
```

### Receiver-Side Validation

```python
class CodeGenerationCapability:
    """
    Capability handler for code generation with built-in truncation prevention.
    """

    def __init__(self, llm_client, tracer):
        self.llm = llm_client
        self.tracer = tracer
        self.safe_line_limit = 150  # Known safe limit for most LLMs

    def handle_handoff(self, handoff: Handoff) -> str:
        """Process code generation handoff with proactive validation."""

        # 1. Pre-flight: Estimate size
        with self.tracer.start_as_current_span("code_generation.preflight") as span:
            estimated = self._estimate_output_size(handoff)
            span.set_attribute("gen_ai.code.estimated_lines", estimated.lines)
            span.set_attribute("gen_ai.code.estimated_complexity", estimated.complexity)

            max_allowed = handoff.expected_output.max_lines or self.safe_line_limit

            if estimated.lines > max_allowed:
                span.add_event("size_exceeded", {
                    "estimated": estimated.lines,
                    "max_allowed": max_allowed,
                    "action": "decompose" if handoff.expected_output.allows_chunking else "reject"
                })

                if handoff.expected_output.allows_chunking:
                    return self._decompose_and_generate(handoff, estimated)
                else:
                    raise HandoffRejectedError(
                        f"Request would produce ~{estimated.lines} lines, "
                        f"exceeds limit of {max_allowed}. Enable chunking or reduce scope."
                    )

        # 2. Generate with monitoring
        with self.tracer.start_as_current_span("code_generation.generate") as span:
            result = self._generate_code(handoff)

            span.set_attribute("gen_ai.code.actual_lines", result.line_count)
            span.set_attribute("gen_ai.code.tokens_used", result.tokens_used)

        # 3. Verify completeness
        with self.tracer.start_as_current_span("code_generation.verify") as span:
            issues = self._verify_completeness(result, handoff.expected_output)

            if issues:
                span.set_status(StatusCode.ERROR)
                span.set_attribute("gen_ai.code.truncated", True)
                span.set_attribute("gen_ai.code.issues", json.dumps(issues))
                raise CodeTruncatedError(issues)

            span.set_attribute("gen_ai.code.truncated", False)
            span.set_attribute("gen_ai.code.verification", "PASSED")

        return result.content

    def _verify_completeness(
        self,
        result: GeneratedCode,
        expected: ExpectedOutput
    ) -> list[str]:
        """Verify generated code is complete."""
        issues = []

        # Check required exports
        if expected.completeness_markers:
            missing = set(expected.completeness_markers) - set(result.exports)
            if missing:
                issues.append(f"Missing required exports: {missing}")

        # Check syntax
        try:
            compile(result.content, result.target_file, 'exec')
        except SyntaxError as e:
            issues.append(f"Syntax error: {e}")

        # Check __all__ consistency
        all_exports = self._extract_all_exports(result.content)
        defined = self._extract_definitions(result.content)
        missing_defs = set(all_exports) - set(defined)
        if missing_defs:
            issues.append(f"__all__ references undefined: {missing_defs}")

        return issues
```

---

## Dashboard: Code Generation Health

Create a Grafana dashboard to monitor code generation health:

### Panel 1: Truncation Rate
```traceql
{ name =~ "code_generation.*" && span.gen_ai.code.truncated != nil }
| rate() by (span.gen_ai.code.truncated)
```

### Panel 2: Decomposition Decisions
```traceql
{ name = "code_generation.preflight" }
| select(span.gen_ai.code.action)
| count() by (span.gen_ai.code.action)
```

### Panel 3: Size Estimation Accuracy
```traceql
{ name = "code_generation.generate" }
| select(
    span.gen_ai.code.estimated_lines,
    span.gen_ai.code.actual_lines
)
```

### Panel 4: Failed Verifications
```traceql
{ name = "code_generation.verify" && status = error }
| select(span.gen_ai.code.issues)
```

---

## Benefits

1. **Proactive Prevention**: Size check happens BEFORE generation, not after
2. **Observable**: All decisions recorded as spans, queryable via TraceQL
3. **Human Visibility**: Dashboards show truncation rates, decomposition frequency
4. **A2A Coordination**: Agents negotiate size limits through handoff contracts
5. **Graceful Degradation**: Large requests decompose instead of failing
6. **Audit Trail**: Every truncation event is traceable to specific handoff

## Anti-Patterns Prevented

| Anti-Pattern | How Prevented |
|--------------|---------------|
| Warn-Then-Proceed | Verification is BLOCKING, not advisory |
| Generate-Complete-Module | Pre-flight estimation triggers decomposition |
| Post-Hoc Validation Only | Pre-flight span emits before generation |
| Silent Truncation | `gen_ai.code.truncated` attribute always set |
| Lost Context on Failure | All decisions preserved in trace |

---

## Implementation Checklist

- [ ] Add `max_lines`, `max_tokens`, `completeness_markers` to ExpectedOutput
- [ ] Implement pre-flight span emission in CodeGenerationCapability
- [ ] Add size estimation heuristics
- [ ] Implement chunked generation with correlation
- [ ] Add verification span with completeness check
- [ ] Create Grafana dashboard for monitoring
- [ ] Add TraceQL queries to CLAUDE.md
- [ ] Document in agent-communication-protocol.md

---

*Design Version: 1.0 | Created: 2026-01-26*
