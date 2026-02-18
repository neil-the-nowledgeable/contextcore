"""Tests for contextcore.utils.capability_scanner."""

from pathlib import Path

import pytest

from contextcore.utils.capability_scanner import (
    DOMAIN_MAP,
    A2A_CAPABILITIES,
    scan_contract_domains,
    scan_a2a_contracts,
    _extract_docstring,
    _compute_confidence,
    _count_test_files,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def project_tree(tmp_path: Path) -> Path:
    """Build a minimal project tree with contract domains."""
    contracts = tmp_path / "src" / "contextcore" / "contracts"
    contracts.mkdir(parents=True)

    # Create all 7 domain directories with full file sets
    for domain in DOMAIN_MAP:
        domain_dir = contracts / domain
        domain_dir.mkdir()
        (domain_dir / "schema.py").write_text(
            f'"""\nPydantic models for {domain} contracts.\n\nDetailed description here.\n"""\n',
            encoding="utf-8",
        )
        (domain_dir / "loader.py").write_text("# loader\n", encoding="utf-8")
        (domain_dir / "validator.py").write_text("# validator\n", encoding="utf-8")
        (domain_dir / "otel.py").write_text("# otel\n", encoding="utf-8")

    # Create test directories for some domains
    for domain in ["propagation", "budget", "lineage"]:
        test_dir = tmp_path / "tests" / "unit" / "contextcore" / "contracts" / domain
        test_dir.mkdir(parents=True)
        (test_dir / "test_schema.py").write_text("# test\n", encoding="utf-8")

    return tmp_path


@pytest.fixture()
def a2a_tree(tmp_path: Path) -> Path:
    """Build a minimal A2A contract directory."""
    a2a_dir = tmp_path / "src" / "contextcore" / "contracts" / "a2a"
    a2a_dir.mkdir(parents=True)

    for module in ["models.py", "gates.py", "validator.py", "boundary.py",
                    "pilot.py", "pipeline_checker.py", "three_questions.py",
                    "queries.py", "__init__.py"]:
        (a2a_dir / module).write_text(f"# {module}\n", encoding="utf-8")

    return tmp_path


# ── scan_contract_domains ─────────────────────────────────────────────────


class TestScanContractDomains:
    def test_discovers_all_seven_domains(self, project_tree: Path):
        contracts = project_tree / "src" / "contextcore" / "contracts"
        caps = scan_contract_domains(contracts, project_root=project_tree)
        assert len(caps) == 7
        ids = {c["capability_id"] for c in caps}
        assert "contextcore.contract.propagation" in ids
        assert "contextcore.contract.data_lineage" in ids

    def test_capability_fields(self, project_tree: Path):
        contracts = project_tree / "src" / "contextcore" / "contracts"
        caps = scan_contract_domains(contracts, project_root=project_tree)
        cap = next(c for c in caps if c["capability_id"] == "contextcore.contract.propagation")

        assert cap["category"] == "transform"
        assert cap["maturity"] == "beta"
        assert isinstance(cap["summary"], str)
        assert len(cap["triggers"]) > 0
        assert "confidence" in cap
        assert "evidence" in cap
        assert cap["evidence"]["layer"] == "L1"

    def test_confidence_with_tests(self, project_tree: Path):
        contracts = project_tree / "src" / "contextcore" / "contracts"
        caps = scan_contract_domains(contracts, project_root=project_tree)

        # propagation has tests → 0.90
        prop = next(c for c in caps if c["capability_id"] == "contextcore.contract.propagation")
        assert prop["confidence"] == 0.90

        # ordering has no tests → 0.80
        order = next(c for c in caps if c["capability_id"] == "contextcore.contract.causal_ordering")
        assert order["confidence"] == 0.80

    def test_missing_domain_dir_skipped(self, tmp_path: Path):
        contracts = tmp_path / "src" / "contextcore" / "contracts"
        contracts.mkdir(parents=True)
        # Only create propagation
        (contracts / "propagation").mkdir()
        (contracts / "propagation" / "schema.py").write_text('"""Doc."""\n')
        (contracts / "propagation" / "loader.py").write_text("# l\n")

        caps = scan_contract_domains(contracts, project_root=tmp_path)
        assert len(caps) == 1
        assert caps[0]["capability_id"] == "contextcore.contract.propagation"

    def test_empty_contracts_dir(self, tmp_path: Path):
        contracts = tmp_path / "src" / "contextcore" / "contracts"
        contracts.mkdir(parents=True)
        caps = scan_contract_domains(contracts, project_root=tmp_path)
        assert caps == []

    def test_docstring_extracted(self, project_tree: Path):
        contracts = project_tree / "src" / "contextcore" / "contracts"
        caps = scan_contract_domains(contracts, project_root=project_tree)
        prop = next(c for c in caps if c["capability_id"] == "contextcore.contract.propagation")
        assert "description" in prop
        assert "agent" in prop["description"]
        assert "Pydantic models for propagation contracts" in prop["description"]["agent"]

    def test_project_root_inferred(self, project_tree: Path):
        """When project_root is not given, it's inferred from contracts_dir."""
        contracts = project_tree / "src" / "contextcore" / "contracts"
        caps = scan_contract_domains(contracts)  # no project_root
        assert len(caps) == 7


# ── scan_a2a_contracts ───────────────────────────────────────────────────


class TestScanA2AContracts:
    def test_discovers_all_a2a_capabilities(self, a2a_tree: Path):
        contracts = a2a_tree / "src" / "contextcore" / "contracts"
        caps = scan_a2a_contracts(contracts, project_root=a2a_tree)
        assert len(caps) == 6
        ids = {c["capability_id"] for c in caps}
        assert "contextcore.a2a.contract.task_span" in ids
        assert "contextcore.a2a.gate.pipeline_integrity" in ids
        assert "contextcore.a2a.gate.diagnostic" in ids

    def test_missing_a2a_dir(self, tmp_path: Path):
        contracts = tmp_path / "src" / "contextcore" / "contracts"
        contracts.mkdir(parents=True)
        caps = scan_a2a_contracts(contracts, project_root=tmp_path)
        assert caps == []

    def test_partial_a2a_modules(self, tmp_path: Path):
        """Only models.py present → only contract capabilities, no gates."""
        a2a_dir = tmp_path / "src" / "contextcore" / "contracts" / "a2a"
        a2a_dir.mkdir(parents=True)
        (a2a_dir / "models.py").write_text("# models\n")
        (a2a_dir / "__init__.py").write_text("# init\n")

        caps = scan_a2a_contracts(
            tmp_path / "src" / "contextcore" / "contracts",
            project_root=tmp_path,
        )
        ids = {c["capability_id"] for c in caps}
        assert "contextcore.a2a.contract.task_span" in ids
        assert "contextcore.a2a.contract.handoff" in ids
        # gates not available without gates.py/pipeline_checker.py
        assert "contextcore.a2a.gate.pipeline_integrity" not in ids

    def test_a2a_confidence_without_tests(self, a2a_tree: Path):
        contracts = a2a_tree / "src" / "contextcore" / "contracts"
        caps = scan_a2a_contracts(contracts, project_root=a2a_tree)
        # No test dir → confidence 0.70
        assert all(c["confidence"] == 0.70 for c in caps)

    def test_a2a_confidence_with_tests(self, a2a_tree: Path):
        test_dir = a2a_tree / "tests" / "unit" / "contextcore" / "contracts" / "a2a"
        test_dir.mkdir(parents=True)
        (test_dir / "test_gates.py").write_text("# test\n")

        contracts = a2a_tree / "src" / "contextcore" / "contracts"
        caps = scan_a2a_contracts(contracts, project_root=a2a_tree)
        assert all(c["confidence"] == 0.85 for c in caps)

    def test_capability_fields(self, a2a_tree: Path):
        contracts = a2a_tree / "src" / "contextcore" / "contracts"
        caps = scan_a2a_contracts(contracts, project_root=a2a_tree)
        cap = next(c for c in caps if c["capability_id"] == "contextcore.a2a.gate.diagnostic")
        assert cap["category"] == "action"
        assert cap["maturity"] == "beta"
        assert "three questions" in cap["triggers"]


# ── Helper functions ─────────────────────────────────────────────────────


class TestExtractDocstring:
    def test_valid_file(self, tmp_path: Path):
        py = tmp_path / "test.py"
        py.write_text('"""Module docstring.\n\nDetails here."""\n')
        assert _extract_docstring(py) == "Module docstring.\n\nDetails here."

    def test_no_docstring(self, tmp_path: Path):
        py = tmp_path / "test.py"
        py.write_text("x = 1\n")
        assert _extract_docstring(py) is None

    def test_syntax_error(self, tmp_path: Path):
        py = tmp_path / "bad.py"
        py.write_text("def f(:\n")
        assert _extract_docstring(py) is None


class TestComputeConfidence:
    def test_full_with_tests(self, tmp_path: Path):
        domain = tmp_path / "domain"
        domain.mkdir()
        for f in ["schema.py", "loader.py", "validator.py", "otel.py"]:
            (domain / f).write_text("# f\n")
        test_dir = tmp_path / "tests" / "unit" / "contextcore" / "contracts" / "domain"
        test_dir.mkdir(parents=True)
        (test_dir / "test_x.py").write_text("# t\n")
        assert _compute_confidence(domain, "domain", tmp_path) == 0.90

    def test_full_without_tests(self, tmp_path: Path):
        domain = tmp_path / "domain"
        domain.mkdir()
        for f in ["schema.py", "loader.py", "validator.py", "otel.py"]:
            (domain / f).write_text("# f\n")
        assert _compute_confidence(domain, "domain", tmp_path) == 0.80

    def test_partial_with_tests(self, tmp_path: Path):
        domain = tmp_path / "domain"
        domain.mkdir()
        (domain / "schema.py").write_text("# f\n")
        test_dir = tmp_path / "tests" / "unit" / "contextcore" / "contracts" / "domain"
        test_dir.mkdir(parents=True)
        (test_dir / "test_x.py").write_text("# t\n")
        assert _compute_confidence(domain, "domain", tmp_path) == 0.70
