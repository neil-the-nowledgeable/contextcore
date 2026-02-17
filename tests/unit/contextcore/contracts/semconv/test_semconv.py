"""Tests for semantic convention contracts (Layer 3)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from contextcore.contracts.semconv.loader import ConventionLoader
from contextcore.contracts.semconv.otel import emit_alias_detected, emit_convention_result
from contextcore.contracts.semconv.schema import (
    AttributeConvention,
    ConventionContract,
    EnumConvention,
)
from contextcore.contracts.semconv.validator import (
    ConventionValidationResult,
    ConventionValidator,
)
from contextcore.contracts.types import ConstraintSeverity, RequirementLevel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_contract() -> ConventionContract:
    return ConventionContract(
        schema_version="0.1.0",
        namespace="test.conventions",
        attributes=[
            AttributeConvention(
                name="service.name",
                type="str",
                requirement_level=RequirementLevel.REQUIRED,
                aliases=["svc_name", "service_name"],
            ),
            AttributeConvention(
                name="deployment.environment",
                type="str",
                requirement_level=RequirementLevel.RECOMMENDED,
                aliases=["env"],
                allowed_values=["production", "staging", "development"],
            ),
            AttributeConvention(
                name="telemetry.sdk.name",
                type="str",
                requirement_level=RequirementLevel.OPT_IN,
            ),
        ],
        enums=[
            EnumConvention(name="status_code", values=["OK", "ERROR", "UNSET"]),
        ],
    )


MINIMAL_YAML = textwrap.dedent("""\
    schema_version: "0.1.0"
    namespace: test.conventions
    attributes:
      - name: service.name
        type: str
        requirement_level: required
        aliases: [svc_name]
    enums:
      - name: status_code
        values: [OK, ERROR]
""")


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_attribute_defaults(self):
        attr = AttributeConvention(name="x")
        assert attr.type == "str"
        assert attr.requirement_level == RequirementLevel.RECOMMENDED
        assert attr.aliases == []
        assert attr.allowed_values is None

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            AttributeConvention(name="")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            AttributeConvention(name="x", bogus="y")

    def test_enum_defaults(self):
        e = EnumConvention(name="x", values=["a"])
        assert e.extensible is False

    def test_contract_minimal(self):
        c = ConventionContract(schema_version="0.1.0", namespace="ns")
        assert c.attributes == []
        assert c.enums == []

    def test_wrong_contract_type_rejected(self):
        with pytest.raises(ValidationError):
            ConventionContract(
                schema_version="0.1.0",
                contract_type="wrong",
                namespace="ns",
            )


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    ConventionLoader.clear_cache()
    yield
    ConventionLoader.clear_cache()


class TestLoader:
    def test_load_from_string(self):
        c = ConventionLoader().load_from_string(MINIMAL_YAML)
        assert c.namespace == "test.conventions"
        assert len(c.attributes) == 1

    def test_load_from_file(self, tmp_path: Path):
        f = tmp_path / "test.yaml"
        f.write_text(MINIMAL_YAML)
        c = ConventionLoader().load(f)
        assert c.namespace == "test.conventions"

    def test_caching(self, tmp_path: Path):
        f = tmp_path / "test.yaml"
        f.write_text(MINIMAL_YAML)
        loader = ConventionLoader()
        assert loader.load(f) is loader.load(f)

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            ConventionLoader().load(Path("/nonexistent.yaml"))


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------


class TestValidator:
    def test_valid_canonical(self):
        v = ConventionValidator(_make_contract())
        r = v.validate_attributes({"service.name": "svc", "deployment.environment": "production"})
        assert r.passed is True
        assert r.violations == 0

    def test_alias_resolved(self):
        v = ConventionValidator(_make_contract())
        r = v.validate_attributes({"svc_name": "svc"})
        assert r.passed is True
        assert r.aliases_resolved == 1

    def test_unknown_attribute(self):
        v = ConventionValidator(_make_contract())
        r = v.validate_attributes({"service.name": "svc", "unknown.attr": "val"})
        assert r.passed is True
        unknown = next(x for x in r.results if x.attribute == "unknown.attr")
        assert unknown.status == "unknown"

    def test_invalid_value(self):
        v = ConventionValidator(_make_contract())
        r = v.validate_attributes({"service.name": "svc", "deployment.environment": "bad"})
        assert r.passed is True  # invalid values are WARNING not BLOCKING
        bad = next(x for x in r.results if x.attribute == "deployment.environment")
        assert bad.status == "invalid_value"

    def test_missing_required_blocks(self):
        v = ConventionValidator(_make_contract())
        r = v.validate_attributes({"deployment.environment": "production"})
        assert r.passed is False
        assert r.violations == 1

    def test_required_via_alias(self):
        v = ConventionValidator(_make_contract())
        r = v.validate_attributes({"svc_name": "svc"})
        assert r.passed is True

    def test_resolve_alias(self):
        v = ConventionValidator(_make_contract())
        assert v.resolve_alias("svc_name") == "service.name"
        assert v.resolve_alias("service.name") == "service.name"
        assert v.resolve_alias("unknown") is None

    def test_validate_value(self):
        v = ConventionValidator(_make_contract())
        assert v.validate_value("deployment.environment", "production") is True
        assert v.validate_value("deployment.environment", "bad") is False
        assert v.validate_value("service.name", "anything") is True
        assert v.validate_value("unknown", "anything") is True


# ---------------------------------------------------------------------------
# OTel tests
# ---------------------------------------------------------------------------


class TestOtel:
    def test_emit_convention_result(self):
        span = MagicMock()
        span.is_recording.return_value = True
        with patch("contextcore.contracts.semconv.otel._HAS_OTEL", True), \
             patch("contextcore.contracts.semconv.otel.otel_trace") as mt:
            mt.get_current_span.return_value = span
            emit_convention_result(
                ConventionValidationResult(passed=True, total_checked=3, violations=0, aliases_resolved=1)
            )
            span.add_event.assert_called_once()
            attrs = span.add_event.call_args.kwargs["attributes"]
            assert attrs["convention.passed"] is True

    def test_no_otel_no_crash(self):
        with patch("contextcore.contracts.semconv.otel._HAS_OTEL", False):
            emit_convention_result(
                ConventionValidationResult(passed=True, total_checked=0, violations=0, aliases_resolved=0)
            )
            emit_alias_detected("a", "b")
