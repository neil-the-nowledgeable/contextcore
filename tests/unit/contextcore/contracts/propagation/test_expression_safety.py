"""Tests for verification expression safety (NFR-PCG-004).

Validates the AST allowlist that hardens eval() for propagation chain
verification expressions. This is interim hardening pending CEL migration (R6-S1).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contextcore.contracts.propagation.schema import (
    ChainEndpoint,
    PropagationChainSpec,
    _validate_expression,
)


# ---------------------------------------------------------------------------
# Direct _validate_expression tests
# ---------------------------------------------------------------------------


class TestValidateExpressionAllowed:
    """Expressions that MUST be accepted."""

    def test_safe_comparison_passes(self):
        _validate_expression("source == dest")

    def test_safe_len_call_passes(self):
        _validate_expression("len(dest) > 0")

    def test_safe_context_get_passes(self):
        _validate_expression('context.get("field", "")')

    def test_safe_context_get_comparison(self):
        _validate_expression('context.get("field", "") != ""')

    def test_safe_boolean_expression(self):
        _validate_expression("source and dest")

    def test_safe_isinstance_call(self):
        _validate_expression("isinstance(dest, str)")

    def test_safe_int_conversion(self):
        _validate_expression("int(source) > 0")

    def test_safe_source_startswith(self):
        _validate_expression('source.startswith("http")')


class TestValidateExpressionRejected:
    """Expressions that MUST be rejected."""

    def test_import_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_expression('__import__("os")')

    def test_os_system_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_expression('os.system("rm -rf /")')

    def test_deep_attribute_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_expression("context.__class__.__bases__")

    def test_fstring_rejected(self):
        with pytest.raises(ValueError, match="f-string"):
            _validate_expression('f"{context}"')

    def test_expression_length_limit(self):
        long_expr = "source == " + '"a' + "a" * 499 + '"'
        assert len(long_expr) > 500
        with pytest.raises(ValueError, match="too long"):
            _validate_expression(long_expr)

    def test_chained_method_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_expression('context.get("x", "").strip()')

    def test_arbitrary_function_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_expression('exec("print(1)")')

    def test_disallowed_variable_attribute(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_expression("os.path")

    def test_dunder_method_on_allowed_var_rejected(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_expression('context.__delitem__("key")')


# ---------------------------------------------------------------------------
# Pydantic field_validator integration tests
# ---------------------------------------------------------------------------


class TestPropagationChainSpecValidation:
    """Verify that the Pydantic model rejects bad expressions at parse time."""

    def _make_chain(self, verification: str | None = None) -> PropagationChainSpec:
        return PropagationChainSpec(
            chain_id="test",
            source=ChainEndpoint(phase="plan", field="domain"),
            destination=ChainEndpoint(phase="impl", field="domain"),
            verification=verification,
        )

    def test_model_accepts_none_verification(self):
        chain = self._make_chain(verification=None)
        assert chain.verification is None

    def test_model_accepts_safe_expression(self):
        chain = self._make_chain(verification="source == dest")
        assert chain.verification == "source == dest"

    def test_model_rejects_dangerous_expression(self):
        with pytest.raises(ValidationError):
            self._make_chain(verification='__import__("os")')

    def test_model_rejects_fstring(self):
        with pytest.raises(ValidationError):
            self._make_chain(verification='f"{context}"')
