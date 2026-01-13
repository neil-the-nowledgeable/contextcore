"""
OpenTelemetry Resource Detector for ProjectContext.

This detector reads project context from Kubernetes pod annotations and
injects it into all telemetry (traces, metrics, logs) as resource attributes.

Usage:
    from opentelemetry.sdk.resources import get_aggregated_resources
    from opentelemetry.sdk.trace import TracerProvider
    from contextcore import ProjectContextDetector

    resource = get_aggregated_resources([ProjectContextDetector()])
    provider = TracerProvider(resource=resource)

All spans/metrics/logs will include attributes like:
    - project.id
    - project.epic
    - business.criticality
    - design.doc
    - etc.
"""

import logging
import os
from typing import Optional

from opentelemetry.sdk.resources import Resource, ResourceDetector

logger = logging.getLogger(__name__)

# Annotation prefix for ContextCore
ANNOTATION_PREFIX = "contextcore.io/"

# Mapping from annotation keys to OTel resource attribute names
ANNOTATION_TO_ATTRIBUTE = {
    # Project
    "project": "project.id",
    "project-id": "project.id",
    "epic": "project.epic",
    "epic-id": "project.epic",
    "task": "project.task",
    "task-id": "project.task",
    "trace-id": "project.trace_id",

    # Design
    "design-doc": "design.doc",
    "adr": "design.adr",
    "api-contract": "design.api_contract",

    # Business
    "criticality": "business.criticality",
    "business-value": "business.value",
    "owner": "business.owner",
    "cost-center": "business.cost_center",

    # Requirements
    "slo-availability": "requirement.availability",
    "slo-latency-p99": "requirement.latency_p99",
    "slo-latency-p50": "requirement.latency_p50",
    "error-budget": "requirement.error_budget",

    # Risk
    "risk-type": "risk.type",
    "risk-priority": "risk.priority",

    # K8s context
    "projectcontext": "k8s.projectcontext.name",
}


class ProjectContextDetector(ResourceDetector):
    """
    Detect project context from Kubernetes pod annotations.

    This detector reads annotations from the pod's metadata and converts
    them to OpenTelemetry resource attributes. It supports both:

    1. Direct pod annotation reading (when running in K8s)
    2. Environment variable fallback (for local development)

    The detector looks for annotations with the prefix "contextcore.io/"
    and maps them to semantic convention attributes.
    """

    def __init__(
        self,
        pod_name: Optional[str] = None,
        namespace: Optional[str] = None,
        kubeconfig: Optional[str] = None,
    ):
        """
        Initialize the detector.

        Args:
            pod_name: Pod name (defaults to HOSTNAME env var)
            namespace: Namespace (defaults to mounted namespace file or 'default')
            kubeconfig: Path to kubeconfig (defaults to in-cluster config)
        """
        self._pod_name = pod_name
        self._namespace = namespace
        self._kubeconfig = kubeconfig

    def detect(self) -> Resource:
        """
        Detect project context and return as Resource.

        Attempts to read from K8s annotations first, then falls back to
        environment variables for local development.
        """
        attributes = {}

        # Try K8s annotations first
        try:
            k8s_attrs = self._detect_from_k8s()
            attributes.update(k8s_attrs)
        except Exception as e:
            logger.debug(f"Could not detect from K8s: {e}")

        # Fallback to environment variables
        env_attrs = self._detect_from_env()
        for key, value in env_attrs.items():
            if key not in attributes:
                attributes[key] = value

        if attributes:
            logger.info(f"Detected project context: {list(attributes.keys())}")

        return Resource.create(attributes)

    def _detect_from_k8s(self) -> dict[str, str]:
        """Read project context from K8s pod annotations."""
        try:
            from kubernetes import client, config
        except ImportError:
            logger.debug("kubernetes package not installed, skipping K8s detection")
            return {}

        # Determine pod name and namespace
        pod_name = self._pod_name or os.environ.get("HOSTNAME")
        namespace = self._namespace or self._get_namespace()

        if not pod_name or not namespace:
            return {}

        # Load kubeconfig
        try:
            if self._kubeconfig:
                config.load_kube_config(config_file=self._kubeconfig)
            else:
                config.load_incluster_config()
        except Exception:
            config.load_kube_config()

        # Get pod annotations
        v1 = client.CoreV1Api()
        try:
            pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        except Exception as e:
            logger.debug(f"Could not read pod {namespace}/{pod_name}: {e}")
            return {}

        annotations = pod.metadata.annotations or {}
        return self._parse_annotations(annotations)

    def _detect_from_env(self) -> dict[str, str]:
        """Read project context from environment variables."""
        attributes = {}

        # Map environment variables to attributes
        env_mapping = {
            "CONTEXTCORE_PROJECT_ID": "project.id",
            "CONTEXTCORE_EPIC": "project.epic",
            "CONTEXTCORE_TASK": "project.task",
            "CONTEXTCORE_CRITICALITY": "business.criticality",
            "CONTEXTCORE_BUSINESS_VALUE": "business.value",
            "CONTEXTCORE_OWNER": "business.owner",
            "CONTEXTCORE_DESIGN_DOC": "design.doc",
            "CONTEXTCORE_ADR": "design.adr",
            "CONTEXTCORE_SLO_AVAILABILITY": "requirement.availability",
            "CONTEXTCORE_SLO_LATENCY_P99": "requirement.latency_p99",
        }

        for env_var, attr_name in env_mapping.items():
            value = os.environ.get(env_var)
            if value:
                attributes[attr_name] = value

        return attributes

    def _get_namespace(self) -> Optional[str]:
        """Get namespace from mounted service account or environment."""
        # Try mounted namespace file (in-cluster)
        namespace_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        if os.path.exists(namespace_file):
            with open(namespace_file) as f:
                return f.read().strip()

        # Try environment variable
        return os.environ.get("CONTEXTCORE_NAMESPACE", "default")

    def _parse_annotations(self, annotations: dict[str, str]) -> dict[str, str]:
        """Parse contextcore.io annotations into resource attributes."""
        attributes = {}

        for key, value in annotations.items():
            if not key.startswith(ANNOTATION_PREFIX):
                continue

            # Remove prefix
            annotation_key = key[len(ANNOTATION_PREFIX):]

            # Map to attribute name
            attr_name = ANNOTATION_TO_ATTRIBUTE.get(annotation_key)
            if attr_name:
                attributes[attr_name] = value
            else:
                # Unknown annotation, use as-is with prefix
                attributes[f"contextcore.{annotation_key}"] = value

        # Also include standard K8s context
        if "k8s.pod.name" not in attributes:
            pod_name = self._pod_name or os.environ.get("HOSTNAME")
            if pod_name:
                attributes["k8s.pod.name"] = pod_name

        if "k8s.namespace.name" not in attributes:
            namespace = self._namespace or self._get_namespace()
            if namespace:
                attributes["k8s.namespace.name"] = namespace

        return attributes


def get_project_context() -> dict[str, str]:
    """
    Convenience function to get project context as a dictionary.

    Useful for debugging or when you need the context without creating
    a full Resource object.
    """
    detector = ProjectContextDetector()
    resource = detector.detect()
    return dict(resource.attributes)
