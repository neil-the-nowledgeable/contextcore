"""
Pytest configuration and fixtures for ContextCore tests.
"""

from __future__ import annotations

import os
from typing import Dict, Generator
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Environment Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def test_env() -> Dict[str, str]:
    """Test environment variables."""
    return {
        "CONTEXTCORE_PROJECT_ID": "test-project",
        "CONTEXTCORE_CRITICALITY": "high",
        "CONTEXTCORE_OWNER": "test-team",
        "CONTEXTCORE_DESIGN_DOC": "https://docs.test/design",
        "CONTEXTCORE_NAMESPACE": "test-namespace",
    }


@pytest.fixture(autouse=True)
def set_test_env(test_env: Dict[str, str]) -> Generator[None, None, None]:
    """Set test environment variables for each test."""
    original = {}
    for key, value in test_env.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# ============================================================================
# Model Fixtures
# ============================================================================


@pytest.fixture
def sample_project_context_spec() -> dict:
    """Sample ProjectContext spec for testing."""
    return {
        "project": {
            "id": "commerce-platform",
            "epic": "EPIC-42",
            "tasks": ["TASK-789", "TASK-790"],
        },
        "design": {
            "doc": "https://docs.internal/checkout-redesign",
            "adr": "ADR-015-event-driven-checkout",
        },
        "business": {
            "criticality": "critical",
            "value": "revenue-primary",
            "owner": "commerce-team",
        },
        "requirements": {
            "availability": "99.95",
            "latencyP99": "200ms",
            "errorBudget": "0.05",
        },
        "risks": [
            {
                "type": "security",
                "description": "Handles PII and payment data",
                "priority": "P1",
            },
        ],
        "targets": [
            {"kind": "Deployment", "name": "checkout-service"},
            {"kind": "Service", "name": "checkout-api"},
        ],
        "observability": {
            "traceSampling": 1.0,
            "metricsInterval": "10s",
            "dashboardPlacement": "featured",
            "alertChannels": ["commerce-oncall"],
        },
    }


@pytest.fixture
def minimal_project_context_spec() -> dict:
    """Minimal valid ProjectContext spec."""
    return {
        "project": {"id": "minimal-project"},
        "targets": [{"kind": "Deployment", "name": "my-app"}],
    }


# ============================================================================
# Kubernetes Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_k8s_client() -> MagicMock:
    """Mock Kubernetes client for testing."""
    client = MagicMock()

    # Mock pod with annotations
    pod = MagicMock()
    pod.metadata.annotations = {
        "contextcore.io/project": "test-project",
        "contextcore.io/criticality": "high",
        "contextcore.io/owner": "test-team",
        "contextcore.io/design-doc": "https://docs.test/design",
    }
    pod.metadata.name = "test-pod-abc123"
    pod.metadata.namespace = "test-namespace"

    client.read_namespaced_pod.return_value = pod

    return client


@pytest.fixture
def mock_k8s_deployment() -> MagicMock:
    """Mock Kubernetes deployment."""
    deployment = MagicMock()
    deployment.metadata.name = "checkout-service"
    deployment.metadata.namespace = "commerce"
    deployment.metadata.annotations = {}
    return deployment


# ============================================================================
# OTel Fixtures
# ============================================================================


@pytest.fixture
def otel_resource_attributes() -> Dict[str, str]:
    """Expected OTel resource attributes from detector."""
    return {
        "project.id": "test-project",
        "business.criticality": "high",
        "business.owner": "test-team",
        "design.doc": "https://docs.test/design",
    }


# ============================================================================
# Generator Fixtures
# ============================================================================


@pytest.fixture
def sample_service_monitor() -> dict:
    """Expected ServiceMonitor structure."""
    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "ServiceMonitor",
        "metadata": {
            "name": "checkout-service-monitor",
            "namespace": "commerce",
            "labels": {
                "contextcore.io/project": "commerce-platform",
            },
        },
        "spec": {
            "selector": {
                "matchLabels": {
                    "app": "checkout-service",
                },
            },
            "endpoints": [
                {
                    "port": "metrics",
                    "interval": "10s",
                },
            ],
        },
    }


@pytest.fixture
def sample_prometheus_rule() -> dict:
    """Expected PrometheusRule structure."""
    return {
        "apiVersion": "monitoring.coreos.com/v1",
        "kind": "PrometheusRule",
        "metadata": {
            "name": "checkout-service-slo",
            "namespace": "commerce",
        },
        "spec": {
            "groups": [
                {
                    "name": "checkout-service.slo",
                    "rules": [
                        {
                            "alert": "CheckoutServiceLatencyHigh",
                            "expr": 'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{service="checkout-service"}[5m])) > 0.2',
                            "for": "5m",
                            "labels": {
                                "severity": "critical",
                                "project": "commerce-platform",
                            },
                            "annotations": {
                                "summary": "High latency on checkout-service",
                                "design_doc": "https://docs.internal/checkout-redesign",
                                "adr": "ADR-015-event-driven-checkout",
                            },
                        },
                    ],
                },
            ],
        },
    }
