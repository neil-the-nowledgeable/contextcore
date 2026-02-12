"""
Timeout and retry constants for ContextCore.

Centralizes timeout values to ensure consistency across the codebase
and make tuning easier.
"""

from __future__ import annotations

# =============================================================================
# OTel Provider Timeouts
# =============================================================================

# Timeout for force_flush operations on TracerProvider/MeterProvider
OTEL_FLUSH_TIMEOUT_MS = 5000

# Timeout for checking if OTLP endpoint is reachable
OTEL_ENDPOINT_CHECK_TIMEOUT_S = 2.0

# Default OTLP gRPC port
OTEL_DEFAULT_GRPC_PORT = 4317

# Default OTLP HTTP/protobuf port
OTEL_DEFAULT_HTTP_PORT = 4318

# =============================================================================
# HTTP Client Timeouts
# =============================================================================

# Default timeout for HTTP requests (Tempo, Grafana, etc.)
HTTP_CLIENT_TIMEOUT_S = 30.0

# Shorter timeout for health/readiness checks
HTTP_HEALTH_CHECK_TIMEOUT_S = 5.0

# Timeout for individual trace fetches (less critical, can fail faster)
HTTP_TRACE_FETCH_TIMEOUT_S = 10.0

# =============================================================================
# Kubernetes API Timeouts
# =============================================================================

# Connect timeout for K8s API calls
K8S_API_CONNECT_TIMEOUT_S = 3

# Read timeout for K8s API calls
K8S_API_READ_TIMEOUT_S = 5

# =============================================================================
# Handoff Timeouts
# =============================================================================

# Default timeout for handoff operations
HANDOFF_DEFAULT_TIMEOUT_MS = 300000  # 5 minutes

# Default poll interval for handoff receivers
HANDOFF_POLL_INTERVAL_S = 1.0

# =============================================================================
# Subprocess Timeouts
# =============================================================================

# Default timeout for kubectl and similar commands
SUBPROCESS_DEFAULT_TIMEOUT_S = 30

# =============================================================================
# Retry Configuration
# =============================================================================

# Default number of retries for transient failures
DEFAULT_MAX_RETRIES = 3

# Initial delay between retries
DEFAULT_RETRY_DELAY_S = 1.0

# Exponential backoff multiplier
DEFAULT_RETRY_BACKOFF = 2.0

# HTTP status codes that should trigger a retry
RETRYABLE_HTTP_STATUS_CODES = frozenset({502, 503, 504, 429})

# =============================================================================
# Export Retry Configuration
# =============================================================================

# Maximum retry attempts before moving to dead-letter
EXPORT_RETRY_MAX_ATTEMPTS = 3

# Maximum pending retry files before dropping new failures (prevents disk exhaustion)
EXPORT_RETRY_MAX_FILES = 100

# Number of pending retry files to drain per successful export
EXPORT_RETRY_DRAIN_BATCH = 3

# =============================================================================
# OTel Shutdown Configuration
# =============================================================================

# Timeout for TracerProvider shutdown (atexit handler)
OTEL_SHUTDOWN_TIMEOUT_MS = 10000

# =============================================================================
# Insight Cache Configuration
# =============================================================================

# Time-to-live for cached insight query results (seconds)
INSIGHT_CACHE_TTL_S = 300.0
