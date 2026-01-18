# Phase 2: Medium Effort Implementation Plan

**Estimated Effort**: Days per feature
**Total Phase Duration**: 1-2 weeks
**Dependencies**: Phase 1 complete, external tool integrations

---

## Overview

Phase 2 focuses on generating actionable artifacts from ProjectContext metadata that integrate with CI/CD pipelines, testing frameworks, and development workflows. These features require more substantial implementation but deliver significant automation value.

---

## Feature 2.1: SLO-Driven Test Generation

**Effort**: 2-3 days
**Files to Create**:
- `src/contextcore/generators/slo_tests.py`
- `src/contextcore/generators/templates/k6_template.js`
- `src/contextcore/generators/templates/chaos_template.yaml`

### Goal

Generate load tests (k6) and chaos tests (chaos-mesh) directly from ProjectContext requirements, eliminating manual test specification.

### Implementation Steps

#### Step 1: Create test generator module

```python
# src/contextcore/generators/slo_tests.py
"""Generate SLO verification tests from ProjectContext requirements."""

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any

class TestType(Enum):
    LOAD = "load"
    CHAOS = "chaos"
    AVAILABILITY = "availability"
    LATENCY = "latency"


@dataclass
class GeneratedTest:
    """A generated test specification."""
    name: str
    test_type: TestType
    derived_from: str  # Which requirement this came from
    content: str  # The actual test code/config
    file_extension: str


def parse_duration(duration_str: str) -> int:
    """Parse duration string to milliseconds."""
    if not duration_str:
        return 0

    match = re.match(r"(\d+)(ms|s|m|h)?", duration_str.lower())
    if not match:
        return 0

    value = int(match.group(1))
    unit = match.group(2) or "ms"

    multipliers = {"ms": 1, "s": 1000, "m": 60000, "h": 3600000}
    return value * multipliers.get(unit, 1)


def parse_throughput(throughput_str: str) -> int:
    """Parse throughput string to requests per second."""
    if not throughput_str:
        return 100  # Default

    match = re.match(r"(\d+)\s*(rps|req/s|/s)?", throughput_str.lower())
    if match:
        return int(match.group(1))
    return 100


class SLOTestGenerator:
    """Generate tests from ProjectContext SLO requirements."""

    def __init__(self, templates_dir: Optional[Path] = None):
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"

    def generate(
        self,
        project_id: str,
        spec: Dict[str, Any],
        test_types: Optional[List[TestType]] = None
    ) -> List[GeneratedTest]:
        """Generate all applicable tests from spec."""

        tests = []
        requirements = spec.get("requirements", {})
        targets = spec.get("targets", [])
        business = spec.get("business", {})

        if not test_types:
            test_types = list(TestType)

        # Get service endpoint from targets
        service_endpoint = self._get_service_endpoint(targets, spec)

        # Generate latency tests
        if TestType.LATENCY in test_types or TestType.LOAD in test_types:
            if requirements.get("latencyP99") or requirements.get("latencyP50"):
                tests.append(self._generate_latency_test(
                    project_id, requirements, service_endpoint
                ))

        # Generate throughput/load tests
        if TestType.LOAD in test_types:
            if requirements.get("throughput"):
                tests.append(self._generate_load_test(
                    project_id, requirements, service_endpoint
                ))

        # Generate availability/chaos tests
        if TestType.CHAOS in test_types or TestType.AVAILABILITY in test_types:
            if requirements.get("availability"):
                tests.extend(self._generate_chaos_tests(
                    project_id, requirements, targets, business
                ))

        return tests

    def _get_service_endpoint(self, targets: List[Dict], spec: Dict) -> str:
        """Derive service endpoint from targets."""
        for target in targets:
            if target.get("kind") == "Service":
                ns = target.get("namespace", "default")
                name = target.get("name", "service")
                return f"http://{name}.{ns}.svc.cluster.local"

        # Fallback: use first target name
        if targets:
            return f"http://{targets[0].get('name', 'service')}"

        return "http://localhost:8080"

    def _generate_latency_test(
        self,
        project_id: str,
        requirements: Dict,
        endpoint: str
    ) -> GeneratedTest:
        """Generate k6 latency test."""

        p99_ms = parse_duration(requirements.get("latencyP99", "500ms"))
        p50_ms = parse_duration(requirements.get("latencyP50", "100ms"))
        throughput = parse_throughput(requirements.get("throughput", "100rps"))

        k6_script = f'''// Generated from ProjectContext: {project_id}
// Derived from: requirements.latencyP99, requirements.latencyP50

import http from 'k6/http';
import {{ check, sleep }} from 'k6';
import {{ Rate, Trend }} from 'k6/metrics';

// Custom metrics
const latencyP99 = new Trend('latency_p99');
const latencyP50 = new Trend('latency_p50');
const failureRate = new Rate('failures');

// SLO thresholds from ProjectContext
export const options = {{
  stages: [
    {{ duration: '1m', target: {throughput // 2} }},   // Ramp up
    {{ duration: '3m', target: {throughput} }},        // Steady state
    {{ duration: '1m', target: {throughput * 2} }},    // Stress
    {{ duration: '1m', target: 0 }},                   // Ramp down
  ],
  thresholds: {{
    'http_req_duration': [
      'p(99)<{p99_ms}',  // P99 latency from requirements.latencyP99
      'p(50)<{p50_ms}',  // P50 latency from requirements.latencyP50
    ],
    'failures': ['rate<0.01'],  // 1% error rate max
  }},
}};

export default function () {{
  const res = http.get('{endpoint}/health');

  check(res, {{
    'status is 200': (r) => r.status === 200,
    'latency OK': (r) => r.timings.duration < {p99_ms},
  }});

  failureRate.add(res.status !== 200);
  latencyP99.add(res.timings.duration);

  sleep(1 / {throughput});  // Maintain target RPS
}}

export function handleSummary(data) {{
  return {{
    'stdout': JSON.stringify({{
      project: '{project_id}',
      test_type: 'latency_slo',
      p99_threshold_ms: {p99_ms},
      p50_threshold_ms: {p50_ms},
      passed: data.metrics.http_req_duration.values['p(99)'] < {p99_ms},
      actual_p99_ms: data.metrics.http_req_duration.values['p(99)'],
      actual_p50_ms: data.metrics.http_req_duration.values['p(50)'],
    }}, null, 2),
  }};
}}
'''
        return GeneratedTest(
            name=f"{project_id}-latency-slo-test",
            test_type=TestType.LATENCY,
            derived_from="requirements.latencyP99, requirements.latencyP50",
            content=k6_script,
            file_extension=".js"
        )

    def _generate_load_test(
        self,
        project_id: str,
        requirements: Dict,
        endpoint: str
    ) -> GeneratedTest:
        """Generate k6 load/throughput test."""

        throughput = parse_throughput(requirements.get("throughput", "100rps"))
        error_budget = float(requirements.get("errorBudget", "0.1"))

        k6_script = f'''// Generated from ProjectContext: {project_id}
// Derived from: requirements.throughput, requirements.errorBudget

import http from 'k6/http';
import {{ check, sleep }} from 'k6';
import {{ Rate, Counter }} from 'k6/metrics';

const errorRate = new Rate('error_rate');
const requestCount = new Counter('requests');

// Load profile from ProjectContext requirements.throughput
export const options = {{
  scenarios: {{
    sustained_load: {{
      executor: 'constant-arrival-rate',
      rate: {throughput},
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: {max(10, throughput // 10)},
      maxVUs: {throughput},
    }},
    spike_test: {{
      executor: 'ramping-arrival-rate',
      startRate: {throughput},
      timeUnit: '1s',
      stages: [
        {{ duration: '1m', target: {throughput} }},
        {{ duration: '30s', target: {throughput * 3} }},  // 3x spike
        {{ duration: '1m', target: {throughput} }},
      ],
      preAllocatedVUs: {throughput},
      maxVUs: {throughput * 3},
    }},
  }},
  thresholds: {{
    'error_rate': ['rate<{error_budget}'],  // From requirements.errorBudget
    'http_req_duration': ['p(95)<1000'],    // 1s max at p95
  }},
}};

export default function () {{
  const res = http.get('{endpoint}/health');

  const passed = check(res, {{
    'status is 2xx': (r) => r.status >= 200 && r.status < 300,
  }});

  errorRate.add(!passed);
  requestCount.add(1);
}}

export function handleSummary(data) {{
  const actualErrorRate = data.metrics.error_rate?.values?.rate || 0;
  return {{
    'stdout': JSON.stringify({{
      project: '{project_id}',
      test_type: 'throughput_slo',
      target_rps: {throughput},
      error_budget: {error_budget},
      passed: actualErrorRate < {error_budget},
      actual_error_rate: actualErrorRate,
      total_requests: data.metrics.requests?.values?.count || 0,
    }}, null, 2),
  }};
}}
'''
        return GeneratedTest(
            name=f"{project_id}-throughput-slo-test",
            test_type=TestType.LOAD,
            derived_from="requirements.throughput, requirements.errorBudget",
            content=k6_script,
            file_extension=".js"
        )

    def _generate_chaos_tests(
        self,
        project_id: str,
        requirements: Dict,
        targets: List[Dict],
        business: Dict
    ) -> List[GeneratedTest]:
        """Generate chaos-mesh experiments."""

        tests = []
        availability = float(requirements.get("availability", "99.0"))
        criticality = business.get("criticality", "medium")

        # Get deployment target
        deployment_target = None
        namespace = "default"
        for target in targets:
            if target.get("kind") == "Deployment":
                deployment_target = target.get("name")
                namespace = target.get("namespace", "default")
                break

        if not deployment_target:
            return tests

        # Pod failure test
        pod_failure_yaml = f'''# Generated from ProjectContext: {project_id}
# Derived from: requirements.availability ({availability}%)
# Validates service survives pod failure

apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: {project_id}-pod-failure
  namespace: {namespace}
  labels:
    contextcore.io/project: {project_id}
    contextcore.io/test-type: availability
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces:
      - {namespace}
    labelSelectors:
      app: {deployment_target}
  duration: "30s"
  scheduler:
    cron: "@every 5m"  # Run periodically in staging
'''
        tests.append(GeneratedTest(
            name=f"{project_id}-pod-failure-chaos",
            test_type=TestType.CHAOS,
            derived_from="requirements.availability",
            content=pod_failure_yaml,
            file_extension=".yaml"
        ))

        # Network delay test (for critical/high services)
        if criticality in ["critical", "high"]:
            network_delay_yaml = f'''# Generated from ProjectContext: {project_id}
# Derived from: requirements.availability, business.criticality ({criticality})
# Validates service handles network degradation gracefully

apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {project_id}-network-delay
  namespace: {namespace}
  labels:
    contextcore.io/project: {project_id}
    contextcore.io/test-type: latency-resilience
spec:
  action: delay
  mode: all
  selector:
    namespaces:
      - {namespace}
    labelSelectors:
      app: {deployment_target}
  delay:
    latency: "100ms"
    jitter: "50ms"
    correlation: "50"
  duration: "2m"
'''
            tests.append(GeneratedTest(
                name=f"{project_id}-network-delay-chaos",
                test_type=TestType.CHAOS,
                derived_from="requirements.availability, business.criticality",
                content=network_delay_yaml,
                file_extension=".yaml"
            ))

        # CPU stress test (for critical services only)
        if criticality == "critical":
            cpu_stress_yaml = f'''# Generated from ProjectContext: {project_id}
# Derived from: business.criticality (critical)
# Validates service degrades gracefully under CPU pressure

apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: {project_id}-cpu-stress
  namespace: {namespace}
  labels:
    contextcore.io/project: {project_id}
    contextcore.io/test-type: resource-resilience
spec:
  mode: one
  selector:
    namespaces:
      - {namespace}
    labelSelectors:
      app: {deployment_target}
  stressors:
    cpu:
      workers: 2
      load: 80
  duration: "2m"
'''
            tests.append(GeneratedTest(
                name=f"{project_id}-cpu-stress-chaos",
                test_type=TestType.CHAOS,
                derived_from="business.criticality",
                content=cpu_stress_yaml,
                file_extension=".yaml"
            ))

        return tests


def write_tests(tests: List[GeneratedTest], output_dir: Path) -> List[Path]:
    """Write generated tests to files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []

    for test in tests:
        filename = f"{test.name}{test.file_extension}"
        filepath = output_dir / filename
        filepath.write_text(test.content)
        written.append(filepath)

    return written
```

#### Step 2: Add CLI command

```python
# In cli.py, add to generate group:

@generate.command("slo-tests")
@click.option("--project", "-p", required=True, help="Project ID")
@click.option("--output-dir", "-o", type=click.Path(), default="./generated-tests")
@click.option("--types", "-t", multiple=True,
              type=click.Choice(["load", "latency", "chaos", "availability"]),
              help="Test types to generate (default: all)")
@click.pass_context
def generate_slo_tests_cmd(ctx, project: str, output_dir: str, types: tuple):
    """Generate SLO verification tests from ProjectContext requirements."""
    from contextcore.generators.slo_tests import SLOTestGenerator, TestType, write_tests

    spec = get_project_context_spec(project)
    if not spec:
        click.echo(f"Error: ProjectContext '{project}' not found", err=True)
        raise SystemExit(1)

    test_types = [TestType(t) for t in types] if types else None
    generator = SLOTestGenerator()
    tests = generator.generate(project, spec, test_types)

    if not tests:
        click.echo("No tests generated. Check that requirements are specified in ProjectContext.")
        return

    output_path = Path(output_dir)
    written = write_tests(tests, output_path)

    click.echo(f"Generated {len(tests)} test(s):")
    for path in written:
        click.echo(f"  - {path}")

    click.echo(f"\nRun load tests:  k6 run {output_path}/*-slo-test.js")
    click.echo(f"Apply chaos:     kubectl apply -f {output_path}/*-chaos.yaml")
```

### Acceptance Criteria

- [ ] `contextcore generate slo-tests --project <id>` generates k6 scripts
- [ ] k6 scripts have thresholds derived from requirements.latencyP99/P50
- [ ] k6 scripts have load profiles derived from requirements.throughput
- [ ] Chaos-mesh YAMLs generated for availability requirements
- [ ] Critical services get additional stress tests
- [ ] All generated files have comments indicating derivation source
- [ ] Generated tests are syntactically valid

### Test Cases

```python
def test_latency_test_generation():
    spec = {
        "project": {"id": "test"},
        "requirements": {"latencyP99": "200ms", "latencyP50": "50ms"},
        "targets": [{"kind": "Service", "name": "test-svc"}],
    }
    gen = SLOTestGenerator()
    tests = gen.generate("test", spec, [TestType.LATENCY])
    assert len(tests) == 1
    assert "p(99)<200" in tests[0].content

def test_chaos_test_generation_critical():
    spec = {
        "project": {"id": "test"},
        "requirements": {"availability": "99.95"},
        "business": {"criticality": "critical"},
        "targets": [{"kind": "Deployment", "name": "test-deploy", "namespace": "prod"}],
    }
    gen = SLOTestGenerator()
    tests = gen.generate("test", spec, [TestType.CHAOS])
    assert len(tests) >= 2  # pod-failure + network-delay at minimum
    assert any("StressChaos" in t.content for t in tests)  # Critical gets CPU stress
```

---

## Feature 2.2: Risk-Based PR Review Guidance

**Effort**: 2-3 days
**Files to Create**:
- `src/contextcore/integrations/github_review.py`
- `.github/actions/contextcore-review/action.yml`

### Goal

Create a GitHub Action that analyzes PRs against ProjectContext risks and provides automated review guidance, checklists, and required reviewer suggestions.

### Implementation Steps

#### Step 1: Create review analyzer

```python
# src/contextcore/integrations/github_review.py
"""GitHub PR review guidance based on ProjectContext risks."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Set

class ReviewPriority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ReviewFocus:
    """A specific area requiring review attention."""
    area: str
    reason: str
    priority: ReviewPriority
    checklist: List[str] = field(default_factory=list)
    required_reviewers: List[str] = field(default_factory=list)


@dataclass
class ReviewGuidance:
    """Complete review guidance for a PR."""
    pr_number: int
    project_id: str
    focus_areas: List[ReviewFocus] = field(default_factory=list)
    overall_priority: ReviewPriority = ReviewPriority.LOW
    auto_checklist: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert to GitHub-compatible markdown comment."""
        lines = []

        # Header with priority badge
        priority_emoji = {
            ReviewPriority.CRITICAL: "🚨",
            ReviewPriority.HIGH: "⚠️",
            ReviewPriority.MEDIUM: "📋",
            ReviewPriority.LOW: "ℹ️",
        }
        emoji = priority_emoji[self.overall_priority]
        lines.append(f"## {emoji} ContextCore Review Guidance\n")
        lines.append(f"**Project**: {self.project_id}")
        lines.append(f"**Review Priority**: {self.overall_priority.value.upper()}\n")

        # Warnings
        if self.warnings:
            lines.append("### ⚠️ Warnings\n")
            for warning in self.warnings:
                lines.append(f"- {warning}")
            lines.append("")

        # Focus areas
        if self.focus_areas:
            lines.append("### Focus Areas\n")
            for focus in self.focus_areas:
                lines.append(f"#### {focus.area} ({focus.priority.value})")
                lines.append(f"> {focus.reason}\n")

                if focus.checklist:
                    lines.append("**Checklist:**")
                    for item in focus.checklist:
                        lines.append(f"- [ ] {item}")
                    lines.append("")

                if focus.required_reviewers:
                    reviewers = ", ".join(f"@{r}" for r in focus.required_reviewers)
                    lines.append(f"**Required reviewers**: {reviewers}\n")

        # Auto-generated checklist
        if self.auto_checklist:
            lines.append("### General Checklist\n")
            for item in self.auto_checklist:
                lines.append(f"- [ ] {item}")
            lines.append("")

        lines.append("---")
        lines.append("_Generated by ContextCore from ProjectContext risk analysis_")

        return "\n".join(lines)


class PRReviewAnalyzer:
    """Analyze PRs against ProjectContext for review guidance."""

    # Map risk types to review focus areas
    RISK_CHECKLISTS = {
        "security": [
            "No hardcoded credentials or secrets",
            "Input validation on all user-provided data",
            "SQL/NoSQL injection prevention verified",
            "XSS prevention in any HTML output",
            "Authentication/authorization checks in place",
            "Sensitive data not logged",
        ],
        "compliance": [
            "Audit logging for compliance-relevant operations",
            "Data retention policies followed",
            "PII handling follows data protection requirements",
            "Change is documented for audit trail",
        ],
        "data-integrity": [
            "Database transactions used appropriately",
            "Idempotency implemented for mutations",
            "Data validation at system boundaries",
            "Backup/recovery impact considered",
        ],
        "availability": [
            "Graceful degradation implemented",
            "Circuit breakers for external dependencies",
            "Timeout configuration appropriate",
            "Health check endpoints updated if needed",
        ],
        "financial": [
            "Cost impact of change assessed",
            "Rate limiting in place for expensive operations",
            "Billing/metering accuracy verified",
        ],
    }

    # Risk type to reviewer team mapping
    RISK_REVIEWERS = {
        "security": ["security-team"],
        "compliance": ["compliance-team", "legal"],
        "data-integrity": ["data-team", "dba"],
        "financial": ["finance-eng"],
    }

    def analyze(
        self,
        pr_number: int,
        changed_files: List[str],
        project_context_spec: Dict,
    ) -> ReviewGuidance:
        """Analyze PR against ProjectContext risks."""

        project_id = self._get_project_id(project_context_spec)
        risks = project_context_spec.get("risks", [])
        business = project_context_spec.get("business", {})

        guidance = ReviewGuidance(
            pr_number=pr_number,
            project_id=project_id,
        )

        # Check each risk against changed files
        for risk in risks:
            risk_type = risk.get("type", "")
            risk_scope = risk.get("scope", "")  # Optional path pattern
            risk_priority = risk.get("priority", "P3")

            # Check if any changed file matches risk scope
            if risk_scope:
                matching_files = self._match_files(changed_files, risk_scope)
                if not matching_files:
                    continue  # Risk doesn't apply to this PR
            else:
                matching_files = changed_files  # Risk applies to all changes

            # Create focus area for this risk
            focus = ReviewFocus(
                area=risk_type.replace("-", " ").title(),
                reason=risk.get("description", f"Risk area: {risk_type}"),
                priority=self._priority_from_string(risk_priority),
                checklist=self.RISK_CHECKLISTS.get(risk_type, []).copy(),
                required_reviewers=self.RISK_REVIEWERS.get(risk_type, []).copy(),
            )

            # Add risk-specific mitigation to checklist
            if risk.get("mitigation"):
                focus.checklist.append(f"Mitigation verified: {risk['mitigation']}")

            # Add controls verification
            for control in risk.get("controls", []):
                focus.checklist.append(f"Control in place: {control}")

            guidance.focus_areas.append(focus)

        # Determine overall priority
        if guidance.focus_areas:
            priorities = [f.priority for f in guidance.focus_areas]
            guidance.overall_priority = min(priorities, key=lambda p: list(ReviewPriority).index(p))

        # Add warnings for high-criticality services
        if business.get("criticality") in ["critical", "high"]:
            guidance.warnings.append(
                f"This is a {business['criticality']} criticality service. "
                "Extra scrutiny required."
            )

        # Add general checklist items based on change scope
        guidance.auto_checklist = self._generate_general_checklist(changed_files)

        return guidance

    def _get_project_id(self, spec: Dict) -> str:
        project = spec.get("project", {})
        if isinstance(project, dict):
            return project.get("id", "unknown")
        return str(project) if project else "unknown"

    def _match_files(self, files: List[str], pattern: str) -> List[str]:
        """Match files against glob-like pattern."""
        import fnmatch
        return [f for f in files if fnmatch.fnmatch(f, pattern)]

    def _priority_from_string(self, priority_str: str) -> ReviewPriority:
        mapping = {
            "P1": ReviewPriority.CRITICAL,
            "P2": ReviewPriority.HIGH,
            "P3": ReviewPriority.MEDIUM,
            "P4": ReviewPriority.LOW,
        }
        return mapping.get(priority_str, ReviewPriority.MEDIUM)

    def _generate_general_checklist(self, files: List[str]) -> List[str]:
        """Generate general checklist based on files changed."""
        checklist = []

        # Check for test files
        has_tests = any("test" in f.lower() for f in files)
        if not has_tests:
            checklist.append("Tests added/updated for changes")

        # Check for config changes
        config_files = [f for f in files if any(
            f.endswith(ext) for ext in [".yaml", ".yml", ".json", ".toml", ".env"]
        )]
        if config_files:
            checklist.append("Configuration changes reviewed for security")
            checklist.append("Environment-specific values not hardcoded")

        # Check for API changes
        api_files = [f for f in files if "api" in f.lower() or "handler" in f.lower()]
        if api_files:
            checklist.append("API changes are backwards compatible (or versioned)")
            checklist.append("API documentation updated")

        # Check for database changes
        db_files = [f for f in files if any(
            term in f.lower() for term in ["migration", "schema", "model", "db"]
        )]
        if db_files:
            checklist.append("Database migration is reversible")
            checklist.append("Migration tested on production-like data")

        return checklist
```

#### Step 2: Create GitHub Action

```yaml
# .github/actions/contextcore-review/action.yml
name: 'ContextCore PR Review'
description: 'Generate review guidance from ProjectContext risks'

inputs:
  project-id:
    description: 'ProjectContext project ID'
    required: true
  github-token:
    description: 'GitHub token for API access'
    required: true
  kubeconfig:
    description: 'Base64-encoded kubeconfig for cluster access'
    required: false

outputs:
  review-priority:
    description: 'Overall review priority'
  focus-areas:
    description: 'Number of risk focus areas identified'

runs:
  using: 'composite'
  steps:
    - name: Install ContextCore
      shell: bash
      run: pip install contextcore

    - name: Get changed files
      id: changed-files
      shell: bash
      run: |
        FILES=$(gh pr view ${{ github.event.pull_request.number }} --json files -q '.files[].path' | tr '\n' ',')
        echo "files=$FILES" >> $GITHUB_OUTPUT
      env:
        GH_TOKEN: ${{ inputs.github-token }}

    - name: Generate review guidance
      id: review
      shell: bash
      run: |
        contextcore review pr \
          --project "${{ inputs.project-id }}" \
          --pr-number "${{ github.event.pull_request.number }}" \
          --files "${{ steps.changed-files.outputs.files }}" \
          --output review-guidance.md \
          --json review-metadata.json

        echo "priority=$(jq -r .overall_priority review-metadata.json)" >> $GITHUB_OUTPUT
        echo "focus-count=$(jq '.focus_areas | length' review-metadata.json)" >> $GITHUB_OUTPUT

    - name: Post review comment
      shell: bash
      run: |
        gh pr comment ${{ github.event.pull_request.number }} \
          --body-file review-guidance.md
      env:
        GH_TOKEN: ${{ inputs.github-token }}
```

#### Step 3: Add CLI command

```python
# In cli.py, add review group:

@cli.group()
def review():
    """PR review guidance commands."""
    pass

@review.command("pr")
@click.option("--project", "-p", required=True, help="Project ID")
@click.option("--pr-number", required=True, type=int, help="PR number")
@click.option("--files", required=True, help="Comma-separated changed files")
@click.option("--output", "-o", type=click.Path(), help="Output markdown file")
@click.option("--json", "json_output", type=click.Path(), help="Output JSON metadata")
def review_pr_cmd(project: str, pr_number: int, files: str, output: str, json_output: str):
    """Generate review guidance for a PR."""
    from contextcore.integrations.github_review import PRReviewAnalyzer
    import json

    spec = get_project_context_spec(project)
    if not spec:
        click.echo(f"Error: ProjectContext '{project}' not found", err=True)
        raise SystemExit(1)

    changed_files = [f.strip() for f in files.split(",") if f.strip()]
    analyzer = PRReviewAnalyzer()
    guidance = analyzer.analyze(pr_number, changed_files, spec)

    if output:
        with open(output, "w") as f:
            f.write(guidance.to_markdown())
        click.echo(f"Review guidance written to {output}")
    else:
        click.echo(guidance.to_markdown())

    if json_output:
        metadata = {
            "pr_number": guidance.pr_number,
            "project_id": guidance.project_id,
            "overall_priority": guidance.overall_priority.value,
            "focus_areas": [
                {"area": f.area, "priority": f.priority.value}
                for f in guidance.focus_areas
            ],
            "warning_count": len(guidance.warnings),
        }
        with open(json_output, "w") as f:
            json.dump(metadata, f, indent=2)
```

### Acceptance Criteria

- [ ] `contextcore review pr` generates markdown review guidance
- [ ] Guidance includes risk-specific checklists
- [ ] Guidance suggests required reviewers for P1/P2 risks
- [ ] GitHub Action posts comment on PR
- [ ] Overall priority reflects highest-priority applicable risk
- [ ] Files outside risk scope don't trigger risk-specific reviews

---

## Feature 2.3: Contract Drift Detection

**Effort**: 2-3 days
**Files to Create**:
- `src/contextcore/integrations/contract_drift.py`
- `src/contextcore/integrations/openapi_parser.py`

### Goal

Continuously verify that service implementations match their API contracts specified in ProjectContext, detecting drift early.

### Implementation Steps

#### Step 1: Create OpenAPI parser

```python
# src/contextcore/integrations/openapi_parser.py
"""Parse OpenAPI specifications for contract comparison."""

import json
import yaml
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from urllib.request import urlopen


@dataclass
class EndpointSpec:
    """Specification for a single endpoint."""
    path: str
    method: str
    operation_id: Optional[str]
    request_content_type: Optional[str]
    response_content_type: Optional[str]
    response_schema: Optional[Dict]
    parameters: List[Dict]


def parse_openapi(spec_url_or_path: str) -> List[EndpointSpec]:
    """Parse OpenAPI spec and extract endpoint specifications."""

    # Load spec
    if spec_url_or_path.startswith("http"):
        with urlopen(spec_url_or_path) as response:
            content = response.read().decode()
    else:
        with open(spec_url_or_path) as f:
            content = f.read()

    # Parse YAML or JSON
    if spec_url_or_path.endswith(".json"):
        spec = json.loads(content)
    else:
        spec = yaml.safe_load(content)

    endpoints = []

    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                endpoint = EndpointSpec(
                    path=path,
                    method=method.upper(),
                    operation_id=operation.get("operationId"),
                    request_content_type=_get_request_content_type(operation),
                    response_content_type=_get_response_content_type(operation),
                    response_schema=_get_response_schema(operation, spec),
                    parameters=operation.get("parameters", []),
                )
                endpoints.append(endpoint)

    return endpoints


def _get_request_content_type(operation: Dict) -> Optional[str]:
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    return list(content.keys())[0] if content else None


def _get_response_content_type(operation: Dict) -> Optional[str]:
    responses = operation.get("responses", {})
    success = responses.get("200", responses.get("201", {}))
    content = success.get("content", {})
    return list(content.keys())[0] if content else None


def _get_response_schema(operation: Dict, spec: Dict) -> Optional[Dict]:
    responses = operation.get("responses", {})
    success = responses.get("200", responses.get("201", {}))
    content = success.get("content", {})

    if not content:
        return None

    first_content = list(content.values())[0]
    schema = first_content.get("schema", {})

    # Resolve $ref if present
    if "$ref" in schema:
        return _resolve_ref(schema["$ref"], spec)

    return schema


def _resolve_ref(ref: str, spec: Dict) -> Dict:
    """Resolve a JSON Schema $ref."""
    # Format: #/components/schemas/MySchema
    parts = ref.lstrip("#/").split("/")
    result = spec
    for part in parts:
        result = result.get(part, {})
    return result
```

#### Step 2: Create drift detector

```python
# src/contextcore/integrations/contract_drift.py
"""Detect drift between API contract and implementation."""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from contextcore.integrations.openapi_parser import parse_openapi, EndpointSpec


@dataclass
class DriftIssue:
    """A single drift issue detected."""
    path: str
    method: str
    issue_type: str  # missing_endpoint, schema_mismatch, status_code_mismatch
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
        return len(self.issues) > 0

    @property
    def critical_issues(self) -> List[DriftIssue]:
        return [i for i in self.issues if i.severity == "critical"]

    def to_markdown(self) -> str:
        lines = []
        lines.append(f"# Contract Drift Report: {self.project_id}\n")
        lines.append(f"**Contract**: {self.contract_url}")
        lines.append(f"**Service**: {self.service_url}")
        lines.append(f"**Endpoints Checked**: {self.endpoints_checked}")
        lines.append(f"**Passed**: {self.endpoints_passed}")
        lines.append(f"**Issues**: {len(self.issues)}\n")

        if not self.issues:
            lines.append("✅ No drift detected!\n")
            return "\n".join(lines)

        lines.append("## Issues\n")

        # Group by severity
        for severity in ["critical", "warning", "info"]:
            severity_issues = [i for i in self.issues if i.severity == severity]
            if severity_issues:
                emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}[severity]
                lines.append(f"### {emoji} {severity.title()} ({len(severity_issues)})\n")

                for issue in severity_issues:
                    lines.append(f"**{issue.method} {issue.path}** - {issue.issue_type}")
                    lines.append(f"- Expected: `{issue.expected}`")
                    lines.append(f"- Actual: `{issue.actual}`\n")

        return "\n".join(lines)


class ContractDriftDetector:
    """Detect drift between OpenAPI contract and live service."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def detect(
        self,
        project_id: str,
        contract_url: str,
        service_url: str,
        sample_requests: Optional[Dict[str, Dict]] = None,
    ) -> DriftReport:
        """
        Detect drift between contract and implementation.

        Args:
            project_id: Project identifier
            contract_url: URL or path to OpenAPI spec
            service_url: Base URL of the service to test
            sample_requests: Optional dict of {operationId: {body, headers}} for testing
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
        sample_requests: Dict,
    ) -> List[DriftIssue]:
        """Check a single endpoint for drift."""
        issues = []

        # Build request URL (replace path params with placeholders)
        path = endpoint.path
        for param in endpoint.parameters:
            if param.get("in") == "path":
                path = path.replace(f"{{{param['name']}}}", "test")

        url = f"{service_url}{path}"

        # Get sample request if available
        sample = sample_requests.get(endpoint.operation_id, {})
        body = sample.get("body")
        headers = sample.get("headers", {})

        # Make request
        try:
            req = Request(url, method=endpoint.method)
            for k, v in headers.items():
                req.add_header(k, v)

            if body and endpoint.method in ["POST", "PUT", "PATCH"]:
                req.data = json.dumps(body).encode()
                req.add_header("Content-Type", "application/json")

            with urlopen(req, timeout=self.timeout) as response:
                status = response.status
                response_body = response.read().decode()
                content_type = response.headers.get("Content-Type", "")

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
                        actual=response_body[:100],
                        severity="critical",
                    ))

        return issues

    def _validate_schema(
        self,
        schema: Dict,
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
```

#### Step 3: Add CLI command

```python
@cli.group()
def contract():
    """API contract commands."""
    pass

@contract.command("check")
@click.option("--project", "-p", required=True, help="Project ID")
@click.option("--service-url", "-s", help="Service URL (auto-detect from targets if not provided)")
@click.option("--output", "-o", type=click.Path(), help="Output report file")
@click.option("--fail-on-drift", is_flag=True, help="Exit with error if drift detected")
def contract_check_cmd(project: str, service_url: str, output: str, fail_on_drift: bool):
    """Check for API contract drift."""
    from contextcore.integrations.contract_drift import ContractDriftDetector

    spec = get_project_context_spec(project)
    if not spec:
        click.echo(f"Error: ProjectContext '{project}' not found", err=True)
        raise SystemExit(1)

    design = spec.get("design", {})
    contract_url = design.get("apiContract")
    if not contract_url:
        click.echo("Error: No apiContract specified in ProjectContext design", err=True)
        raise SystemExit(1)

    if not service_url:
        service_url = derive_service_url(spec.get("targets", []))

    detector = ContractDriftDetector()
    report = detector.detect(project, contract_url, service_url)

    if output:
        with open(output, "w") as f:
            f.write(report.to_markdown())
        click.echo(f"Report written to {output}")
    else:
        click.echo(report.to_markdown())

    if fail_on_drift and report.has_drift:
        raise SystemExit(1)
```

### Acceptance Criteria

- [ ] `contextcore contract check` runs drift detection
- [ ] Reports missing endpoints as critical issues
- [ ] Reports schema mismatches as warnings
- [ ] Reports unexpected properties as info
- [ ] `--fail-on-drift` causes non-zero exit on issues
- [ ] Can auto-detect service URL from ProjectContext targets

---

## Verification Checklist

After implementing all Phase 2 features:

- [ ] SLO test generator creates valid k6 scripts
- [ ] SLO test generator creates valid chaos-mesh YAMLs
- [ ] Generated tests run successfully against test service
- [ ] PR review analyzer generates appropriate checklists
- [ ] GitHub Action posts review comment on PRs
- [ ] Contract drift detector identifies known drift
- [ ] All new CLI commands have help text and work correctly

---

## Quick Implementation Prompt

```
Implement ContextCore Phase 2 features:

1. Create src/contextcore/generators/slo_tests.py with SLOTestGenerator class:
   - Generate k6 load test scripts from requirements.latencyP99/P50/throughput
   - Generate chaos-mesh YAML experiments from requirements.availability
   - Derive test intensity from business.criticality
   Add CLI command: contextcore generate slo-tests

2. Create src/contextcore/integrations/github_review.py with PRReviewAnalyzer:
   - Map risks[] to review focus areas with checklists
   - Determine required reviewers from risk type
   - Generate markdown PR comment with priority badge
   Add CLI command: contextcore review pr

3. Create src/contextcore/integrations/contract_drift.py with ContractDriftDetector:
   - Parse OpenAPI spec from design.apiContract
   - Probe live endpoints and compare responses
   - Report missing endpoints, schema mismatches
   Add CLI command: contextcore contract check

Reference: PHASE2_MEDIUM_EFFORT.md for detailed implementation steps.
```
