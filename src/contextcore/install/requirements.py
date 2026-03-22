"""
Installation requirements for ContextCore.

Defines what constitutes a complete ContextCore installation, organized by
category. Each requirement has a check function that returns True if met.

Environment Variables:
    GRAFANA_URL: Grafana base URL (default: http://localhost:3000)
    GRAFANA_USER: Grafana admin username (default: admin)
    GRAFANA_PASSWORD: Grafana admin password (default: admin)
    TEMPO_URL: Tempo base URL (default: http://localhost:3200)
    MIMIR_URL: Mimir base URL (default: http://localhost:9009)
    LOKI_URL: Loki base URL (default: http://localhost:3100)
    OTLP_GRPC_PORT: OTLP gRPC port (default: 4317)
    OTLP_HTTP_PORT: OTLP HTTP port (default: 4318)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import httpx


# Configuration from environment with sensible defaults
def _get_config():
    """Get configuration from environment variables."""
    return {
        "grafana_url": os.environ.get("GRAFANA_URL", "http://localhost:3000"),
        "grafana_user": os.environ.get("GRAFANA_USER", "admin"),
        "grafana_password": os.environ.get("GRAFANA_PASSWORD", "admin"),
        "tempo_url": os.environ.get("TEMPO_URL", "http://localhost:3200"),
        "mimir_url": os.environ.get("MIMIR_URL", "http://localhost:9009"),
        "loki_url": os.environ.get("LOKI_URL", "http://localhost:3100"),
        "otlp_grpc_port": int(os.environ.get("OTLP_GRPC_PORT", "4317")),
        "otlp_http_port": int(os.environ.get("OTLP_HTTP_PORT", "4318")),
    }


class RequirementCategory(str, Enum):
    """Categories of installation requirements."""

    CONFIGURATION = "configuration"  # Config files present
    INFRASTRUCTURE = "infrastructure"  # Docker, services running
    TOOLING = "tooling"  # CLI, make targets available
    OBSERVABILITY = "observability"  # Grafana datasources, dashboards
    DOCUMENTATION = "documentation"  # Runbooks, guides
    SECURITY = "security"  # Security contract completeness (REQ-SCV-001)


class RequirementStatus(str, Enum):
    """Status of a requirement check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class InstallationRequirement:
    """A single installation requirement."""

    id: str
    name: str
    description: str
    category: RequirementCategory
    check: Callable[[], bool]
    critical: bool = True  # If True, installation is incomplete without it
    depends_on: list[str] = field(default_factory=list)

    # Telemetry attributes
    metric_name: str = ""  # e.g., "contextcore.install.config.docker_compose"
    span_name: str = ""  # e.g., "install.verify.docker_compose"

    def __post_init__(self):
        if not self.metric_name:
            self.metric_name = f"contextcore.install.{self.category.value}.{self.id}"
        if not self.span_name:
            self.span_name = f"install.verify.{self.id}"


def _find_project_root() -> Optional[Path]:
    """Find the ContextCore project root."""
    # Try current directory first
    cwd = Path.cwd()
    if (cwd / "docker-compose.yaml").exists():
        return cwd

    # Try parent directories
    for parent in cwd.parents:
        if (parent / "docker-compose.yaml").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            with open(parent / "pyproject.toml") as f:
                if "contextcore" in f.read():
                    return parent

    return None


# =============================================================================
# Check Functions
# =============================================================================


def check_docker_compose_exists() -> bool:
    """Check if docker-compose.yaml exists."""
    root = _find_project_root()
    return root is not None and (root / "docker-compose.yaml").exists()


def check_makefile_exists() -> bool:
    """Check if Makefile exists."""
    root = _find_project_root()
    return root is not None and (root / "Makefile").exists()


def check_tempo_config() -> bool:
    """Check if Tempo configuration exists."""
    root = _find_project_root()
    return root is not None and (root / "tempo" / "tempo.yaml").exists()


def check_mimir_config() -> bool:
    """Check if Mimir configuration exists."""
    root = _find_project_root()
    return root is not None and (root / "mimir" / "mimir.yaml").exists()


def check_loki_config() -> bool:
    """Check if Loki configuration exists."""
    root = _find_project_root()
    return root is not None and (root / "loki" / "loki.yaml").exists()


def check_grafana_datasources() -> bool:
    """Check if Grafana datasources provisioning exists."""
    root = _find_project_root()
    if root is None:
        return False
    path = root / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
    return path.exists()


def check_grafana_dashboards_provisioning() -> bool:
    """Check if Grafana dashboards provisioning exists."""
    root = _find_project_root()
    if root is None:
        return False
    path = root / "grafana" / "provisioning" / "dashboards" / "dashboards.yaml"
    return path.exists()


def check_ops_module() -> bool:
    """Check if ops module is installed."""
    try:
        from contextcore import ops

        return hasattr(ops, "doctor") and hasattr(ops, "health_check")
    except ImportError:
        return False


def check_install_module() -> bool:
    """Check if install module is installed."""
    try:
        from contextcore import install

        return hasattr(install, "verify_installation")
    except ImportError:
        return False


def check_cli_installed() -> bool:
    """Check if contextcore CLI is available."""
    return shutil.which("contextcore") is not None


def check_docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_make_available() -> bool:
    """Check if make is available."""
    return shutil.which("make") is not None


def check_grafana_running() -> bool:
    """Check if Grafana is running and healthy."""
    config = _get_config()
    try:
        response = httpx.get(f"{config['grafana_url']}/api/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def check_tempo_running() -> bool:
    """Check if Tempo is running and healthy."""
    config = _get_config()
    try:
        response = httpx.get(f"{config['tempo_url']}/ready", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def check_mimir_running() -> bool:
    """Check if Mimir is running and healthy."""
    config = _get_config()
    try:
        response = httpx.get(f"{config['mimir_url']}/ready", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def check_loki_running() -> bool:
    """Check if Loki is running and healthy."""
    config = _get_config()
    try:
        response = httpx.get(f"{config['loki_url']}/ready", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def check_otlp_grpc_listening() -> bool:
    """Check if OTLP gRPC endpoint is listening."""
    import socket
    config = _get_config()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("localhost", config['otlp_grpc_port']))
        sock.close()
        return result == 0
    except Exception:
        return False


def check_otlp_http_listening() -> bool:
    """Check if OTLP HTTP endpoint is listening."""
    import socket
    config = _get_config()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("localhost", config['otlp_http_port']))
        sock.close()
        return result == 0
    except Exception:
        return False


def _get_grafana_auth():
    """Get Grafana authentication tuple.

    Uses GRAFANA_USER and GRAFANA_PASSWORD environment variables.
    Defaults to admin:admin if not set.
    """
    config = _get_config()
    return (config['grafana_user'], config['grafana_password'])


def _check_grafana_api(endpoint: str) -> tuple[bool, str]:
    """Check Grafana API endpoint with auth.

    Returns (success, error_message) tuple.
    """
    config = _get_config()
    try:
        response = httpx.get(
            f"{config['grafana_url']}{endpoint}",
            auth=_get_grafana_auth(),
            timeout=5,
        )
        if response.status_code == 200:
            return True, ""
        elif response.status_code == 401:
            return False, "Authentication failed. Set GRAFANA_USER/GRAFANA_PASSWORD env vars."
        else:
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)


def _get_grafana_datasources() -> list[dict] | None:
    """Get Grafana datasources list.

    Returns list of datasources or None if request failed.
    Handles auth errors gracefully.
    """
    config = _get_config()
    try:
        response = httpx.get(
            f"{config['grafana_url']}/api/datasources",
            auth=_get_grafana_auth(),
            timeout=5,
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            # Auth failed - check if datasources are provisioned by checking health
            # Grafana with anonymous auth may still have provisioned datasources
            import logging
            logging.getLogger(__name__).debug(
                "Grafana API auth failed. Set GRAFANA_USER/GRAFANA_PASSWORD env vars. "
                "Datasources may still be provisioned via config files."
            )
        return None
    except Exception:
        return None


def check_grafana_has_tempo_datasource() -> bool:
    """Check if Grafana has Tempo datasource configured."""
    datasources = _get_grafana_datasources()
    if datasources is None:
        # Fallback: check if provisioning config exists
        root = _find_project_root()
        if root:
            ds_config = root / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
            if ds_config.exists():
                with open(ds_config) as f:
                    content = f.read()
                    return "type: tempo" in content
        return False
    return any(ds.get("type") == "tempo" for ds in datasources)


def check_grafana_has_mimir_datasource() -> bool:
    """Check if Grafana has Mimir/Prometheus datasource configured."""
    datasources = _get_grafana_datasources()
    if datasources is None:
        # Fallback: check if provisioning config exists
        root = _find_project_root()
        if root:
            ds_config = root / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
            if ds_config.exists():
                with open(ds_config) as f:
                    content = f.read()
                    return "type: prometheus" in content
        return False
    return any(ds.get("type") == "prometheus" for ds in datasources)


def check_grafana_has_loki_datasource() -> bool:
    """Check if Grafana has Loki datasource configured."""
    datasources = _get_grafana_datasources()
    if datasources is None:
        # Fallback: check if provisioning config exists
        root = _find_project_root()
        if root:
            ds_config = root / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
            if ds_config.exists():
                with open(ds_config) as f:
                    content = f.read()
                    return "type: loki" in content
        return False
    return any(ds.get("type") == "loki" for ds in datasources)


def check_grafana_has_dashboards() -> bool:
    """Check if Grafana has ContextCore dashboards.

    Checks both API (if accessible) and provisioning directory.
    """
    config = _get_config()

    # Try API first
    try:
        response = httpx.get(
            f"{config['grafana_url']}/api/search?type=dash-db&tag=contextcore",
            auth=_get_grafana_auth(),
            timeout=5,
        )
        if response.status_code == 200:
            dashboards = response.json()
            if len(dashboards) > 0:
                return True
    except Exception:
        pass

    # Fallback: check provisioning directory
    root = _find_project_root()
    if root:
        dash_dir = root / "grafana" / "provisioning" / "dashboards" / "json"
        if dash_dir.exists():
            json_files = list(dash_dir.glob("*.json"))
            return len(json_files) > 0

    return False


def check_operational_resilience_doc() -> bool:
    """Check if operational resilience documentation exists."""
    root = _find_project_root()
    if root is None:
        return False
    return (root / "docs" / "OPERATIONAL_RESILIENCE.md").exists()


def check_operational_runbook() -> bool:
    """Check if operational runbook exists."""
    root = _find_project_root()
    if root is None:
        return False
    return (root / "docs" / "OPERATIONAL_RUNBOOK.md").exists()


def check_data_directories() -> bool:
    """Check if data directories exist for persistence.

    This check verifies that persistent storage is configured. It passes if:
    1. Local data/ directory exists with subdirs, OR
    2. Services are running (implying Kubernetes PVCs or similar)
    """
    root = _find_project_root()

    # Check for local data directory (docker-compose setup)
    if root is not None:
        data_dir = root / "data"
        if data_dir.exists():
            subdirs = ["grafana", "tempo", "mimir", "loki"]
            if any((data_dir / subdir).exists() for subdir in subdirs):
                return True

    # If services are running, assume persistence is configured (K8s PVCs)
    # This handles Kubernetes deployments where data dirs aren't local
    if check_grafana_running() and check_mimir_running():
        return True

    return False


# =============================================================================
# Security Contract Checks (REQ-SCV-002–004)
# =============================================================================


def _load_contextcore_yaml() -> Optional[dict]:
    """Load .contextcore.yaml from project root, returning parsed dict or None."""
    root = _find_project_root()
    if root is None:
        return None
    yaml_path = root / ".contextcore.yaml"
    if not yaml_path.exists():
        return None
    try:
        import yaml
        return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_security_data_stores(data: dict) -> list[dict]:
    """Extract spec.security.data_stores from parsed .contextcore.yaml."""
    spec = data.get("spec") or {}
    security = spec.get("security") or {}
    stores = security.get("data_stores", security.get("dataStores", []))
    return stores if isinstance(stores, list) else []


def check_security_manifest_declaration() -> bool:
    """Check that spec.security is declared when databases are detected (REQ-SCV-002).

    Passes when:
    - spec.security.data_stores exists, OR
    - No detected databases in the most recent export, OR
    - No .contextcore.yaml exists (not applicable)
    Fails when detected databases exist but spec.security is absent.
    """
    data = _load_contextcore_yaml()
    if data is None:
        return True  # No manifest — not applicable

    # If spec.security.data_stores declared → pass
    if _get_security_data_stores(data):
        return True

    # Check for detected databases in most recent export
    root = _find_project_root()
    if root is None:
        return True
    for candidate in (root / "out" / "export", root / "output"):
        onboarding = candidate / "onboarding-metadata.json"
        if onboarding.is_file():
            try:
                import json
                ob = json.loads(onboarding.read_text(encoding="utf-8"))
                hints = ob.get("instrumentation_hints", {})
                for svc_hints in hints.values():
                    if isinstance(svc_hints, dict) and svc_hints.get("detected_databases"):
                        return False  # Databases detected but no spec.security
            except Exception:
                pass
    return True  # No detected databases — not applicable


def check_security_audit_policy() -> bool:
    """Check that high-sensitivity stores have audit_access: true (REQ-SCV-003)."""
    data = _load_contextcore_yaml()
    if data is None:
        return True
    stores = _get_security_data_stores(data)
    if not stores:
        return True
    for store in stores:
        if not isinstance(store, dict):
            continue
        sensitivity = store.get("sensitivity", "medium")
        if sensitivity == "high":
            policy = store.get("access_policy", store.get("accessPolicy")) or {}
            if not policy.get("audit_access", policy.get("auditAccess", False)):
                return False
    return True


_KNOWN_CREDENTIAL_SOURCES = {
    "env_var", "environment_variable", "secrets_manager", "workload_identity",
}


def check_security_credential_sources() -> bool:
    """Check that credential_source values are known mechanisms (REQ-SCV-004)."""
    data = _load_contextcore_yaml()
    if data is None:
        return True
    stores = _get_security_data_stores(data)
    if not stores:
        return True
    for store in stores:
        if not isinstance(store, dict):
            continue
        cred = store.get("credential_source", store.get("credentialSource", ""))
        if cred and cred not in _KNOWN_CREDENTIAL_SOURCES:
            return False
    return True


# =============================================================================
# Installation Requirements Registry
# =============================================================================

INSTALLATION_REQUIREMENTS: list[InstallationRequirement] = [
    # Configuration
    InstallationRequirement(
        id="docker_compose",
        name="Docker Compose Configuration",
        description="docker-compose.yaml exists with service definitions",
        category=RequirementCategory.CONFIGURATION,
        check=check_docker_compose_exists,
        critical=True,
    ),
    InstallationRequirement(
        id="makefile",
        name="Makefile",
        description="Makefile with operational targets (doctor, up, health, etc.)",
        category=RequirementCategory.CONFIGURATION,
        check=check_makefile_exists,
        critical=True,
    ),
    InstallationRequirement(
        id="tempo_config",
        name="Tempo Configuration",
        description="tempo/tempo.yaml with OTLP receivers and storage",
        category=RequirementCategory.CONFIGURATION,
        check=check_tempo_config,
        critical=True,
    ),
    InstallationRequirement(
        id="mimir_config",
        name="Mimir Configuration",
        description="mimir/mimir.yaml with metrics storage",
        category=RequirementCategory.CONFIGURATION,
        check=check_mimir_config,
        critical=True,
    ),
    InstallationRequirement(
        id="loki_config",
        name="Loki Configuration",
        description="loki/loki.yaml with log storage",
        category=RequirementCategory.CONFIGURATION,
        check=check_loki_config,
        critical=True,
    ),
    InstallationRequirement(
        id="grafana_datasources_config",
        name="Grafana Datasources Provisioning",
        description="Grafana datasources auto-provisioning configuration",
        category=RequirementCategory.CONFIGURATION,
        check=check_grafana_datasources,
        critical=True,
    ),
    InstallationRequirement(
        id="grafana_dashboards_config",
        name="Grafana Dashboards Provisioning",
        description="Grafana dashboards auto-provisioning configuration",
        category=RequirementCategory.CONFIGURATION,
        check=check_grafana_dashboards_provisioning,
        critical=False,
    ),
    # Tooling
    InstallationRequirement(
        id="cli_installed",
        name="ContextCore CLI",
        description="contextcore command available in PATH",
        category=RequirementCategory.TOOLING,
        check=check_cli_installed,
        critical=True,
    ),
    InstallationRequirement(
        id="ops_module",
        name="Operations Module",
        description="contextcore.ops module with doctor, health, backup",
        category=RequirementCategory.TOOLING,
        check=check_ops_module,
        critical=True,
    ),
    InstallationRequirement(
        id="install_module",
        name="Installation Module",
        description="contextcore.install module with verification",
        category=RequirementCategory.TOOLING,
        check=check_install_module,
        critical=False,
    ),
    InstallationRequirement(
        id="docker_available",
        name="Docker Available",
        description="Docker daemon is running and accessible",
        category=RequirementCategory.TOOLING,
        check=check_docker_available,
        critical=True,
    ),
    InstallationRequirement(
        id="make_available",
        name="Make Available",
        description="make command available for operational targets",
        category=RequirementCategory.TOOLING,
        check=check_make_available,
        critical=False,
    ),
    # Infrastructure
    InstallationRequirement(
        id="grafana_running",
        name="Grafana Running",
        description="Grafana service healthy at localhost:3000",
        category=RequirementCategory.INFRASTRUCTURE,
        check=check_grafana_running,
        critical=True,
        depends_on=["docker_compose", "docker_available"],
    ),
    InstallationRequirement(
        id="tempo_running",
        name="Tempo Running",
        description="Tempo service healthy at localhost:3200",
        category=RequirementCategory.INFRASTRUCTURE,
        check=check_tempo_running,
        critical=True,
        depends_on=["docker_compose", "docker_available", "tempo_config"],
    ),
    InstallationRequirement(
        id="mimir_running",
        name="Mimir Running",
        description="Mimir service healthy at localhost:9009",
        category=RequirementCategory.INFRASTRUCTURE,
        check=check_mimir_running,
        critical=True,
        depends_on=["docker_compose", "docker_available", "mimir_config"],
    ),
    InstallationRequirement(
        id="loki_running",
        name="Loki Running",
        description="Loki service healthy at localhost:3100",
        category=RequirementCategory.INFRASTRUCTURE,
        check=check_loki_running,
        critical=True,
        depends_on=["docker_compose", "docker_available", "loki_config"],
    ),
    InstallationRequirement(
        id="otlp_grpc",
        name="OTLP gRPC Endpoint",
        description="OTLP gRPC receiver listening at localhost:4317",
        category=RequirementCategory.INFRASTRUCTURE,
        check=check_otlp_grpc_listening,
        critical=True,
        depends_on=["tempo_running"],
    ),
    InstallationRequirement(
        id="otlp_http",
        name="OTLP HTTP Endpoint",
        description="OTLP HTTP receiver listening at localhost:4318",
        category=RequirementCategory.INFRASTRUCTURE,
        check=check_otlp_http_listening,
        critical=True,
        depends_on=["tempo_running"],
    ),
    InstallationRequirement(
        id="data_persistence",
        name="Data Persistence",
        description="Data directories exist for persistent storage",
        category=RequirementCategory.INFRASTRUCTURE,
        check=check_data_directories,
        critical=True,
        depends_on=["docker_compose"],
    ),
    # Observability
    InstallationRequirement(
        id="grafana_tempo_datasource",
        name="Tempo Datasource",
        description="Grafana has Tempo datasource for traces",
        category=RequirementCategory.OBSERVABILITY,
        check=check_grafana_has_tempo_datasource,
        critical=True,
        depends_on=["grafana_running"],
    ),
    InstallationRequirement(
        id="grafana_mimir_datasource",
        name="Mimir Datasource",
        description="Grafana has Mimir/Prometheus datasource for metrics",
        category=RequirementCategory.OBSERVABILITY,
        check=check_grafana_has_mimir_datasource,
        critical=True,
        depends_on=["grafana_running"],
    ),
    InstallationRequirement(
        id="grafana_loki_datasource",
        name="Loki Datasource",
        description="Grafana has Loki datasource for logs",
        category=RequirementCategory.OBSERVABILITY,
        check=check_grafana_has_loki_datasource,
        critical=True,
        depends_on=["grafana_running"],
    ),
    InstallationRequirement(
        id="grafana_dashboards",
        name="Dashboards Provisioned",
        description="ContextCore dashboards available in Grafana",
        category=RequirementCategory.OBSERVABILITY,
        check=check_grafana_has_dashboards,
        critical=False,
        depends_on=["grafana_running"],
    ),
    # Documentation
    InstallationRequirement(
        id="operational_resilience_doc",
        name="Operational Resilience Guide",
        description="docs/OPERATIONAL_RESILIENCE.md with architecture",
        category=RequirementCategory.DOCUMENTATION,
        check=check_operational_resilience_doc,
        critical=False,
    ),
    InstallationRequirement(
        id="operational_runbook",
        name="Operational Runbook",
        description="docs/OPERATIONAL_RUNBOOK.md with quick reference",
        category=RequirementCategory.DOCUMENTATION,
        check=check_operational_runbook,
        critical=False,
    ),
    # Security (REQ-SCV-002–004)
    InstallationRequirement(
        id="security_manifest_declaration",
        name="Security Contract Declaration",
        description="spec.security.data_stores declared when databases detected in communication graph",
        category=RequirementCategory.SECURITY,
        check=check_security_manifest_declaration,
        critical=False,
        depends_on=["cli_installed"],
    ),
    InstallationRequirement(
        id="security_audit_policy",
        name="High-Sensitivity Audit Policy",
        description="High-sensitivity data stores have access_policy.audit_access enabled",
        category=RequirementCategory.SECURITY,
        check=check_security_audit_policy,
        critical=False,
        depends_on=["security_manifest_declaration"],
    ),
    InstallationRequirement(
        id="security_credential_sources",
        name="Credential Source Validation",
        description="Data store credential_source values are known mechanisms",
        category=RequirementCategory.SECURITY,
        check=check_security_credential_sources,
        critical=False,
        depends_on=["security_manifest_declaration"],
    ),
]


def get_requirements_by_category(
    category: RequirementCategory,
) -> list[InstallationRequirement]:
    """Get all requirements for a specific category."""
    return [r for r in INSTALLATION_REQUIREMENTS if r.category == category]


def get_critical_requirements() -> list[InstallationRequirement]:
    """Get all critical requirements."""
    return [r for r in INSTALLATION_REQUIREMENTS if r.critical]


def get_requirement_by_id(req_id: str) -> Optional[InstallationRequirement]:
    """Get a requirement by its ID."""
    for req in INSTALLATION_REQUIREMENTS:
        if req.id == req_id:
            return req
    return None
