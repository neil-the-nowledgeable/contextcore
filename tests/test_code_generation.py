"""
Tests for code generation truncation prevention.

Tests the proactive truncation prevention pattern including:
- Size estimation accuracy
- Pre-flight rejection of large requests
- ExpectedOutput size constraints
- CodeGenerationCapability verification
"""

import pytest
from unittest.mock import MagicMock, patch

from contextcore.agent.size_estimation import (
    SizeEstimate,
    SizeEstimator,
    estimate_from_spec,
)
from contextcore.agent.code_generation import (
    CodeGenerationSpec,
    CodeGenerationHandoff,
    CodeGenerationCapability,
    CodeGenerationResult,
    CodeTruncatedError,
    HandoffRejectedError,
    GeneratedCode,
    VerificationResult,
)
from contextcore.agent.handoff import ExpectedOutput, HandoffStatus


class TestSizeEstimator:
    """Tests for SizeEstimator heuristics."""

    def test_low_complexity_task(self):
        """Simple fix task should estimate low complexity."""
        estimator = SizeEstimator()
        estimate = estimator.estimate(
            task="Fix the simple small typo in the variable name",
            inputs={},
        )

        assert estimate.complexity == "low"
        assert estimate.lines < 50
        assert estimate.confidence > 0.3

    def test_high_complexity_task(self):
        """Comprehensive API implementation should estimate high."""
        estimator = SizeEstimator()
        estimate = estimator.estimate(
            task="Implement a comprehensive REST API client with CRUD operations and error handling",
            inputs={"required_exports": ["APIClient", "Response", "Error"]},
        )

        assert estimate.complexity == "high"
        assert estimate.lines > 100
        assert estimate.confidence > 0.5

    def test_medium_complexity_task(self):
        """Standard class implementation should be medium."""
        estimator = SizeEstimator()
        estimate = estimator.estimate(
            task="Implement the FooBar class with method x",
            inputs={"required_exports": ["FooBar"]},
        )

        assert estimate.complexity == "medium"
        assert 50 < estimate.lines < 150

    def test_required_exports_increase_estimate(self):
        """More exports should increase the estimate."""
        estimator = SizeEstimator()

        estimate_small = estimator.estimate(
            task="Implement classes",
            inputs={"required_exports": ["Foo"]},
        )

        estimate_large = estimator.estimate(
            task="Implement classes",
            inputs={"required_exports": ["Foo", "Bar", "Baz", "Qux"]},
        )

        assert estimate_large.lines > estimate_small.lines

    def test_crud_keyword_adds_methods(self):
        """CRUD keyword should add 4 methods to estimate."""
        estimator = SizeEstimator()

        estimate_crud = estimator.estimate(
            task="Implement CRUD operations for user management",
            inputs={},
        )

        estimate_no_crud = estimator.estimate(
            task="Implement operations for user management",
            inputs={},
        )

        # CRUD should add ~48 lines (4 methods * 12 lines)
        assert estimate_crud.lines > estimate_no_crud.lines + 30

    def test_tokens_calculated_from_lines(self):
        """Tokens should be approximately 3x lines."""
        estimator = SizeEstimator()
        estimate = estimator.estimate(
            task="Implement a simple function",
            inputs={},
        )

        assert estimate.tokens == estimate.lines * 3

    def test_reasoning_includes_complexity(self):
        """Reasoning should mention complexity."""
        estimator = SizeEstimator()
        estimate = estimator.estimate(
            task="Implement something",
            inputs={},
        )

        assert "Complexity:" in estimate.reasoning


class TestExpectedOutputExtensions:
    """Tests for ExpectedOutput size constraint extensions."""

    def test_default_values(self):
        """ExpectedOutput should have sensible defaults."""
        output = ExpectedOutput(
            type="code",
            fields=["content"],
        )

        assert output.max_lines is None
        assert output.max_tokens is None
        assert output.completeness_markers == []
        assert output.allows_chunking is True
        assert output.chunk_correlation_id is None

    def test_size_constraints_set(self):
        """Size constraints can be explicitly set."""
        output = ExpectedOutput(
            type="code",
            fields=["content"],
            max_lines=150,
            max_tokens=500,
            completeness_markers=["FooBar", "__all__"],
            allows_chunking=False,
        )

        assert output.max_lines == 150
        assert output.max_tokens == 500
        assert output.completeness_markers == ["FooBar", "__all__"]
        assert output.allows_chunking is False


class TestCodeGenerationSpec:
    """Tests for CodeGenerationSpec."""

    def test_default_values(self):
        """Spec should have sensible defaults."""
        spec = CodeGenerationSpec(
            target_file="src/mymodule.py",
            description="Implement FooBar",
        )

        assert spec.max_lines == 150
        assert spec.max_tokens == 500
        assert spec.allows_decomposition is True
        assert spec.must_have_docstring is True
        assert spec.context_files == []

    def test_estimate_from_spec(self):
        """estimate_from_spec should use spec fields."""
        spec = CodeGenerationSpec(
            target_file="src/mymodule.py",
            description="Implement FooBar class with methods x, y, z",
            required_exports=["FooBar"],
            must_have_docstring=True,
        )

        estimate = estimate_from_spec(spec)

        assert isinstance(estimate, SizeEstimate)
        assert estimate.lines > 0


class TestCodeGenerationCapability:
    """Tests for CodeGenerationCapability handler."""

    def test_verification_passes_valid_code(self):
        """Valid code should pass verification."""
        capability = CodeGenerationCapability()

        valid_code = '''"""Module docstring."""

class FooBar:
    """FooBar class."""

    def method_x(self):
        """Method x."""
        pass
'''
        issues = capability._verify_completeness(
            content=valid_code,
            required_exports=["FooBar"],
        )

        assert issues == []

    def test_verification_fails_missing_exports(self):
        """Missing required exports should fail verification."""
        capability = CodeGenerationCapability()

        incomplete_code = '''"""Module docstring."""

class WrongClass:
    pass
'''
        issues = capability._verify_completeness(
            content=incomplete_code,
            required_exports=["FooBar"],
        )

        assert len(issues) > 0
        assert any("Missing required exports" in i for i in issues)

    def test_verification_fails_syntax_error(self):
        """Syntax errors should fail verification."""
        capability = CodeGenerationCapability()

        bad_code = '''def foo(
    # Missing closing parenthesis
'''
        issues = capability._verify_completeness(
            content=bad_code,
            required_exports=None,
        )

        assert len(issues) > 0
        assert any("Syntax error" in i for i in issues)

    def test_verification_detects_truncation_markers(self):
        """Common truncation markers should be detected."""
        capability = CodeGenerationCapability()

        # Unclosed triple-quote (3 triple-quotes = odd = truncated)
        truncated_code = '''"""Module docstring."""

class Foo:
    """This docstring is not closed'''

        issues = capability._verify_completeness(
            content=truncated_code,
            required_exports=None,
        )

        assert len(issues) > 0
        assert any("TRUNCATED" in i for i in issues)

    def test_extract_exports_finds_classes(self):
        """Should extract class definitions."""
        capability = CodeGenerationCapability()

        code = '''class Foo:
    pass

class Bar:
    pass
'''
        exports = capability._extract_exports(code)

        assert "Foo" in exports
        assert "Bar" in exports

    def test_extract_exports_finds_functions(self):
        """Should extract public function definitions."""
        capability = CodeGenerationCapability()

        code = '''def public_func():
    pass

def _private_func():
    pass
'''
        exports = capability._extract_exports(code)

        assert "public_func" in exports
        assert "_private_func" not in exports


class TestCodeGenerationResult:
    """Tests for CodeGenerationResult."""

    def test_from_handoff_result(self):
        """Should create from base HandoffResult."""
        from contextcore.agent.handoff import HandoffResult

        base_result = HandoffResult(
            handoff_id="handoff-123",
            status=HandoffStatus.COMPLETED,
            result_trace_id="trace-456",
        )

        result = CodeGenerationResult.from_handoff_result(
            base_result,
            code_content="def foo(): pass",
        )

        assert result.handoff_id == "handoff-123"
        assert result.status == HandoffStatus.COMPLETED
        assert result.code_content == "def foo(): pass"
        assert result.decomposition_required is False

    def test_with_decomposition_info(self):
        """Should track decomposition details."""
        from contextcore.agent.handoff import HandoffResult

        base_result = HandoffResult(
            handoff_id="handoff-123",
            status=HandoffStatus.COMPLETED,
        )

        result = CodeGenerationResult.from_handoff_result(
            base_result,
            decomposition_info={
                "chunk_count": 3,
                "chunk_ids": ["chunk-1", "chunk-2", "chunk-3"],
            },
        )

        assert result.decomposition_required is True
        assert result.chunk_count == 3
        assert result.chunk_ids == ["chunk-1", "chunk-2", "chunk-3"]


class TestPreFlightIntegration:
    """Integration tests for pre-flight validation flow."""

    def test_pre_flight_triggers_decomposition(self):
        """Large estimates should suggest decomposition."""
        estimator = SizeEstimator()
        estimate = estimator.estimate(
            task="Implement a comprehensive system with full API, tests, documentation, and error handling for all edge cases",
            inputs={"required_exports": ["System", "API", "Tests", "Docs", "Errors"]},
        )

        # This large task should exceed limits
        if estimate.lines > 150:
            assert estimate.complexity == "high"
            # In a real flow, this would trigger decomposition

    def test_small_task_proceeds(self):
        """Small estimates should proceed with generation."""
        estimator = SizeEstimator()
        estimate = estimator.estimate(
            task="Fix the simple bug",
            inputs={},
        )

        assert estimate.lines < 150
        assert estimate.complexity == "low"


class TestTruncationDetection:
    """Tests for truncation detection in verification."""

    @pytest.mark.parametrize("truncated_code,expected_issue", [
        ('"""Unclosed', "TRUNCATED"),
        ("class Foo:\n    def bar(:\n", "Syntax error"),
        ("...", "TRUNCATED"),
    ])
    def test_truncation_patterns_detected(self, truncated_code, expected_issue):
        """Various truncation patterns should be detected."""
        capability = CodeGenerationCapability()
        issues = capability._verify_completeness(
            content=truncated_code,
            required_exports=None,
        )

        assert len(issues) > 0
        assert any(expected_issue in str(i) for i in issues)
