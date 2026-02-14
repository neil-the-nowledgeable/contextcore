"""
ContextCore CLI — Weaver semantic convention registry management.

Validates the ``semconv/`` registry against Python enums and attribute
constants. Phase 1 provides offline validation; future phases will integrate
with the OTel Weaver binary for full schema resolution.

Usage::

    contextcore weaver check                    # Validate registry
    contextcore weaver check --registry semconv/ # Explicit path
    contextcore weaver list                     # List registered attributes

See ``docs/plans/WEAVER_REGISTRY_REQUIREMENTS.md`` for full requirements.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import click
import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry validation
# ---------------------------------------------------------------------------

@dataclass
class RegistryIssue:
    """A single issue found during registry validation."""

    file: str
    location: str  # YAML path
    issue_type: str  # enum_mismatch, missing_attribute, extra_attribute, format_error
    severity: str  # error, warning, info
    message: str


@dataclass
class RegistryValidationReport:
    """Aggregated registry validation report."""

    registry_path: str = ""
    files_checked: int = 0
    attributes_found: int = 0
    enums_checked: int = 0
    issues: List[RegistryIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[RegistryIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[RegistryIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        status = "VALID" if self.is_valid else "INVALID"
        return (
            f"Registry: {status} "
            f"({self.files_checked} files, {self.attributes_found} attributes, "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings)"
        )


def _load_python_enums() -> Dict[str, Set[str]]:
    """Load canonical enum values from contracts/types.py."""
    enums: Dict[str, Set[str]] = {}
    try:
        from contextcore.contracts.types import (
            TaskStatus,
            TaskType,
            Priority,
            HandoffStatus,
            SessionStatus,
            InsightType,
            AgentType,
            BusinessValue,
            RiskType,
            Criticality,
        )

        enums["TaskStatus"] = {e.value for e in TaskStatus}
        enums["TaskType"] = {e.value for e in TaskType}
        enums["Priority"] = {e.value for e in Priority}
        enums["HandoffStatus"] = {e.value for e in HandoffStatus}
        enums["SessionStatus"] = {e.value for e in SessionStatus}
        enums["InsightType"] = {e.value for e in InsightType}
        enums["AgentType"] = {e.value for e in AgentType}
        enums["BusinessValue"] = {e.value for e in BusinessValue}
        enums["RiskType"] = {e.value for e in RiskType}
        enums["Criticality"] = {e.value for e in Criticality}
    except ImportError as e:
        logger.warning(f"Could not import enums: {e}")

    return enums


def _load_python_attributes() -> Set[str]:
    """Load attribute constants from tracker.py."""
    attrs: Set[str] = set()
    try:
        from contextcore import tracker

        for name in dir(tracker):
            val = getattr(tracker, name)
            if isinstance(val, str) and "." in val and name.isupper():
                attrs.add(val)
    except ImportError:
        pass

    return attrs


# Map registry attribute IDs to the Python enum they should match
_ATTRIBUTE_ENUM_MAP = {
    "task.type": "TaskType",
    "task.status": "TaskStatus",
    "task.priority": "Priority",
    "agent.type": "AgentType",
}


def validate_registry(registry_path: str = "semconv/") -> RegistryValidationReport:
    """Validate the Weaver registry against Python source of truth.

    Checks:
    1. All registry YAML files are valid and parseable.
    2. Enum values in registry match Python enums in contracts/types.py.
    3. Attributes defined in tracker.py exist in the registry.
    4. Registry manifest references valid files.
    """
    report = RegistryValidationReport(registry_path=registry_path)
    reg_path = Path(registry_path)

    if not reg_path.exists():
        report.issues.append(
            RegistryIssue(
                file=registry_path,
                location="/",
                issue_type="missing_directory",
                severity="error",
                message=f"Registry directory not found: {registry_path}",
            )
        )
        return report

    # Load Python sources
    python_enums = _load_python_enums()
    python_attrs = _load_python_attributes()

    # Check manifest
    manifest_path = reg_path / "registry_manifest.yaml"
    if not manifest_path.exists():
        report.issues.append(
            RegistryIssue(
                file="registry_manifest.yaml",
                location="/",
                issue_type="missing_file",
                severity="error",
                message="registry_manifest.yaml not found.",
            )
        )
    else:
        report.files_checked += 1
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)

            # Check that referenced files exist
            for group_list_key in ("groups", "spans", "events", "metrics"):
                referenced = manifest.get(group_list_key, []) or []
                for ref_file in referenced:
                    ref_path = reg_path / ref_file
                    if not ref_path.exists():
                        report.issues.append(
                            RegistryIssue(
                                file="registry_manifest.yaml",
                                location=f"/{group_list_key}/{ref_file}",
                                issue_type="missing_reference",
                                severity="error",
                                message=f"Referenced file not found: {ref_file}",
                            )
                        )
        except (yaml.YAMLError, OSError) as e:
            report.issues.append(
                RegistryIssue(
                    file="registry_manifest.yaml",
                    location="/",
                    issue_type="parse_error",
                    severity="error",
                    message=f"Failed to parse manifest: {e}",
                )
            )

    # Validate all registry YAML files
    registry_attrs: Set[str] = set()
    for yaml_file in sorted(reg_path.rglob("*.yaml")):
        if yaml_file.name == "registry_manifest.yaml":
            continue

        report.files_checked += 1
        relative = yaml_file.relative_to(reg_path)

        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as e:
            report.issues.append(
                RegistryIssue(
                    file=str(relative),
                    location="/",
                    issue_type="parse_error",
                    severity="error",
                    message=f"Failed to parse: {e}",
                )
            )
            continue

        if not data or not isinstance(data, dict):
            report.issues.append(
                RegistryIssue(
                    file=str(relative),
                    location="/",
                    issue_type="format_error",
                    severity="warning",
                    message="File is empty or not a valid YAML mapping.",
                )
            )
            continue

        # Extract and validate groups
        groups = data.get("groups", [])
        if not isinstance(groups, list):
            continue

        for group in groups:
            if not isinstance(group, dict):
                continue

            group_id = group.get("id", "unknown")
            attributes = group.get("attributes", [])
            if not isinstance(attributes, list):
                continue

            for attr in attributes:
                if not isinstance(attr, dict):
                    continue

                attr_id = attr.get("id") or attr.get("ref")
                if attr_id:
                    registry_attrs.add(attr_id)
                    report.attributes_found += 1

                # Validate enum members against Python enums
                attr_type = attr.get("type")
                if isinstance(attr_type, dict) and "members" in attr_type:
                    members = attr_type["members"]
                    yaml_values = set()
                    for member in members:
                        if isinstance(member, dict) and "value" in member:
                            yaml_values.add(member["value"])

                    # Find the matching Python enum
                    enum_name = _ATTRIBUTE_ENUM_MAP.get(attr_id)
                    if enum_name and enum_name in python_enums:
                        report.enums_checked += 1
                        python_values = python_enums[enum_name]

                        in_yaml_not_python = yaml_values - python_values
                        in_python_not_yaml = python_values - yaml_values

                        for val in sorted(in_yaml_not_python):
                            report.issues.append(
                                RegistryIssue(
                                    file=str(relative),
                                    location=f"/{group_id}/{attr_id}/members",
                                    issue_type="enum_mismatch",
                                    severity="error",
                                    message=(
                                        f"Value '{val}' in registry but not in Python "
                                        f"{enum_name}. Remove from YAML or add to "
                                        f"contracts/types.py."
                                    ),
                                )
                            )

                        for val in sorted(in_python_not_yaml):
                            report.issues.append(
                                RegistryIssue(
                                    file=str(relative),
                                    location=f"/{group_id}/{attr_id}/members",
                                    issue_type="enum_mismatch",
                                    severity="error",
                                    message=(
                                        f"Value '{val}' in Python {enum_name} but not "
                                        f"in registry. Add to {relative}."
                                    ),
                                )
                            )

    # Cross-check: Python attributes not in registry (warnings only)
    for py_attr in sorted(python_attrs):
        if py_attr not in registry_attrs:
            # Only warn for Phase 1 namespaces
            ns = py_attr.split(".")[0]
            if ns in ("task", "project", "sprint", "agent"):
                report.issues.append(
                    RegistryIssue(
                        file="(python source)",
                        location=py_attr,
                        issue_type="missing_in_registry",
                        severity="warning",
                        message=(
                            f"Attribute '{py_attr}' defined in Python but not in "
                            f"registry. Add to semconv/registry/{ns}.yaml."
                        ),
                    )
                )

    return report


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
def weaver():
    """Semantic convention registry management (OTel Weaver)."""
    pass


@weaver.command("check")
@click.option(
    "--registry",
    default="semconv/",
    help="Path to the semconv registry directory",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
)
@click.option(
    "--fail-on-warning",
    is_flag=True,
    help="Exit with error on warnings (not just errors)",
)
def weaver_check(registry: str, output_format: str, fail_on_warning: bool):
    """Validate the semantic convention registry against Python source.

    Checks:
    - All YAML files are valid and parseable
    - Enum values in registry match Python enums in contracts/types.py
    - Required attributes from tracker.py exist in the registry
    - Registry manifest references valid files

    Examples:
        contextcore weaver check
        contextcore weaver check --registry semconv/ --format json
        contextcore weaver check --fail-on-warning
    """
    report = validate_registry(registry)

    if output_format == "json":
        data = {
            "registry_path": report.registry_path,
            "files_checked": report.files_checked,
            "attributes_found": report.attributes_found,
            "enums_checked": report.enums_checked,
            "is_valid": report.is_valid,
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "issues": [
                {
                    "file": i.file,
                    "location": i.location,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "message": i.message,
                }
                for i in report.issues
            ],
        }
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(report.summary())
        click.echo()

        if report.errors:
            click.echo("Errors:")
            for issue in report.errors:
                click.echo(f"  ✗ [{issue.file}] {issue.location}: {issue.message}")
            click.echo()

        if report.warnings:
            click.echo("Warnings:")
            for issue in report.warnings:
                click.echo(f"  ⚠ [{issue.file}] {issue.location}: {issue.message}")
            click.echo()

        if report.is_valid and not report.warnings:
            click.echo("✓ Registry is valid. All enums match Python source.")

    if not report.is_valid:
        sys.exit(1)
    if fail_on_warning and report.warnings:
        sys.exit(1)


@weaver.command("list")
@click.option(
    "--registry",
    default="semconv/",
    help="Path to the semconv registry directory",
)
@click.option(
    "--namespace",
    "-n",
    default=None,
    help="Filter by attribute namespace (e.g., task, project, sprint)",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
)
def weaver_list(registry: str, namespace: Optional[str], output_format: str):
    """List all attributes in the semantic convention registry.

    Examples:
        contextcore weaver list
        contextcore weaver list --namespace task
        contextcore weaver list --format json
    """
    reg_path = Path(registry)
    if not reg_path.exists():
        click.echo(f"Registry not found: {registry}", err=True)
        sys.exit(1)

    all_attrs: List[Dict[str, Any]] = []

    for yaml_file in sorted(reg_path.rglob("*.yaml")):
        if yaml_file.name == "registry_manifest.yaml":
            continue

        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError):
            continue

        if not data or not isinstance(data, dict):
            continue

        groups = data.get("groups", [])
        if not isinstance(groups, list):
            continue

        source_file = str(yaml_file.relative_to(reg_path))
        for group in groups:
            if not isinstance(group, dict):
                continue

            group_id = group.get("id", "")
            group_type = group.get("type", "attribute_group")
            attributes = group.get("attributes", [])
            if not isinstance(attributes, list):
                continue

            for attr in attributes:
                if not isinstance(attr, dict):
                    continue

                attr_id = attr.get("id") or attr.get("ref", "")
                if not attr_id:
                    continue

                # Filter by namespace
                if namespace and not attr_id.startswith(f"{namespace}."):
                    continue

                attr_type = attr.get("type", "string")
                if isinstance(attr_type, dict):
                    attr_type = "enum"

                req_level = attr.get("requirement_level", "opt_in")
                deprecated = attr.get("deprecated")
                brief = attr.get("brief", "")

                all_attrs.append({
                    "id": attr_id,
                    "type": attr_type if isinstance(attr_type, str) else "enum",
                    "requirement_level": req_level,
                    "deprecated": deprecated,
                    "brief": brief[:60] if isinstance(brief, str) else "",
                    "source": source_file,
                    "group": group_id,
                    "group_type": group_type,
                })

    if output_format == "json":
        click.echo(json.dumps(all_attrs, indent=2))
    else:
        ns_label = f" (namespace: {namespace})" if namespace else ""
        click.echo(f"Registered attributes{ns_label}: {len(all_attrs)}")
        click.echo()
        click.echo(f"  {'Attribute':<30} {'Type':<8} {'Req Level':<14} {'Source'}")
        click.echo(f"  {'-'*30} {'-'*8} {'-'*14} {'-'*30}")
        for a in all_attrs:
            dep = " [DEPRECATED]" if a["deprecated"] else ""
            click.echo(
                f"  {a['id']:<30} {a['type']:<8} {a['requirement_level']:<14} "
                f"{a['source']}{dep}"
            )
