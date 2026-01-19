"""
Centralized configuration for ContextCore.

Uses Pydantic BaseSettings for environment variable integration
and validation. All configurable values should be defined here.

Configuration sources (in order of precedence):
1. Explicit constructor arguments
2. Environment variables (CONTEXTCORE_*)
3. .env file
4. Default values

Example:
    from contextcore.config import get_config

    config = get_config()
    print(config.otlp_endpoint)  # From CONTEXTCORE_OTLP_ENDPOINT or default

    # Override at runtime
    config = get_config(otlp_endpoint="custom:4317")
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ContextCoreConfig(BaseSettings):
    """
    Central configuration for ContextCore.

    All settings can be overridden via environment variables
    prefixed with CONTEXTCORE_.

    Example:
        export CONTEXTCORE_OTLP_ENDPOINT=collector:4317
        export CONTEXTCORE_LOG_LEVEL=debug
    """

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTCORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service identification
    service_name: str = Field(
        default="contextcore",
        description="Service name for telemetry attribution",
    )
    service_namespace: str = Field(
        default="contextcore",
        description="Service namespace for telemetry attribution",
    )

    # Project defaults
    default_project: str = Field(
        default="default",
        description="Default project ID when not specified",
    )

    # State persistence
    state_dir: str = Field(
        default="~/.contextcore/state",
        description="Directory for persisting task state",
    )
    storage_dir: str = Field(
        default="~/.contextcore/storage",
        description="Directory for file-based storage backend",
    )

    # OTLP export
    otlp_endpoint: str = Field(
        default="localhost:4317",
        description="OTLP gRPC endpoint for trace/metric export",
    )
    otlp_insecure: bool = Field(
        default=True,
        description="Use insecure connection to OTLP endpoint",
    )
    otlp_headers: Optional[str] = Field(
        default=None,
        description="Optional headers for OTLP (key=value,key=value)",
    )

    # Logging
    log_level: Literal["debug", "info", "warning", "error"] = Field(
        default="info",
        description="Logging level for ContextCore",
    )
    log_format: Literal["json", "text"] = Field(
        default="json",
        description="Log output format (json for Loki, text for console)",
    )

    # Kubernetes
    kubernetes_namespace: str = Field(
        default="default",
        description="Default Kubernetes namespace",
    )
    kubeconfig: Optional[str] = Field(
        default=None,
        description="Path to kubeconfig file (auto-detected if not set)",
    )

    # Storage backend
    storage_type: Literal["auto", "kubernetes", "file", "memory"] = Field(
        default="auto",
        description="Storage backend type (auto-detects if not set)",
    )

    # Task tracking
    auto_save_interval_seconds: int = Field(
        default=30,
        ge=5,
        description="Interval for auto-saving task state",
    )
    max_active_spans: int = Field(
        default=1000,
        ge=10,
        description="Maximum number of active task spans",
    )

    # Metrics
    metrics_prefix: str = Field(
        default="",
        description="Prefix for all emitted metrics (project-specific)",
    )

    @field_validator("state_dir", "storage_dir")
    @classmethod
    def expand_path(cls, v: str) -> str:
        """Expand ~ and environment variables in paths."""
        return os.path.expanduser(os.path.expandvars(v))

    @field_validator("otlp_endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate OTLP endpoint format."""
        # Remove protocol prefix if present (SDK adds it)
        if v.startswith("http://"):
            v = v[7:]
        elif v.startswith("https://"):
            v = v[8:]
        return v

    def get_state_path(self, project: Optional[str] = None) -> Path:
        """Get state directory path for a project."""
        base = Path(self.state_dir)
        if project:
            return base / project
        return base

    def get_storage_path(self, namespace: Optional[str] = None) -> Path:
        """Get storage directory path for a namespace."""
        base = Path(self.storage_dir)
        if namespace:
            return base / namespace
        return base


# Global singleton
_config: Optional[ContextCoreConfig] = None


def get_config(**overrides) -> ContextCoreConfig:
    """
    Get the global configuration instance.

    Creates a singleton on first call. Subsequent calls return
    the same instance unless overrides are provided.

    Args:
        **overrides: Override any config values

    Returns:
        ContextCoreConfig instance
    """
    global _config

    if overrides or _config is None:
        _config = ContextCoreConfig(**overrides)

    return _config


def reset_config() -> None:
    """Reset the global configuration (for testing)."""
    global _config
    _config = None


# Convenience functions for common config access
def get_otlp_endpoint() -> str:
    """Get the configured OTLP endpoint."""
    return get_config().otlp_endpoint


def get_state_dir() -> str:
    """Get the configured state directory."""
    return get_config().state_dir


def get_log_level() -> str:
    """Get the configured log level."""
    return get_config().log_level


def is_kubernetes_available() -> bool:
    """Check if Kubernetes is available."""
    config = get_config()

    # Check explicit kubeconfig
    if config.kubeconfig:
        return os.path.exists(config.kubeconfig)

    # Check in-cluster
    if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount"):
        return True

    # Check KUBECONFIG env
    if os.environ.get("KUBECONFIG"):
        return os.path.exists(os.environ["KUBECONFIG"])

    # Check default kubeconfig
    return os.path.exists(os.path.expanduser("~/.kube/config"))
