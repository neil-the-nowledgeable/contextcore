from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from contextcore.models.manifest import (
    ContextManifest,
    KeyResult,
    MetricUnit,
    TargetOperator,
    load_context_manifest,
)


def test_example_manifest_parses() -> None:
    """Lock the example file to the schema so onboarding templates can't drift."""
    p = Path("examples/context_manifest_example.yaml")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    manifest = ContextManifest(**data)
    assert manifest.metadata.name == "checkout-service"
    assert manifest.version.startswith("1.")


def test_example_manifest_comprehensive_validation() -> None:
    """
    Comprehensive validation of examples/context_manifest_example.yaml.

    Ensures the example:
    - Has all required v1.1 sections (apiVersion, kind, metadata, spec)
    - Has valid strategic context (objectives, strategies with tactics)
    - Has valid insights with severity and evidence
    - Has cross-references that resolve correctly
    """
    p = Path("examples/context_manifest_example.yaml")
    manifest = load_context_manifest(p)

    # 1. K8s-like structure
    assert manifest.api_version == "contextcore.io/v1alpha1"
    assert manifest.kind == "ContextManifest"

    # 2. Metadata
    assert manifest.metadata.name == "checkout-service"
    assert len(manifest.metadata.owners) >= 1
    assert len(manifest.metadata.changelog) >= 1

    # 3. Objectives with key_results
    assert len(manifest.objectives) >= 1
    obj = manifest.objectives[0]
    assert obj.id.startswith("OBJ-")
    assert len(obj.key_results) >= 1, "Objectives should have structured key_results"

    # 4. Strategies with tactics
    assert len(manifest.strategies) >= 1
    strat = manifest.strategies[0]
    assert strat.id.startswith("STRAT-")
    assert len(strat.tactics) >= 1

    tactic = strat.tactics[0]
    assert tactic.id.startswith("TAC-")
    assert tactic.status is not None

    # 5. Insights with enhanced fields
    assert len(manifest.insights) >= 1
    insight = manifest.insights[0]
    assert insight.severity is not None
    assert len(insight.evidence) >= 1 or insight.recommended_actions

    # 6. Spec (operational context)
    assert manifest.spec.project is not None
    assert manifest.spec.project.id == "checkout-service"
    assert manifest.spec.business is not None
    assert manifest.spec.business.criticality is not None

    # 7. Cross-reference validation passes (no exception)
    # This is implicitly tested by successful parsing with model_validator


# =============================================================================
# KEYRESULT OPERATOR TESTS
# =============================================================================


def test_keyresult_explicit_operator() -> None:
    """KeyResult with explicit operator should use that operator."""
    kr = KeyResult(
        metric_key="custom_metric",
        unit=MetricUnit.COUNT,
        target=100,
        operator=TargetOperator.EQ,
    )
    assert kr.get_operator() == TargetOperator.EQ
    assert kr.evaluate(100) is True
    assert kr.evaluate(99) is False
    assert kr.evaluate(101) is False


def test_keyresult_infers_gte_for_availability() -> None:
    """Availability metrics should infer 'gte' operator (higher is better)."""
    kr = KeyResult(
        metric_key="availability",
        unit=MetricUnit.PERCENT,
        target=99.9,
    )
    assert kr.get_operator() == TargetOperator.GTE
    assert kr.evaluate(99.95) is True  # Above target
    assert kr.evaluate(99.9) is True   # Exactly at target
    assert kr.evaluate(99.5) is False  # Below target


def test_keyresult_infers_lte_for_latency() -> None:
    """Latency metrics should infer 'lte' operator (lower is better)."""
    kr = KeyResult(
        metric_key="latency.p99",
        unit=MetricUnit.MILLISECONDS,
        target=200,
    )
    assert kr.get_operator() == TargetOperator.LTE
    assert kr.evaluate(150) is True   # Below target
    assert kr.evaluate(200) is True   # Exactly at target
    assert kr.evaluate(250) is False  # Above target


def test_keyresult_infers_lte_for_error_metrics() -> None:
    """Error metrics should infer 'lte' operator (lower is better)."""
    kr = KeyResult(
        metric_key="error_rate",
        unit=MetricUnit.PERCENT,
        target=0.1,
    )
    assert kr.get_operator() == TargetOperator.LTE
    assert kr.evaluate(0.05) is True
    assert kr.evaluate(0.2) is False


def test_keyresult_default_infers_gte() -> None:
    """Unknown metrics should default to 'gte' (higher is better)."""
    kr = KeyResult(
        metric_key="throughput",
        unit=MetricUnit.RPS,
        target=1000,
    )
    assert kr.get_operator() == TargetOperator.GTE
    assert kr.evaluate(1500) is True
    assert kr.evaluate(500) is False


def test_legacy_manifest_upgrades_in_memory(tmp_path: Path) -> None:
    """
    Legacy v1.0 manifests may omit apiVersion/kind/metadata.
    We should still be able to load them without forcing manual edits.
    """
    legacy = {
        "version": "1.0",
        "objectives": [],
        "strategies": [],
        "insights": [],
        "spec": {
            "project": {"id": "legacy-proj"},
            "targets": [{"kind": "Deployment", "name": "legacy"}],
        },
    }
    # Round-trip through YAML loader behavior
    tmp_file = tmp_path / "test_manifest_legacy_tmp.yaml"
    tmp_file.write_text(yaml.safe_dump(legacy), encoding="utf-8")

    manifest = load_context_manifest(tmp_file)
    assert manifest.api_version == "contextcore.io/v1alpha1"
    assert manifest.kind == "ContextManifest"
    assert manifest.metadata.name == "legacy-proj"
    assert manifest.version == "1.0"


def test_distill_crd_namespace_is_configurable() -> None:
    p = Path("examples/context_manifest_example.yaml")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    manifest = ContextManifest(**data)

    crd = manifest.distill_crd(namespace="observability", name="checkout-service")
    assert crd["kind"] == "ProjectContext"
    assert crd["metadata"]["namespace"] == "observability"
    assert crd["metadata"]["name"] == "checkout-service"

