"""
Storage abstraction layer for ContextCore.

Provides pluggable storage backends for:
- Handoff queue management
- Agent session tracking
- Insight storage
- State persistence

This allows ContextCore to work in different environments:
- Kubernetes (using CRDs)
- Local development (using filesystem)
- Distributed systems (using Redis)

Example:
    from contextcore.storage import get_storage, StorageType

    # Auto-detect storage backend
    storage = get_storage()

    # Explicitly use file storage for local dev
    storage = get_storage(StorageType.FILE)

    # Use storage for handoffs
    storage.save_handoff(handoff)
    storage.get_handoff(handoff_id)
"""

from contextcore.storage.base import (
    StorageBackend,
    StorageType,
    get_storage,
)
from contextcore.storage.file import FileStorage
from contextcore.storage.kubernetes import KubernetesStorage

__all__ = [
    "StorageBackend",
    "StorageType",
    "get_storage",
    "FileStorage",
    "KubernetesStorage",
]
