"""
Detect drift between API contract and implementation.

This module compares OpenAPI specifications against live service responses
to detect contract drift early.

Prime Contractor Pattern: Spec by Claude, implementation by Claude.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import re

from contextcore.integrations.openapi_parser import parse_openapi, EndpointSpec

__all__ = ['DriftIssue', 'DriftReport', 'ContractDriftDetector']


@dataclass
class DriftIssue:
    """A single drift issue detected."""
    path: str
    method: str
    issue_type: str  # missing_endpoint, schema_mismatch, status_code_mismatch, etc.
    expected: Any
    actual: Any
    severity: str  # critical, warning, info


@dataclass
class DriftReport:
    """Complete drift detection report."""
    project_id: str
    contract_url: str
    service_url: str
    issues: List[DriftIssue] = field(default_factory=list)
    endpoints_checked: int = 0
    endpoints_passed: int = 0

    @property
    def has_drift(self) -> bool:
        """Return True if any drift issues were detected."""
        return len(self.issues) > 0

    @property
    def critical_issues(self) -> List[DriftIssue]:
        """Return only critical severity issues."""
        return [i for i in self.issues if i.severity == "critical"]

    def to_markdown(self) -> str:
        """Convert report to markdown format."""
        lines = []
        lines.append(f"# Contract Drift Report: {self.project_id}\n")
        lines.append(f"**Contract**: {self.contract_url}")
        lines.append(f"**Service**: {self.service_url}")
        lines.append(f"**Endpoints Checked**: {self.endpoints_checked}")
        lines.append(f"**Passed**: {self.endpoints_passed}")
        lines.append(f"**Issues**: {len(self.issues)}\n")

        if not self.issues:
            lines.append("\u2705 No drift detected!\n")
            return "\n".join(lines)

        lines.append("## Issues\n")

        # Group by severity
        for severity in ["critical", "warning", "info"]:
            severity_issues = [i for i in self.issues if i.severity == severity]
            if severity_issues:
                emoji = {"critical": "\U0001f6a8", "warning": "\u26a0\ufe0f", "info": "\u2139\ufe0f"}[severity]
                lines.append(f"### {emoji} {severity.title()} ({len(severity_issues)})\n")

                for issue in severity_issues:
                    lines.append(f"**{issue.method} {issue.path}** - {issue.issue_type}")
                    lines.append(f"- Expected: `{issue.expected}`")
                    lines.append(f"- Actual: `{issue.actual}`\n")

        return "\n".join(lines)


class ContractDriftDetector:
    """Detect drift between OpenAPI contract and live service."""

    def __init__(self, timeout: int = 10):
        """
        Initialize drift detector.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    def detect(
        self,
        project_id: str,
        contract_url: str,
        service_url: str,
        sample_requests: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> DriftReport:
        """
        Detect drift between contract and implementation.

        Args:
            project_id: Project identifier
            contract_url: URL or path to OpenAPI spec
            service_url: Base URL of the service to test
            sample_requests: Optional dict of {operationId: {body, headers}} for testing

        Returns:
            DriftReport with detected issues
        """
        report = DriftReport(
            project_id=project_id,
            contract_url=contract_url,
            service_url=service_url.rstrip("/"),
        )

        # Parse contract
        try:
            endpoints = parse_openapi(contract_url)
        except Exception as e:
            report.issues.append(DriftIssue(
                path="/",
                method="*",
                issue_type="contract_parse_error",
                expected="Valid OpenAPI spec",
                actual=str(e),
                severity="critical",
            ))
            return report

        sample_requests = sample_requests or {}

        for endpoint in endpoints:
            report.endpoints_checked += 1
            issues = self._check_endpoint(endpoint, service_url, sample_requests)

            if issues:
                report.issues.extend(issues)
            else:
                report.endpoints_passed += 1

        return report

    def _check_endpoint(
        self,
        endpoint: EndpointSpec,
        service_url: str,
        sample_requests: Dict[str, Dict[str, Any]],
    ) -> List[DriftIssue]:
        """Check a single endpoint for drift."""
        issues = []

        # Build request URL (replace path params with placeholders)
        path = endpoint.path
        for param in endpoint.parameters:
            if param.get("in") == "path":
                param_name = param.get("name", "")
                # Replace {paramName} with "test" placeholder
                path = re.sub(rf"\{{{param_name}\}}", "test", path)

        url = f"{service_url}{path}"

        # Get sample request if available
        sample = sample_requests.get(endpoint.operation_id, {}) if endpoint.operation_id else {}
        body = sample.get("body")
        headers = sample.get("headers", {})

        # Make request
        try:
            req = Request(url, method=endpoint.method)
            for k, v in headers.items():
                req.add_header(k, v)

            if body and endpoint.method in ["POST", "PUT", "PATCH"]:
                req.data = json.dumps(body).encode('utf-8')
                req.add_header("Content-Type", "application/json")

            with urlopen(req, timeout=self.timeout) as response:
                status = response.status
                response_body = response.read().decode('utf-8')
                content_type = response.headers.get("Content-Type", "")

        except HTTPError as e:
            # Non-2xx responses might be expected for some endpoints
            if e.code == 404:
                issues.append(DriftIssue(
                    path=endpoint.path,
                    method=endpoint.method,
                    issue_type="endpoint_not_found",
                    expected="Endpoint exists",
                    actual=f"404 Not Found",
                    severity="critical",
                ))
            elif e.code == 401 or e.code == 403:
                # Auth errors are not drift, just can't test
                issues.append(DriftIssue(
                    path=endpoint.path,
                    method=endpoint.method,
                    issue_type="auth_required",
                    expected="Accessible endpoint",
                    actual=f"{e.code} {e.reason}",
                    severity="info",
                ))
            else:
                issues.append(DriftIssue(
                    path=endpoint.path,
                    method=endpoint.method,
                    issue_type="unexpected_status",
                    expected="2xx status code",
                    actual=f"{e.code} {e.reason}",
                    severity="warning",
                ))
            return issues

        except URLError as e:
            # Endpoint not reachable
            issues.append(DriftIssue(
                path=endpoint.path,
                method=endpoint.method,
                issue_type="endpoint_unreachable",
                expected="Reachable endpoint",
                actual=str(e.reason),
                severity="critical",
            ))
            return issues

        except Exception as e:
            issues.append(DriftIssue(
                path=endpoint.path,
                method=endpoint.method,
                issue_type="request_error",
                expected="Successful request",
                actual=str(e),
                severity="critical",
            ))
            return issues

        # Check content type
        if endpoint.response_content_type:
            expected_ct = endpoint.response_content_type
            if expected_ct not in content_type:
                issues.append(DriftIssue(
                    path=endpoint.path,
                    method=endpoint.method,
                    issue_type="content_type_mismatch",
                    expected=expected_ct,
                    actual=content_type,
                    severity="warning",
                ))

        # Check response schema (basic structure validation)
        if endpoint.response_schema and response_body:
            try:
                actual_data = json.loads(response_body)
                schema_issues = self._validate_schema(
                    endpoint.response_schema,
                    actual_data,
                    endpoint.path,
                    endpoint.method,
                )
                issues.extend(schema_issues)
            except json.JSONDecodeError:
                if "json" in (endpoint.response_content_type or "").lower():
                    issues.append(DriftIssue(
                        path=endpoint.path,
                        method=endpoint.method,
                        issue_type="invalid_json_response",
                        expected="Valid JSON",
                        actual=response_body[:100] + "..." if len(response_body) > 100 else response_body,
                        severity="critical",
                    ))

        return issues

    def _validate_schema(
        self,
        schema: Dict[str, Any],
        data: Any,
        path: str,
        method: str,
    ) -> List[DriftIssue]:
        """Basic schema validation."""
        issues = []

        # Check required properties
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        if isinstance(data, dict):
            for req_prop in required:
                if req_prop not in data:
                    issues.append(DriftIssue(
                        path=path,
                        method=method,
                        issue_type="missing_required_property",
                        expected=f"Property '{req_prop}' required",
                        actual=f"Property '{req_prop}' missing",
                        severity="critical",
                    ))

            # Check for unexpected properties (info level)
            expected_props = set(properties.keys())
            actual_props = set(data.keys())
            extra_props = actual_props - expected_props

            if extra_props and expected_props:  # Only flag if schema defines properties
                issues.append(DriftIssue(
                    path=path,
                    method=method,
                    issue_type="unexpected_properties",
                    expected=f"Properties: {sorted(expected_props)}",
                    actual=f"Extra: {sorted(extra_props)}",
                    severity="info",
                ))

        return issues
