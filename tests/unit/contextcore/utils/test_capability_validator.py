"""Tests for contextcore.utils.capability_validator."""

from pathlib import Path

import pytest

from contextcore.utils.capability_validator import (
    CheckResult,
    ValidationReport,
    validate_manifest,
    validate_manifest_file,
    _count_trigger_matches,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _minimal_manifest(**overrides):
    """Build a minimal valid manifest dict."""
    base = {
        "manifest_id": "contextcore.agent",
        "name": "ContextCore Agent Capabilities",
        "version": "1.11.0",
        "capabilities": [
            {"capability_id": "contextcore.insight.emit", "category": "action",
             "maturity": "stable", "summary": "Emit insights", "triggers": ["emit insight"]},
            {"capability_id": "contextcore.task.track", "category": "action",
             "maturity": "stable", "summary": "Track tasks", "triggers": ["track task"]},
        ],
    }
    base.update(overrides)
    return base


def _full_manifest():
    """Build a manifest that passes all REQ-CID checks."""
    contract_caps = [
        {"capability_id": f"contextcore.contract.{name}", "category": "transform",
         "maturity": "beta", "summary": f"{name} contracts",
         "triggers": [f"{name} contract", "boundary validation"]}
        for name in ["propagation", "schema_compat", "semantic_convention",
                      "causal_ordering", "capability_propagation", "slo_budget",
                      "data_lineage"]
    ]
    a2a_caps = [
        {"capability_id": "contextcore.a2a.contract.task_span", "category": "transform",
         "maturity": "beta", "summary": "Task span contract",
         "triggers": ["a2a contract", "task span"]},
        {"capability_id": "contextcore.a2a.contract.handoff", "category": "transform",
         "maturity": "beta", "summary": "Handoff contract",
         "triggers": ["a2a contract", "handoff"]},
        {"capability_id": "contextcore.a2a.contract.artifact_intent", "category": "transform",
         "maturity": "beta", "summary": "Artifact intent",
         "triggers": ["a2a contract", "artifact"]},
        {"capability_id": "contextcore.a2a.contract.gate_result", "category": "transform",
         "maturity": "beta", "summary": "Gate result",
         "triggers": ["governance gate"]},
        {"capability_id": "contextcore.a2a.gate.pipeline_integrity", "category": "action",
         "maturity": "beta", "summary": "Pipeline integrity",
         "triggers": ["governance gate", "pipeline integrity"]},
        {"capability_id": "contextcore.a2a.gate.diagnostic", "category": "action",
         "maturity": "beta", "summary": "Diagnostic gate",
         "triggers": ["governance diagnostic", "pipeline diagnostic"]},
    ]
    existing_caps = [
        {"capability_id": "contextcore.insight.emit", "category": "action",
         "maturity": "stable", "summary": "Emit insights",
         "triggers": ["emit insight", "pipeline insight"]},
        {"capability_id": "contextcore.task.track", "category": "action",
         "maturity": "stable", "summary": "Track tasks",
         "triggers": ["track task", "pipeline task"]},
        {"capability_id": "contextcore.handoff.initiate", "category": "action",
         "maturity": "stable", "summary": "Initiate handoff",
         "triggers": ["handoff", "pipeline stage handoff"]},
        {"capability_id": "contextcore.handoff.receive", "category": "action",
         "maturity": "stable", "summary": "Receive handoff",
         "triggers": ["receive", "pipeline stage input"]},
    ]

    all_cap_ids = [c["capability_id"] for c in existing_caps + contract_caps + a2a_caps]

    principles = [
        {"id": f"principle_{i}", "principle": f"Principle {i}",
         "rationale": "Reason", "applies_to": [all_cap_ids[0]]}
        for i in range(9)
    ]

    patterns = [
        {"pattern_id": f"pattern_{i}", "name": f"Pattern {i}",
         "summary": f"Summary {i}",
         "capabilities": [all_cap_ids[i % len(all_cap_ids)]],
         "anti_pattern": "Bad way"}
        for i in range(6)
    ]

    return {
        "manifest_id": "contextcore.agent",
        "name": "ContextCore Agent Capabilities",
        "version": "1.11.0",
        "capabilities": existing_caps + contract_caps + a2a_caps,
        "design_principles": principles,
        "patterns": patterns,
    }


# ── Schema validation ─────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_valid_manifest(self):
        report = validate_manifest(_minimal_manifest())
        # All required fields present
        field_checks = [c for c in report.checks if c.name.startswith("required_field")]
        assert all(c.passed for c in field_checks)

    def test_missing_manifest_id(self):
        m = _minimal_manifest()
        del m["manifest_id"]
        report = validate_manifest(m)
        check = next(c for c in report.checks if c.name == "required_field_manifest_id")
        assert not check.passed

    def test_missing_version(self):
        m = _minimal_manifest()
        del m["version"]
        report = validate_manifest(m)
        check = next(c for c in report.checks if c.name == "required_field_version")
        assert not check.passed

    def test_capabilities_not_list(self):
        m = _minimal_manifest(capabilities="not_a_list")
        report = validate_manifest(m)
        check = next(c for c in report.checks if c.name == "capabilities_is_list")
        assert not check.passed

    def test_invalid_category(self):
        m = _minimal_manifest()
        m["capabilities"][0]["category"] = "invalid_category"
        report = validate_manifest(m)
        check = next(c for c in report.checks if "category" in c.name and "insight" in c.name)
        assert not check.passed

    def test_invalid_maturity(self):
        m = _minimal_manifest()
        m["capabilities"][0]["maturity"] = "invalid"
        report = validate_manifest(m)
        check = next(c for c in report.checks if "maturity" in c.name and "insight" in c.name)
        assert not check.passed

    def test_missing_summary_is_warning(self):
        m = _minimal_manifest()
        m["capabilities"][0]["summary"] = ""
        report = validate_manifest(m)
        check = next(c for c in report.checks if "summary" in c.name and "insight" in c.name)
        assert not check.passed
        assert check.severity == "warning"


# ── REQ-CID acceptance checks ────────────────────────────────────────────


class TestReqCidValidation:
    def test_full_manifest_passes(self):
        report = validate_manifest(_full_manifest())
        errors = [c for c in report.checks if not c.passed and c.severity == "error"]
        assert len(errors) == 0, f"Errors: {[c.name + ': ' + c.message for c in errors]}"

    def test_backward_compat_pass(self):
        m = _minimal_manifest()
        prev_ids = {"contextcore.insight.emit", "contextcore.task.track"}
        report = validate_manifest(m, previous_cap_ids=prev_ids)
        check = next(c for c in report.checks if c.name == "backward_compat")
        assert check.passed

    def test_backward_compat_fail(self):
        m = _minimal_manifest()
        prev_ids = {"contextcore.insight.emit", "contextcore.task.track", "contextcore.removed.cap"}
        report = validate_manifest(m, previous_cap_ids=prev_ids)
        check = next(c for c in report.checks if c.name == "backward_compat")
        assert not check.passed
        assert "contextcore.removed.cap" in check.message

    def test_principle_count_fail(self):
        m = _minimal_manifest()
        m["design_principles"] = [{"id": "p1", "principle": "Test"}]
        report = validate_manifest(m)
        check = next(c for c in report.checks if c.name == "principle_count")
        assert not check.passed

    def test_pattern_count_fail(self):
        m = _minimal_manifest()
        m["patterns"] = [{"pattern_id": "p1", "name": "Test", "summary": "S", "capabilities": []}]
        report = validate_manifest(m)
        check = next(c for c in report.checks if c.name == "pattern_count")
        assert not check.passed

    def test_contract_capability_count_fail(self):
        report = validate_manifest(_minimal_manifest())
        check = next(c for c in report.checks if c.name == "contract_capability_count")
        assert not check.passed
        assert "0" in check.message

    def test_a2a_governance_count_fail(self):
        report = validate_manifest(_minimal_manifest())
        check = next(c for c in report.checks if c.name == "a2a_governance_count")
        assert not check.passed

    def test_trigger_pipeline_coverage(self):
        report = validate_manifest(_full_manifest())
        check = next(c for c in report.checks if c.name == "trigger_pipeline_coverage")
        assert check.passed

    def test_trigger_contract_coverage(self):
        report = validate_manifest(_full_manifest())
        check = next(c for c in report.checks if c.name == "trigger_contract_coverage")
        assert check.passed

    def test_trigger_governance_coverage(self):
        report = validate_manifest(_full_manifest())
        check = next(c for c in report.checks if c.name == "trigger_governance_coverage")
        assert check.passed

    def test_version_bumped_pass(self):
        m = _minimal_manifest(version="1.11.0")
        report = validate_manifest(m, previous_version="1.10.1")
        check = next(c for c in report.checks if c.name == "version_bumped")
        assert check.passed

    def test_version_bumped_fail(self):
        m = _minimal_manifest(version="1.10.0")
        report = validate_manifest(m, previous_version="1.10.1")
        check = next(c for c in report.checks if c.name == "version_bumped")
        assert not check.passed

    def test_pattern_invalid_ref_is_warning(self):
        m = _minimal_manifest()
        m["patterns"] = [{
            "pattern_id": "bad_pat",
            "name": "Bad",
            "summary": "S",
            "capabilities": ["nonexistent.cap"],
        }]
        report = validate_manifest(m)
        check = next(c for c in report.checks if c.name == "pattern_bad_pat_refs_valid")
        assert not check.passed
        assert check.severity == "warning"

    def test_principle_invalid_applies_to_is_warning(self):
        m = _minimal_manifest()
        m["design_principles"] = [{
            "id": "bad_prin",
            "principle": "Test",
            "applies_to": ["nonexistent.cap"],
        }]
        report = validate_manifest(m)
        check = next(c for c in report.checks if c.name == "principle_bad_prin_applies_valid")
        assert not check.passed
        assert check.severity == "warning"


# ── ValidationReport ─────────────────────────────────────────────────────


class TestValidationReport:
    def test_passed_ignores_warnings(self):
        report = ValidationReport()
        report.checks = [
            CheckResult("a", True, "ok"),
            CheckResult("b", False, "warn", severity="warning"),
        ]
        assert report.passed is True

    def test_passed_fails_on_error(self):
        report = ValidationReport()
        report.checks = [
            CheckResult("a", True, "ok"),
            CheckResult("b", False, "fail", severity="error"),
        ]
        assert report.passed is False

    def test_passed_strict_fails_on_warning(self):
        report = ValidationReport()
        report.checks = [
            CheckResult("a", True, "ok"),
            CheckResult("b", False, "warn", severity="warning"),
        ]
        assert report.passed_strict is False

    def test_summary_output(self):
        report = ValidationReport()
        report.checks = [CheckResult("test_check", True, "all good")]
        s = report.summary()
        assert "1/1 checks passed" in s
        assert "[PASS]" in s


# ── validate_manifest_file ───────────────────────────────────────────────


class TestValidateManifestFile:
    def test_valid_file(self, tmp_path: Path):
        import yaml

        m = _full_manifest()
        fp = tmp_path / "test.yaml"
        with open(fp, "w") as f:
            yaml.dump(m, f)
        report = validate_manifest_file(fp)
        assert report.passed

    def test_invalid_yaml(self, tmp_path: Path):
        fp = tmp_path / "bad.yaml"
        fp.write_text("{\n  invalid: yaml: stuff\n}", encoding="utf-8")
        report = validate_manifest_file(fp)
        check = next(c for c in report.checks if c.name == "yaml_parseable")
        assert not check.passed

    def test_with_previous(self, tmp_path: Path):
        import yaml

        prev = _minimal_manifest(version="1.10.1")
        prev_path = tmp_path / "prev.yaml"
        with open(prev_path, "w") as f:
            yaml.dump(prev, f)

        current = _minimal_manifest(version="1.11.0")
        curr_path = tmp_path / "current.yaml"
        with open(curr_path, "w") as f:
            yaml.dump(current, f)

        report = validate_manifest_file(curr_path, previous_path=prev_path)
        bc_check = next(c for c in report.checks if c.name == "backward_compat")
        assert bc_check.passed


# ── Helpers ──────────────────────────────────────────────────────────────


class TestCountTriggerMatches:
    def test_basic_match(self):
        caps = [
            {"triggers": ["pipeline insight"]},
            {"triggers": ["pipeline task"]},
            {"triggers": ["other"]},
        ]
        assert _count_trigger_matches(caps, "pipeline") == 2

    def test_case_insensitive(self):
        caps = [{"triggers": ["Pipeline Stage"]}]
        assert _count_trigger_matches(caps, "pipeline") == 1

    def test_no_match(self):
        caps = [{"triggers": ["other"]}]
        assert _count_trigger_matches(caps, "pipeline") == 0

    def test_empty_caps(self):
        assert _count_trigger_matches([], "pipeline") == 0
