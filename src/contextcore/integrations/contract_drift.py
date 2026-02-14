"""
Contract drift detection — detect divergence between declared schemas and code.

Scope A: A2A schema drift — compare JSON schema files against Pydantic models
and Python enums. Runs offline, reads only local files.

Scope B: OpenAPI drift — compare OpenAPI specs against live service responses.
Requires network access to the service.

Usage::

    from contextcore.integrations.contract_drift import ContractDriftDetector

    detector = ContractDriftDetector()
    report = detector.detect_a2a_drift(
        schemas_dir="schemas/contracts/",
    )
    print(report.to_markdown())
"""
__all__ = [
    'EndpointSpec',
    'parse_openapi',
    'DriftIssue',
    'DriftReport',
    'ContractDriftDetector',
]


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.parse
import json
import logging
import yaml
import os
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class EndpointSpec:
    """Represents a parsed OpenAPI endpoint specification."""
    path: str
    method: str
    operation_id: Optional[str]
    request_content_type: Optional[str]
    response_content_type: Optional[str]
    response_schema: Optional[Dict[str, Any]]
    parameters: List[Dict[str, Any]]

def parse_openapi(spec_url_or_path: str) -> List[EndpointSpec]:
    """
    Parse OpenAPI specification from URL or file path.
    
    Args:
        spec_url_or_path: URL (http/https) or local file path to OpenAPI spec
        
    Returns:
        List of parsed endpoint specifications
        
    Raises:
        Exception: If spec cannot be loaded or parsed
    """
    try:
        spec = _load_spec(spec_url_or_path)
        
        endpoints = []
        paths = spec.get("paths", {})
        
        for path, methods in paths.items():
            # Skip non-method keys like parameters, summary, etc.
            http_methods = {'get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'trace'}
            
            for method, operation in methods.items():
                if method.lower() not in http_methods:
                    continue
                    
                endpoint = EndpointSpec(
                    path=path,
                    method=method.upper(),
                    operation_id=operation.get("operationId"),
                    request_content_type=_get_request_content_type(operation),
                    response_content_type=_get_response_content_type(operation),
                    response_schema=_get_response_schema(operation, spec),
                    parameters=_get_parameters(operation)
                )
                endpoints.append(endpoint)
        
        return endpoints
        
    except Exception as e:
        raise Exception(f"Failed to parse OpenAPI spec from {spec_url_or_path}: {str(e)}") from e

def _load_spec(spec_url_or_path: str) -> Dict[str, Any]:
    """Load specification from URL or file path."""
    if spec_url_or_path.startswith("http://") or spec_url_or_path.startswith("https://"):
        # Load from URL
        with urllib.request.urlopen(spec_url_or_path) as response:
            content = response.read().decode('utf-8')
            if spec_url_or_path.endswith(".json") or response.info().get_content_type() == "application/json":
                return json.loads(content)
            else:
                return yaml.safe_load(content)
    else:
        # Load from file
        with open(spec_url_or_path, 'r', encoding='utf-8') as file:
            if spec_url_or_path.endswith(".json"):
                return json.load(file)
            else:
                return yaml.safe_load(file)

def _get_request_content_type(operation: Dict[str, Any]) -> Optional[str]:
    """Extract request content type from operation."""
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    return next(iter(content.keys()), None) if content else None

def _get_response_content_type(operation: Dict[str, Any]) -> Optional[str]:
    """Extract response content type from operation (defaults to 200 response)."""
    responses = operation.get("responses", {})
    success_response = responses.get("200", responses.get("201", {}))
    content = success_response.get("content", {})
    return next(iter(content.keys()), None) if content else None

def _get_response_schema(operation: Dict[str, Any], spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract and resolve response schema from operation."""
    responses = operation.get("responses", {})
    success_response = responses.get("200", responses.get("201", {}))
    content = success_response.get("content", {})
    
    # Try to get schema from JSON content type first, then any available
    schema_def = None
    if "application/json" in content:
        schema_def = content["application/json"].get("schema")
    elif content:
        schema_def = next(iter(content.values()), {}).get("schema")
    
    if not schema_def:
        return None
        
    # Resolve $ref if present
    if "$ref" in schema_def:
        return _resolve_ref(schema_def["$ref"], spec)
    
    return schema_def

def _resolve_ref(ref: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve JSON Schema $ref reference within the specification.
    
    Args:
        ref: Reference string like "#/components/schemas/User"
        spec: Full OpenAPI specification
        
    Returns:
        Resolved schema dictionary
    """
    if not ref or not ref.startswith("#/"):
        return {}
    
    # Split reference path and navigate through spec
    path_parts = ref[2:].split("/")  # Remove "#/" prefix
    current = spec
    
    for part in path_parts:
        if not isinstance(current, dict) or part not in current:
            return {}
        current = current[part]
    
    return current if isinstance(current, dict) else {}

def _get_parameters(operation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract parameters from operation."""
    return operation.get("parameters", [])


# ---------------------------------------------------------------------------
# A2A Schema Drift Detection (Scope A)
# ---------------------------------------------------------------------------

@dataclass
class DriftIssue:
    """A single drift issue found between schema and implementation."""

    scope: str  # "a2a" or "openapi"
    schema_id: str  # Schema file or OpenAPI spec path
    location: str  # JSON path or endpoint path
    issue_type: str  # "missing_field", "extra_field", "type_mismatch", "enum_drift"
    severity: str  # "critical", "warning", "info"
    expected: str  # What the schema declares
    actual: str  # What the code/output produces
    recommendation: str  # Specific fix action


@dataclass
class DriftReport:
    """Aggregated drift detection report."""

    project_id: str = "contextcore"
    scope: str = "a2a"
    schemas_checked: int = 0
    issues: List[DriftIssue] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def has_drift(self) -> bool:
        return len(self.issues) > 0

    @property
    def critical_issues(self) -> List[DriftIssue]:
        return [i for i in self.issues if i.severity == "critical"]

    @property
    def endpoints_checked(self) -> int:
        """For OpenAPI compat — same as schemas_checked."""
        return self.schemas_checked

    @property
    def endpoints_passed(self) -> int:
        """For OpenAPI compat — schemas without critical issues."""
        failed_schemas = {i.schema_id for i in self.critical_issues}
        return self.schemas_checked - len(failed_schemas)

    def summary(self) -> str:
        status = "DRIFT DETECTED" if self.has_drift else "NO DRIFT"
        crit = len(self.critical_issues)
        return (
            f"Drift Report: {status} "
            f"({self.schemas_checked} schemas, {len(self.issues)} issues, "
            f"{crit} critical)"
        )

    def to_markdown(self) -> str:
        lines = [
            f"# Contract Drift Report",
            f"",
            f"- **Scope**: {self.scope}",
            f"- **Schemas checked**: {self.schemas_checked}",
            f"- **Issues found**: {len(self.issues)}",
            f"- **Critical**: {len(self.critical_issues)}",
            f"- **Timestamp**: {self.timestamp}",
            f"",
        ]
        if not self.issues:
            lines.append("No drift detected. Schemas and code are aligned.")
        else:
            for sev in ("critical", "warning", "info"):
                sev_issues = [i for i in self.issues if i.severity == sev]
                if sev_issues:
                    lines.append(f"## {sev.upper()} ({len(sev_issues)})")
                    lines.append("")
                    for issue in sev_issues:
                        lines.append(f"- **{issue.issue_type}** in `{issue.schema_id}` at `{issue.location}`")
                        lines.append(f"  - Expected: {issue.expected}")
                        lines.append(f"  - Actual: {issue.actual}")
                        lines.append(f"  - Fix: {issue.recommendation}")
                    lines.append("")
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "project_id": self.project_id,
                "scope": self.scope,
                "schemas_checked": self.schemas_checked,
                "issues": [
                    {
                        "scope": i.scope,
                        "schema_id": i.schema_id,
                        "location": i.location,
                        "issue_type": i.issue_type,
                        "severity": i.severity,
                        "expected": i.expected,
                        "actual": i.actual,
                        "recommendation": i.recommendation,
                    }
                    for i in self.issues
                ],
                "has_drift": self.has_drift,
                "critical_count": len(self.critical_issues),
                "timestamp": self.timestamp,
            },
            indent=2,
        )


class ContractDriftDetector:
    """Detect drift between declared schemas and actual code/output.

    Scope A (a2a): Compares JSON schema files in ``schemas/contracts/`` against
    Pydantic models in ``contracts/a2a/models.py`` and Python enums in
    ``contracts/types.py``. Runs entirely offline.

    Scope B (openapi): Compares OpenAPI specs against live service responses.
    Requires network access.
    """

    # Map schema files to their corresponding Pydantic model class names
    SCHEMA_MODEL_MAP = {
        "gate-result.schema.json": "GateResult",
        "handoff-contract.schema.json": "HandoffContract",
        "task-span-contract.schema.json": "TaskSpanContract",
        "artifact-intent.schema.json": "ArtifactIntent",
    }

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def detect(
        self,
        project_id: str = "contextcore",
        contract_url: Optional[str] = None,
        service_url: Optional[str] = None,
        schemas_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
        scope: str = "a2a",
    ) -> DriftReport:
        """Run drift detection.

        Args:
            project_id: Project identifier.
            contract_url: OpenAPI spec URL (scope B only).
            service_url: Live service URL (scope B only).
            schemas_dir: Path to JSON schema directory (scope A).
            output_dir: Path to scan actual output files (scope A).
            scope: "a2a", "openapi", or "all".

        Returns:
            DriftReport with all detected issues.
        """
        report = DriftReport(project_id=project_id, scope=scope)

        if scope in ("a2a", "all"):
            self._detect_a2a_drift(report, schemas_dir, output_dir)

        if scope in ("openapi", "all") and contract_url and service_url:
            self._detect_openapi_drift(report, contract_url, service_url)

        return report

    def detect_a2a_drift(
        self,
        schemas_dir: str = "schemas/contracts/",
        output_dir: Optional[str] = None,
    ) -> DriftReport:
        """Convenience method for A2A-only drift detection."""
        return self.detect(
            schemas_dir=schemas_dir,
            output_dir=output_dir,
            scope="a2a",
        )

    def _detect_a2a_drift(
        self,
        report: DriftReport,
        schemas_dir: Optional[str],
        output_dir: Optional[str],
    ) -> None:
        """Detect drift between JSON schemas and Pydantic models."""
        schemas_path = Path(schemas_dir or "schemas/contracts/")
        if not schemas_path.exists():
            report.issues.append(
                DriftIssue(
                    scope="a2a",
                    schema_id=str(schemas_path),
                    location="/",
                    issue_type="missing_directory",
                    severity="critical",
                    expected="schemas/contracts/ directory exists",
                    actual="directory not found",
                    recommendation=f"Create {schemas_path} with A2A contract schemas.",
                )
            )
            return

        # Load models
        try:
            from contextcore.contracts.a2a.models import (
                GateResult,
                HandoffContract,
                TaskSpanContract,
                ArtifactIntent,
            )

            models_map = {
                "GateResult": GateResult,
                "HandoffContract": HandoffContract,
                "TaskSpanContract": TaskSpanContract,
                "ArtifactIntent": ArtifactIntent,
            }
        except ImportError as e:
            report.issues.append(
                DriftIssue(
                    scope="a2a",
                    schema_id="contracts/a2a/models.py",
                    location="/",
                    issue_type="import_error",
                    severity="critical",
                    expected="models importable",
                    actual=str(e),
                    recommendation="Fix import errors in contracts/a2a/models.py.",
                )
            )
            return

        # Compare each schema file against its model
        for schema_file, model_name in self.SCHEMA_MODEL_MAP.items():
            schema_path = schemas_path / schema_file
            if not schema_path.exists():
                report.issues.append(
                    DriftIssue(
                        scope="a2a",
                        schema_id=schema_file,
                        location="/",
                        issue_type="missing_schema",
                        severity="critical",
                        expected=f"{schema_file} exists",
                        actual="file not found",
                        recommendation=f"Create {schema_path}.",
                    )
                )
                continue

            report.schemas_checked += 1

            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    json_schema = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                report.issues.append(
                    DriftIssue(
                        scope="a2a",
                        schema_id=schema_file,
                        location="/",
                        issue_type="invalid_schema",
                        severity="critical",
                        expected="valid JSON",
                        actual=str(e),
                        recommendation=f"Fix JSON syntax in {schema_file}.",
                    )
                )
                continue

            model_cls = models_map.get(model_name)
            if not model_cls:
                continue

            # Generate Pydantic model's JSON schema for comparison
            try:
                model_schema = model_cls.model_json_schema()
            except Exception as e:
                report.issues.append(
                    DriftIssue(
                        scope="a2a",
                        schema_id=schema_file,
                        location=f"/{model_name}",
                        issue_type="model_schema_error",
                        severity="warning",
                        expected="model_json_schema() succeeds",
                        actual=str(e),
                        recommendation=f"Fix {model_name}.model_json_schema() errors.",
                    )
                )
                continue

            # Compare fields
            self._compare_schema_fields(
                report, schema_file, model_name, json_schema, model_schema
            )

        # Enum drift detection
        self._detect_enum_drift(report, schemas_path)

        # Output file drift (if output_dir provided)
        if output_dir:
            self._detect_output_drift(report, schemas_path, Path(output_dir))

    def _compare_schema_fields(
        self,
        report: DriftReport,
        schema_file: str,
        model_name: str,
        json_schema: Dict[str, Any],
        model_schema: Dict[str, Any],
    ) -> None:
        """Compare declared JSON schema fields against Pydantic model schema."""
        # Get properties from both schemas
        declared_props = set(json_schema.get("properties", {}).keys())
        model_props = set(model_schema.get("properties", {}).keys())

        # Fields in model but not in declared schema
        for prop in sorted(model_props - declared_props):
            report.issues.append(
                DriftIssue(
                    scope="a2a",
                    schema_id=schema_file,
                    location=f"/properties/{prop}",
                    issue_type="extra_field",
                    severity="warning",
                    expected="field not declared in JSON schema",
                    actual=f"field '{prop}' exists in {model_name} Pydantic model",
                    recommendation=f"Add '{prop}' to {schema_file} properties.",
                )
            )

        # Fields in declared schema but not in model
        for prop in sorted(declared_props - model_props):
            report.issues.append(
                DriftIssue(
                    scope="a2a",
                    schema_id=schema_file,
                    location=f"/properties/{prop}",
                    issue_type="missing_field",
                    severity="warning",
                    expected=f"field '{prop}' declared in JSON schema",
                    actual=f"field not found in {model_name} Pydantic model",
                    recommendation=(
                        f"Remove '{prop}' from {schema_file} "
                        f"or add it to {model_name} in models.py."
                    ),
                )
            )

        # Required field comparison
        declared_required = set(json_schema.get("required", []))
        model_required = set(model_schema.get("required", []))

        for prop in sorted(model_required - declared_required):
            if prop in declared_props:
                report.issues.append(
                    DriftIssue(
                        scope="a2a",
                        schema_id=schema_file,
                        location=f"/required/{prop}",
                        issue_type="required_mismatch",
                        severity="warning",
                        expected=f"'{prop}' is optional in JSON schema",
                        actual=f"'{prop}' is required in {model_name}",
                        recommendation=f"Add '{prop}' to required[] in {schema_file}.",
                    )
                )

    def _detect_enum_drift(
        self,
        report: DriftReport,
        schemas_path: Path,
    ) -> None:
        """Detect drift between Python enums and JSON schema enum arrays."""
        try:
            from contextcore.contracts.a2a.models import (
                Phase,
                GateOutcome,
                GateSeverity,
            )

            enum_map = {
                "Phase": Phase,
                "GateOutcome": GateOutcome,
                "GateSeverity": GateSeverity,
            }
        except ImportError:
            return

        # Check each schema file for enum references
        for schema_file in schemas_path.glob("*.schema.json"):
            try:
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            self._check_enum_in_schema(
                report, schema_file.name, schema, enum_map, ""
            )

    def _check_enum_in_schema(
        self,
        report: DriftReport,
        schema_file: str,
        schema_node: Any,
        enum_map: Dict[str, Any],
        path: str,
    ) -> None:
        """Recursively check for enum arrays in schema and compare with Python enums."""
        if not isinstance(schema_node, dict):
            return

        # Check if this node has an enum array
        if "enum" in schema_node:
            schema_values = set(schema_node["enum"])

            # Try to match with a known Python enum by property name
            prop_name = path.rsplit("/", 1)[-1] if "/" in path else path
            for enum_name, enum_cls in enum_map.items():
                python_values = {e.value for e in enum_cls}
                if schema_values & python_values:  # Overlap suggests match
                    in_python_not_schema = python_values - schema_values
                    in_schema_not_python = schema_values - python_values

                    for val in sorted(in_python_not_schema):
                        report.issues.append(
                            DriftIssue(
                                scope="a2a",
                                schema_id=schema_file,
                                location=f"{path}/enum",
                                issue_type="enum_drift",
                                severity="critical",
                                expected=f"'{val}' in schema enum (exists in Python {enum_name})",
                                actual=f"'{val}' missing from schema",
                                recommendation=(
                                    f"Add '{val}' to the enum array at {path} "
                                    f"in {schema_file}."
                                ),
                            )
                        )

                    for val in sorted(in_schema_not_python):
                        report.issues.append(
                            DriftIssue(
                                scope="a2a",
                                schema_id=schema_file,
                                location=f"{path}/enum",
                                issue_type="enum_drift",
                                severity="warning",
                                expected=f"'{val}' in Python {enum_name} (exists in schema)",
                                actual=f"'{val}' missing from Python enum",
                                recommendation=(
                                    f"Remove '{val}' from the enum array at {path} "
                                    f"in {schema_file}, or add it to {enum_name} in models.py."
                                ),
                            )
                        )

        # Recurse into properties and items
        for key in ("properties", "items", "definitions", "$defs"):
            if key in schema_node:
                child = schema_node[key]
                if isinstance(child, dict):
                    for prop_name, prop_value in child.items():
                        self._check_enum_in_schema(
                            report,
                            schema_file,
                            prop_value,
                            enum_map,
                            f"{path}/{key}/{prop_name}",
                        )

        # Recurse into anyOf, oneOf, allOf
        for key in ("anyOf", "oneOf", "allOf"):
            if key in schema_node:
                for idx, item in enumerate(schema_node[key]):
                    self._check_enum_in_schema(
                        report, schema_file, item, enum_map, f"{path}/{key}/{idx}"
                    )

    def _detect_output_drift(
        self,
        report: DriftReport,
        schemas_path: Path,
        output_path: Path,
    ) -> None:
        """Detect drift in actual output files against schemas."""
        if not output_path.exists():
            return

        # Check onboarding-metadata.json against expected structure
        onboarding_file = output_path / "onboarding-metadata.json"
        if onboarding_file.exists():
            report.schemas_checked += 1
            try:
                with open(onboarding_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                required_fields = [
                    "version", "schema", "project_id", "generated_at",
                    "coverage", "artifact_manifest_checksum",
                    "project_context_checksum", "source_checksum",
                ]
                for field_name in required_fields:
                    if field_name not in data:
                        report.issues.append(
                            DriftIssue(
                                scope="a2a",
                                schema_id="onboarding-metadata.json",
                                location=f"/{field_name}",
                                issue_type="missing_field",
                                severity="critical",
                                expected=f"field '{field_name}' present",
                                actual="field missing",
                                recommendation=(
                                    f"Ensure build_onboarding_metadata() populates "
                                    f"'{field_name}' in onboarding-metadata.json."
                                ),
                            )
                        )
            except (json.JSONDecodeError, OSError) as e:
                report.issues.append(
                    DriftIssue(
                        scope="a2a",
                        schema_id="onboarding-metadata.json",
                        location="/",
                        issue_type="invalid_output",
                        severity="critical",
                        expected="valid JSON",
                        actual=str(e),
                        recommendation="Fix onboarding-metadata.json output.",
                    )
                )

    def _detect_openapi_drift(
        self,
        report: DriftReport,
        contract_url: str,
        service_url: str,
    ) -> None:
        """Detect drift between OpenAPI spec and live service (Scope B)."""
        try:
            endpoints = parse_openapi(contract_url)
        except Exception as e:
            report.issues.append(
                DriftIssue(
                    scope="openapi",
                    schema_id=contract_url,
                    location="/",
                    issue_type="parse_error",
                    severity="critical",
                    expected="parseable OpenAPI spec",
                    actual=str(e),
                    recommendation=f"Fix OpenAPI spec at {contract_url}.",
                )
            )
            return

        report.schemas_checked += len(endpoints)

        for endpoint in endpoints:
            url = f"{service_url.rstrip('/')}{endpoint.path}"
            try:
                req = urllib.request.Request(
                    url,
                    method=endpoint.method if endpoint.method != "GET" else None,
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.status
                    if status >= 400:
                        report.issues.append(
                            DriftIssue(
                                scope="openapi",
                                schema_id=contract_url,
                                location=f"{endpoint.method} {endpoint.path}",
                                issue_type="endpoint_error",
                                severity="critical",
                                expected="2xx response",
                                actual=f"HTTP {status}",
                                recommendation=(
                                    f"Endpoint {endpoint.method} {endpoint.path} "
                                    f"returns {status}."
                                ),
                            )
                        )
            except Exception as e:
                report.issues.append(
                    DriftIssue(
                        scope="openapi",
                        schema_id=contract_url,
                        location=f"{endpoint.method} {endpoint.path}",
                        issue_type="connection_error",
                        severity="critical",
                        expected="endpoint reachable",
                        actual=str(e),
                        recommendation=(
                            f"Endpoint {endpoint.method} {endpoint.path} "
                            f"is not reachable at {service_url}."
                        ),
                    )
                )
