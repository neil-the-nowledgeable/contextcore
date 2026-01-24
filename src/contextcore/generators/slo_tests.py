"""
SLO-Driven Test Generation module for ContextCore.

This module generates load tests (k6) and chaos tests (chaos-mesh) directly from 
ProjectContext requirements, eliminating manual test specification.
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path
import re

__all__ = [
    'TestType', 'GeneratedTest', 'SLOTestGenerator', 
    'parse_duration', 'parse_throughput', 'write_tests'
]

# Enums
class TestType(Enum):
    """Enumeration of supported test types."""
    LOAD = "LOAD"
    CHAOS = "CHAOS"
    AVAILABILITY = "AVAILABILITY"
    LATENCY = "LATENCY"

# Data Classes
@dataclass
class GeneratedTest:
    """Represents a generated test with its metadata and content."""
    name: str
    test_type: TestType
    derived_from: str
    content: str
    file_extension: str

# Parsing Functions
def parse_duration(duration_str: str) -> int:
    """
    Parse a duration string in formats like "200ms", "1s", "5m" into milliseconds.
    
    Args:
        duration_str: Duration string (e.g., "200ms", "1s", "5m", "2h")
        
    Returns:
        Duration in milliseconds
        
    Raises:
        ValueError: If duration format is invalid
    """
    if not duration_str:
        raise ValueError("Duration string cannot be empty")
    
    # Handle milliseconds with 'ms' suffix
    ms_match = re.match(r'^(\d+)ms$', duration_str.strip())
    if ms_match:
        return int(ms_match.group(1))
    
    # Handle other units (s, m, h)
    match = re.match(r'^(\d+)([smh])$', duration_str.strip())
    if match:
        value, unit = match.groups()
        value = int(value)
        
        unit_multipliers = {
            's': 1000,      # seconds to milliseconds
            'm': 60000,     # minutes to milliseconds  
            'h': 3600000    # hours to milliseconds
        }
        return value * unit_multipliers[unit]
    
    # Handle bare numbers (assume milliseconds)
    if duration_str.strip().isdigit():
        return int(duration_str.strip())
    
    raise ValueError(f"Invalid duration format: {duration_str}")

def parse_throughput(throughput_str: str) -> int:
    """
    Parse a throughput string in format like "100rps" into numeric value.
    
    Args:
        throughput_str: Throughput string (e.g., "100rps")
        
    Returns:
        Throughput as integer requests per second
        
    Raises:
        ValueError: If throughput format is invalid
    """
    if not throughput_str:
        raise ValueError("Throughput string cannot be empty")
    
    match = re.match(r'^(\d+)rps$', throughput_str.strip())
    if match:
        return int(match.group(1))
    
    raise ValueError(f"Invalid throughput format: {throughput_str}")

# Main Generator
class SLOTestGenerator:
    """Generates SLO-driven load and chaos tests from ProjectContext specifications."""
    
    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize the SLO test generator.
        
        Args:
            templates_dir: Optional custom templates directory (unused in current implementation)
        """
        self.templates_dir = templates_dir
        self._load_templates()

    def _load_templates(self) -> None:
        """Load test templates as string constants."""
        # K6 load test template with constant-arrival-rate and spike scenarios
        self.k6_load_template = '''import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

let errorRate = new Rate('errors');

export let options = {
    thresholds: {
        'http_req_duration': ['p(99)<{{latency_p99}}', 'p(50)<{{latency_p50}}'],
        'errors': ['rate<{{error_budget}}'],
        'http_reqs': ['rate>{{min_throughput}}'],
    },
    scenarios: {
        constant_load: {
            executor: 'constant-arrival-rate',
            rate: {{throughput}},
            timeUnit: '1s',
            duration: '5m',
            preAllocatedVUs: 10,
            maxVUs: 100,
        },
        spike_test: {
            executor: 'constant-arrival-rate',
            rate: {{spike_throughput}},
            timeUnit: '1s',
            duration: '30s',
            startTime: '5m',
            preAllocatedVUs: 20,
            maxVUs: 200,
        },
    }
};

export default function () {
    const response = http.get('{{endpoint}}');
    const result = check(response, {
        'status is 200': (r) => r.status === 200,
        'response time < {{latency_p99}}ms': (r) => r.timings.duration < {{latency_p99}},
    });
    errorRate.add(!result);
    sleep(1);
}

export function handleSummary(data) {
    return {
        'summary.json': JSON.stringify(data, null, 2),
        stdout: textSummary(data, { indent: ' ', enableColors: true }),
    };
}'''

        # K6 latency test template with staged load profile
        self.k6_latency_template = '''import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

let errorRate = new Rate('errors');
let latencyTrend = new Trend('custom_latency');

export let options = {
    thresholds: {
        'http_req_duration': ['p(99)<{{latency_p99}}', 'p(50)<{{latency_p50}}'],
        'errors': ['rate<{{error_budget}}'],
        'custom_latency': ['p(99)<{{latency_p99}}'],
    },
    scenarios: {
        latency_test: {
            executor: 'ramping-vus',
            stages: [
                { duration: '2m', target: 10 },
                { duration: '5m', target: 50 },
                { duration: '2m', target: 100 },
                { duration: '5m', target: 100 },
                { duration: '2m', target: 0 },
            ],
        },
    }
};

export default function () {
    const response = http.get('{{endpoint}}');
    latencyTrend.add(response.timings.duration);
    const result = check(response, {
        'status is 200': (r) => r.status === 200,
        'latency P99 < {{latency_p99}}ms': (r) => r.timings.duration < {{latency_p99}},
        'latency P50 < {{latency_p50}}ms': (r) => r.timings.duration < {{latency_p50}},
    });
    errorRate.add(!result);
    sleep(1);
}

export function handleSummary(data) {
    return {
        'summary.json': JSON.stringify(data, null, 2),
        stdout: textSummary(data, { indent: ' ', enableColors: true }),
    };
}'''

        # Chaos-Mesh PodChaos template
        self.pod_chaos_template = '''apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: {{name}}-pod-kill
  labels:
    contextcore.io/project: "{{project_id}}"
    contextcore.io/test-type: "chaos"
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces: ["{{namespace}}"]
    labelSelectors:
      app: "{{app}}"
  scheduler:
    cron: "*/10 * * * *"
---'''

        # Chaos-Mesh NetworkChaos template (for critical/high criticality)
        self.network_chaos_template = '''apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: {{name}}-network-delay
  labels:
    contextcore.io/project: "{{project_id}}"
    contextcore.io/test-type: "chaos"
spec:
  action: delay
  mode: one
  selector:
    namespaces: ["{{namespace}}"]
    labelSelectors:
      app: "{{app}}"
  delay:
    latency: "100ms"
    correlation: "100"
    jitter: "0ms"
  direction: to
  scheduler:
    cron: "*/15 * * * *"
---'''

        # Chaos-Mesh StressChaos template (critical only)
        self.stress_chaos_template = '''apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: {{name}}-cpu-stress
  labels:
    contextcore.io/project: "{{project_id}}"
    contextcore.io/test-type: "chaos"
spec:
  mode: one
  selector:
    namespaces: ["{{namespace}}"]
    labelSelectors:
      app: "{{app}}"
  duration: "2m"
  stressors:
    cpu:
      workers: 2
      load: 80
  scheduler:
    cron: "*/20 * * * *"
---'''

    def generate(self, project_id: str, spec: Dict[str, Any], test_types: List[TestType]) -> List[GeneratedTest]:
        """
        Generate tests based on ProjectContext specification.
        
        Args:
            project_id: Unique identifier for the project
            spec: ProjectContext specification dictionary
            test_types: List of test types to generate
            
        Returns:
            List of generated tests
        """
        tests = []
        requirements = spec.get("requirements", {})
        targets = spec.get("targets", [])
        business = spec.get("business", {})

        # Get service endpoint from targets
        endpoint = self._get_service_endpoint(targets, spec)

        # Generate requested test types
        if TestType.LOAD in test_types:
            tests.append(self._generate_load_test(project_id, requirements, endpoint))
        
        if TestType.LATENCY in test_types:
            tests.append(self._generate_latency_test(project_id, requirements, endpoint))
        
        if TestType.CHAOS in test_types or TestType.AVAILABILITY in test_types:
            tests.extend(self._generate_chaos_tests(project_id, requirements, targets, business))

        return tests

    def _get_service_endpoint(self, targets: List[Dict[str, Any]], spec: Dict[str, Any]) -> str:
        """
        Extract service endpoint from targets configuration.
        
        Args:
            targets: List of service/deployment targets
            spec: Full ProjectContext specification
            
        Returns:
            Service endpoint URL
            
        Raises:
            ValueError: If no targets are specified
        """
        if not targets:
            raise ValueError("No service targets specified in ProjectContext")
        
        # Use the first service target to construct endpoint
        target = targets[0]
        name = target.get("name", "unknown-service")
        namespace = target.get("namespace", "default")
        port = target.get("port", 80)
        
        # Construct service endpoint (assumes Kubernetes service DNS)
        return f"http://{name}.{namespace}.svc.cluster.local:{port}"

    def _generate_latency_test(self, project_id: str, requirements: Dict[str, Any], endpoint: str) -> GeneratedTest:
        """
        Generate k6 latency test focused on response time validation.
        
        Args:
            project_id: Project identifier
            requirements: SLO requirements dictionary
            endpoint: Target service endpoint
            
        Returns:
            Generated latency test
        """
        # Parse requirements with sensible defaults
        latency_p99 = parse_duration(requirements.get("latencyP99", "500ms"))
        latency_p50 = parse_duration(requirements.get("latencyP50", "200ms"))
        error_budget = float(requirements.get("errorBudget", "0.01"))

        # Replace template placeholders
        content = (self.k6_latency_template
                  .replace("{{latency_p99}}", str(latency_p99))
                  .replace("{{latency_p50}}", str(latency_p50))
                  .replace("{{error_budget}}", str(error_budget))
                  .replace("{{endpoint}}", endpoint))

        return GeneratedTest(
            name=f"{project_id}_latency_test",
            test_type=TestType.LATENCY,
            derived_from=f"latencyP99={requirements.get('latencyP99', '500ms')}, latencyP50={requirements.get('latencyP50', '200ms')}",
            content=content,
            file_extension=".js"
        )

    def _generate_load_test(self, project_id: str, requirements: Dict[str, Any], endpoint: str) -> GeneratedTest:
        """
        Generate k6 load test with constant-arrival-rate and spike scenarios.
        
        Args:
            project_id: Project identifier
            requirements: SLO requirements dictionary
            endpoint: Target service endpoint
            
        Returns:
            Generated load test
        """
        # Parse requirements with sensible defaults
        throughput = parse_throughput(requirements.get("throughput", "100rps"))
        latency_p99 = parse_duration(requirements.get("latencyP99", "500ms"))
        latency_p50 = parse_duration(requirements.get("latencyP50", "200ms"))
        error_budget = float(requirements.get("errorBudget", "0.01"))
        
        # Calculate spike throughput (2x normal load)
        spike_throughput = throughput * 2
        min_throughput = int(throughput * 0.8)  # Allow 20% variance

        # Replace template placeholders
        content = (self.k6_load_template
                  .replace("{{throughput}}", str(throughput))
                  .replace("{{spike_throughput}}", str(spike_throughput))
                  .replace("{{min_throughput}}", str(min_throughput))
                  .replace("{{latency_p99}}", str(latency_p99))
                  .replace("{{latency_p50}}", str(latency_p50))
                  .replace("{{error_budget}}", str(error_budget))
                  .replace("{{endpoint}}", endpoint))

        return GeneratedTest(
            name=f"{project_id}_load_test",
            test_type=TestType.LOAD,
            derived_from=f"throughput={requirements.get('throughput', '100rps')}, latencyP99={requirements.get('latencyP99', '500ms')}",
            content=content,
            file_extension=".js"
        )

    def _generate_chaos_tests(self, project_id: str, requirements: Dict[str, Any], 
                            targets: List[Dict[str, Any]], business: Dict[str, Any]) -> List[GeneratedTest]:
        """
        Generate chaos-mesh YAML tests based on business criticality.
        
        Args:
            project_id: Project identifier
            requirements: SLO requirements dictionary
            targets: List of service/deployment targets
            business: Business context (criticality level)
            
        Returns:
            List of generated chaos tests
        """
        criticality = business.get("criticality", "low")
        chaos_tests = []

        for target in targets:
            namespace = target.get("namespace", "default")
            app_name = target.get("name", "unknown-app")
            base_name