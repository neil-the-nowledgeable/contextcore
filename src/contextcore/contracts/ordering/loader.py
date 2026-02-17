"""
YAML contract loader with per-path caching for ordering contracts.

Loads causal ordering contract YAML files, validates them against the
Pydantic schema models, and caches the result per file path.

Follows the ``ContractLoader`` cache pattern from
``contracts/propagation/loader.py``.

Usage::

    from contextcore.contracts.ordering.loader import OrderingLoader

    loader = OrderingLoader()
    spec = loader.load(Path("pipeline-ordering.contract.yaml"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import yaml

from contextcore.contracts.ordering.schema import OrderingConstraintSpec

logger = logging.getLogger(__name__)


class OrderingLoader:
    """Loads and caches causal ordering contracts from YAML files."""

    _cache: ClassVar[dict[str, OrderingConstraintSpec]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the contract cache (useful in tests)."""
        cls._cache.clear()

    def load(self, path: Path) -> OrderingConstraintSpec:
        """Load a contract from a YAML file.

        Args:
            path: Path to the YAML contract file.

        Returns:
            Validated ``OrderingConstraintSpec`` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file contains invalid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        key = str(path.resolve())
        if key in self._cache:
            logger.debug("Ordering contract cache hit: %s", key)
            return self._cache[key]

        if not path.exists():
            raise FileNotFoundError(f"Contract file not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        spec = OrderingConstraintSpec.model_validate(raw)
        self._cache[key] = spec

        logger.debug(
            "Loaded ordering contract: pipeline=%s, dependencies=%d",
            spec.pipeline_id,
            len(spec.dependencies),
        )
        return spec

    def load_from_string(self, yaml_str: str) -> OrderingConstraintSpec:
        """Load a contract from a YAML string (convenience for testing).

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Validated ``OrderingConstraintSpec`` instance.
        """
        raw = yaml.safe_load(yaml_str)
        return OrderingConstraintSpec.model_validate(raw)
