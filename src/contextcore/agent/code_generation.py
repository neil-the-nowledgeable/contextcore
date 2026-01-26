"""
Code Generation Handoff with Proactive Truncation Prevention.

This module provides specialized handoff management for code generation tasks,
with built-in size estimation and validation to prevent LLM output truncation.

The key insight is that truncation prevention must happen BEFORE generation,
not after. This module implements a span-based coordination protocol where:

1. Requesting agent specifies size constraints in the handoff
2. Receiving agent estimates output size before generation
3. If estimate exceeds limit, decomposition is negotiated via span events
4. All decisions are recorded as spans for observability

Example (requesting agent):
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

Example (receiving agent):
    capability = CodeGenerationCapability(llm_client=client)

    for handoff in receiver.poll_handoffs(project_id="myproject"):
        if handoff.capability_id == "generate_code":
            result = capability.handle_handoff(handoff)
            receiver.complete(handoff.id, project_id="myproject", result_trace_id=result.trace_id)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from contextcore.agent.handoff import (
    ExpectedOutput,
    Handoff,
    HandoffManager,
    HandoffPriority,
    HandoffResult,
    HandoffStatus,
)
from contextcore.contracts.timeouts import HANDOFF_DEFAULT_TIMEOUT_MS

logger = logging.getLogger(__name__)


class CodeGenerationAction(str, Enum):
    """Pre-flight decision actions."""
    GENERATE = "generate"
    DECOMPOSE = "decompose"
    REJECT = "reject"


class VerificationResult(str, Enum):
    """Verification outcome."""
    PASSED = "passed"
    FAILED_TRUNCATION = "failed_truncation"
    FAILED_SYNTAX = "failed_syntax"
    FAILED_MISSING_EXPORTS = "failed_missing_exports"
    FAILED_INCOMPLETE = "failed_incomplete"


@dataclass
class CodeGenerationSpec:
    """Specification for code generation handoff.

    Defines what code to generate along with size constraints
    that enable proactive truncation prevention.

    Attributes:
        target_file: Path to the file to generate/modify
        description: Description of what code to generate
        context_files: Files to read for context
        max_lines: Maximum lines of code (150 = safe for most LLMs)
        max_tokens: Maximum token estimate for output
        required_exports: Exports that must be defined (e.g., class names, functions)
        required_imports: Imports that must be present
        must_have_docstring: Whether module docstring is required
        allows_decomposition: Whether the request can be split into chunks
    """
    target_file: str
    description: str
    context_files: list[str] = field(default_factory=list)

    # Size constraints
    max_lines: int = 150
    max_tokens: int = 500

    # Completeness requirements
    required_exports: Optional[list[str]] = None
    required_imports: Optional[list[str]] = None
    must_have_docstring: bool = True

    # Chunking
    allows_decomposition: bool = True


@dataclass
class ChunkSpec:
    """Specification for a single chunk of a decomposed generation."""
    index: int
    total_chunks: int
    target_file: str
    description: str
    parent_handoff_id: str
    expected_exports: list[str] = field(default_factory=list)


@dataclass
class SizeEstimate:
    """Estimated size of generated output."""
    lines: int
    tokens: int
    complexity: str  # "low", "medium", "high"
    confidence: float  # 0.0 to 1.0
    reasoning: str


@dataclass
class GeneratedCode:
    """Result of code generation."""
    content: str
    target_file: str
    line_count: int
    tokens_used: int
    exports: list[str]
    imports: list[str]


@dataclass
class CodeGenerationResult:
    """Result of a code generation handoff.

    Extends HandoffResult with code-specific information including
    decomposition details and verification status.
    """
    handoff_id: str
    status: HandoffStatus
    result_trace_id: Optional[str] = None
    error_message: Optional[str] = None

    # Code-specific fields
    code_content: Optional[str] = None
    line_count: Optional[int] = None
    exports_found: Optional[list[str]] = None
    verification_result: Optional[VerificationResult] = None

    # Decomposition info
    decomposition_required: bool = False
    chunk_count: Optional[int] = None
    chunk_ids: Optional[list[str]] = None

    @classmethod
    def from_handoff_result(
        cls,
        result: HandoffResult,
        code_content: Optional[str] = None,
        decomposition_info: Optional[dict] = None,
    ) -> "CodeGenerationResult":
        """Create from a base HandoffResult."""
        return cls(
            handoff_id=result.handoff_id,
            status=result.status,
            result_trace_id=result.result_trace_id,
            error_message=result.error_message,
            code_content=code_content,
            decomposition_required=decomposition_info is not None,
            chunk_count=decomposition_info.get("chunk_count") if decomposition_info else None,
            chunk_ids=decomposition_info.get("chunk_ids") if decomposition_info else None,
        )


class HandoffRejectedError(Exception):
    """Raised when a handoff is rejected due to size constraints."""
    pass


class CodeTruncatedError(Exception):
    """Raised when generated code appears truncated."""
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(f"Code truncation detected: {'; '.join(issues)}")


class CodeGenerationHandoff:
    """
    Handoff manager specialized for code generation with truncation prevention.

    This class wraps HandoffManager with code-specific functionality:
    - Size constraints in expected_output
    - Pre-flight validation spans
    - Decomposition coordination

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

    # Default safe limits for LLM output
    DEFAULT_MAX_LINES = 150
    DEFAULT_MAX_TOKENS = 500
    TOKENS_PER_LINE = 3  # Approximate

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        namespace: str = "default",
        storage_type: Optional[str] = None,
        kubeconfig: Optional[str] = None,
    ):
        """Initialize code generation handoff manager.

        Args:
            project_id: Project identifier
            agent_id: This agent's identifier
            namespace: Kubernetes namespace (for K8s storage)
            storage_type: Storage backend type (auto-detected if None)
            kubeconfig: Path to kubeconfig (for K8s storage)
        """
        self.project_id = project_id
        self.agent_id = agent_id
        self._manager = HandoffManager(
            project_id=project_id,
            agent_id=agent_id,
            namespace=namespace,
            storage_type=storage_type,
            kubeconfig=kubeconfig,
        )
        self.tracer = trace.get_tracer("contextcore.code_generation")
        logger.info(
            f"CodeGenerationHandoff initialized for project {project_id}, agent {agent_id}"
        )

    def request_code(
        self,
        to_agent: str,
        spec: CodeGenerationSpec,
        priority: HandoffPriority = HandoffPriority.NORMAL,
        timeout_ms: int = HANDOFF_DEFAULT_TIMEOUT_MS,
    ) -> CodeGenerationResult:
        """
        Request code generation with proactive truncation prevention.

        Creates a handoff with size constraints that the receiving agent
        should validate before generation.

        Args:
            to_agent: Target agent ID
            spec: Code generation specification
            priority: Handoff priority
            timeout_ms: Timeout for completion

        Returns:
            CodeGenerationResult with status and any decomposition info
        """
        with self.tracer.start_as_current_span(
            "code_generation.request",
            kind=SpanKind.PRODUCER,
        ) as span:
            span.set_attribute("gen_ai.code.target_file", spec.target_file)
            span.set_attribute("gen_ai.code.max_lines", spec.max_lines)
            span.set_attribute("gen_ai.code.max_tokens", spec.max_tokens)
            span.set_attribute("gen_ai.code.allows_decomposition", spec.allows_decomposition)

            if spec.required_exports:
                span.set_attribute("gen_ai.code.required_exports", json.dumps(spec.required_exports))

            # Build expected output with size constraints
            expected_output = ExpectedOutput(
                type="code",
                fields=["content", "exports", "imports"],
                max_lines=spec.max_lines,
                max_tokens=spec.max_tokens,
                completeness_markers=spec.required_exports or [],
                allows_chunking=spec.allows_decomposition,
            )

            # Create and await the handoff
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
                    "max_lines": spec.max_lines,
                    "max_tokens": spec.max_tokens,
                },
                expected_output=expected_output,
                priority=priority,
                timeout_ms=timeout_ms,
            )

            span.set_attribute("gen_ai.code.handoff_status", result.status.value)

            return CodeGenerationResult.from_handoff_result(result)

    def request_code_async(
        self,
        to_agent: str,
        spec: CodeGenerationSpec,
        priority: HandoffPriority = HandoffPriority.NORMAL,
        timeout_ms: int = HANDOFF_DEFAULT_TIMEOUT_MS,
    ) -> str:
        """
        Request code generation without waiting for result.

        Returns handoff ID for later status checking.
        """
        with self.tracer.start_as_current_span(
            "code_generation.request_async",
            kind=SpanKind.PRODUCER,
        ) as span:
            span.set_attribute("gen_ai.code.target_file", spec.target_file)
            span.set_attribute("gen_ai.code.max_lines", spec.max_lines)

            expected_output = ExpectedOutput(
                type="code",
                fields=["content", "exports", "imports"],
                max_lines=spec.max_lines,
                max_tokens=spec.max_tokens,
                completeness_markers=spec.required_exports or [],
                allows_chunking=spec.allows_decomposition,
            )

            handoff_id = self._manager.create_handoff(
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

            span.set_attribute("gen_ai.code.handoff_id", handoff_id)
            return handoff_id

    def get_result(self, handoff_id: str) -> CodeGenerationResult:
        """Get result of a previously created handoff."""
        result = self._manager.get_handoff_status(handoff_id)
        return CodeGenerationResult.from_handoff_result(result)


class CodeGenerationCapability:
    """
    Capability handler for code generation with built-in truncation prevention.

    This class implements the receiver side of code generation handoffs,
    with pre-flight size validation and post-generation verification.

    Example:
        capability = CodeGenerationCapability(
            llm_client=my_llm_client,
            generate_fn=my_generation_function,
        )

        for handoff in receiver.poll_handoffs(project_id="myproject"):
            if handoff.capability_id == "generate_code":
                try:
                    result = capability.handle_handoff(handoff)
                    receiver.complete(handoff.id, project_id="myproject", result_trace_id=result.trace_id)
                except CodeTruncatedError as e:
                    receiver.fail(handoff.id, project_id="myproject", reason=str(e))
    """

    # Safe limits for most LLMs
    SAFE_LINE_LIMIT = 150
    SAFE_TOKEN_LIMIT = 500

    def __init__(
        self,
        generate_fn: Optional[Callable[[str, dict], str]] = None,
        estimate_fn: Optional[Callable[[str, dict], SizeEstimate]] = None,
    ):
        """Initialize capability handler.

        Args:
            generate_fn: Function to generate code (task, inputs) -> code_string
            estimate_fn: Function to estimate output size (task, inputs) -> SizeEstimate
        """
        self.generate_fn = generate_fn
        self.estimate_fn = estimate_fn
        self.tracer = trace.get_tracer("contextcore.code_generation")

    def handle_handoff(self, handoff: Handoff) -> GeneratedCode:
        """
        Process code generation handoff with proactive validation.

        1. Pre-flight: Estimate size and decide whether to generate or decompose
        2. Generate: If size OK, generate the code
        3. Verify: Check completeness before returning

        Args:
            handoff: The code generation handoff to process

        Returns:
            GeneratedCode with the result

        Raises:
            HandoffRejectedError: If size exceeds limit and chunking not allowed
            CodeTruncatedError: If generated code appears truncated
        """
        # Extract constraints from expected_output
        max_lines = handoff.expected_output.max_lines or self.SAFE_LINE_LIMIT
        max_tokens = handoff.expected_output.max_tokens or self.SAFE_TOKEN_LIMIT
        allows_chunking = handoff.expected_output.allows_chunking
        required_exports = handoff.expected_output.completeness_markers

        # 1. Pre-flight: Estimate size
        with self.tracer.start_as_current_span("code_generation.preflight") as span:
            estimated = self._estimate_output_size(handoff.task, handoff.inputs)

            span.set_attribute("gen_ai.code.estimated_lines", estimated.lines)
            span.set_attribute("gen_ai.code.estimated_tokens", estimated.tokens)
            span.set_attribute("gen_ai.code.estimated_complexity", estimated.complexity)
            span.set_attribute("gen_ai.code.estimation_confidence", estimated.confidence)
            span.set_attribute("gen_ai.code.max_lines_allowed", max_lines)

            if estimated.lines > max_lines:
                action = CodeGenerationAction.DECOMPOSE if allows_chunking else CodeGenerationAction.REJECT
                span.set_attribute("gen_ai.code.action", action.value)
                span.add_event("preflight_decision", {
                    "decision": action.value.upper(),
                    "reason": f"Estimated {estimated.lines} lines exceeds limit of {max_lines}",
                    "estimated_lines": estimated.lines,
                    "max_allowed": max_lines,
                })

                if action == CodeGenerationAction.REJECT:
                    raise HandoffRejectedError(
                        f"Request would produce ~{estimated.lines} lines, "
                        f"exceeds limit of {max_lines}. Enable chunking or reduce scope."
                    )
                else:
                    # TODO: Implement decomposition
                    logger.warning(
                        f"Decomposition required but not yet implemented. "
                        f"Estimated {estimated.lines} lines > {max_lines} limit."
                    )
                    # For now, proceed with generation and hope for the best
            else:
                span.set_attribute("gen_ai.code.action", CodeGenerationAction.GENERATE.value)

        # 2. Generate code
        with self.tracer.start_as_current_span("code_generation.generate") as span:
            content = self._generate_code(handoff.task, handoff.inputs)
            line_count = content.count('\n') + 1
            tokens_used = line_count * 3  # Rough estimate

            span.set_attribute("gen_ai.code.actual_lines", line_count)
            span.set_attribute("gen_ai.code.tokens_used", tokens_used)
            span.set_attribute("gen_ai.code.target_file", handoff.inputs.get("target_file", "unknown"))

        # 3. Verify completeness
        with self.tracer.start_as_current_span("code_generation.verify") as span:
            exports = self._extract_exports(content)
            imports = self._extract_imports(content)
            issues = self._verify_completeness(content, required_exports)

            span.set_attribute("gen_ai.code.exports_found", json.dumps(exports))
            span.set_attribute("gen_ai.code.imports_found", json.dumps(imports))

            if issues:
                span.set_status(Status(StatusCode.ERROR, f"Verification failed: {issues[0]}"))
                span.set_attribute("gen_ai.code.truncated", True)
                span.set_attribute("gen_ai.code.verification_issues", json.dumps(issues))
                raise CodeTruncatedError(issues)

            span.set_attribute("gen_ai.code.truncated", False)
            span.set_attribute("gen_ai.code.verification_result", VerificationResult.PASSED.value)

        return GeneratedCode(
            content=content,
            target_file=handoff.inputs.get("target_file", "unknown"),
            line_count=line_count,
            tokens_used=tokens_used,
            exports=exports,
            imports=imports,
        )

    def _estimate_output_size(self, task: str, inputs: dict) -> SizeEstimate:
        """Estimate the size of the generated output.

        Uses heuristics based on task description and inputs.
        """
        if self.estimate_fn:
            return self.estimate_fn(task, inputs)

        # Default heuristic estimation
        from contextcore.agent.size_estimation import SizeEstimator
        estimator = SizeEstimator()
        return estimator.estimate(task, inputs)

    def _generate_code(self, task: str, inputs: dict) -> str:
        """Generate code for the task."""
        if self.generate_fn:
            return self.generate_fn(task, inputs)

        # Placeholder - in real usage, this would call an LLM
        raise NotImplementedError(
            "No generate_fn provided. Please provide a code generation function."
        )

    def _extract_exports(self, content: str) -> list[str]:
        """Extract defined exports from code."""
        exports = []
        import ast
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    exports.append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    if not node.name.startswith('_'):
                        exports.append(node.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == '__all__':
                            if isinstance(node.value, ast.List):
                                for elt in node.value.elts:
                                    if isinstance(elt, ast.Constant):
                                        exports.append(elt.value)
        except SyntaxError:
            pass  # Will be caught in verification
        return exports

    def _extract_imports(self, content: str) -> list[str]:
        """Extract imports from code."""
        imports = []
        import ast
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except SyntaxError:
            pass
        return imports

    def _verify_completeness(
        self,
        content: str,
        required_exports: Optional[list[str]],
    ) -> list[str]:
        """Verify generated code is complete."""
        issues = []

        # Check required exports
        if required_exports:
            found_exports = set(self._extract_exports(content))
            missing = set(required_exports) - found_exports
            if missing:
                issues.append(f"Missing required exports: {missing}")

        # Check syntax
        try:
            compile(content, "<generated>", 'exec')
        except SyntaxError as e:
            issues.append(f"Syntax error at line {e.lineno}: {e.msg}")

        # Check for common truncation indicators
        truncation_checks = [
            # Unclosed string/docstring
            (content.count('"""') % 2 != 0, "Unclosed triple-quote string"),
            (content.count("'''") % 2 != 0, "Unclosed triple-quote string"),
            # Incomplete class/function
            (content.rstrip().endswith(':') and not content.rstrip().endswith('pass'), "Incomplete block ending with colon"),
            # Trailing ellipsis (common LLM truncation marker)
            (content.rstrip().endswith('...') and 'Ellipsis' not in content, "Ends with ellipsis (truncation marker)"),
        ]

        for condition, message in truncation_checks:
            if condition:
                issues.append(f"TRUNCATED: {message}")

        return issues
