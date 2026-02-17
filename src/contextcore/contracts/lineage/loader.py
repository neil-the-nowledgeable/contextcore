"""
YAML contract loader with per-path caching for data lineage contracts.

Follows the ``ContractLoader`` pattern from ``propagation/loader.py``.

Usage::

    from contextcore.contracts.lineage.loader import LineageLoader

    loader = LineageLoader()
    contract = loader.load(Path("pipeline-lineage.contract.yaml"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import yaml

from contextcore.contracts.lineage.schema import LineageContract

logger = logging.getLogger(__name__)


class LineageLoader:
    """Loads and caches data lineage contracts from YAML files."""

    _cache: ClassVar[dict[str, LineageContract]] = {}

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the contract cache (useful in tests)."""
        cls._cache.clear()

    def load(self, path: Path) -> LineageContract:
        """Load a contract from a YAML file.

        Args:
            path: Path to the YAML contract file.

        Returns:
            Validated ``LineageContract`` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            yaml.YAMLError: If the file contains invalid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        key = str(path.resolve())
        if key in self._cache:
            logger.debug("Lineage contract cache hit: %s", key)
            return self._cache[key]

        if not path.exists():
            raise FileNotFoundError(f"Contract file not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        contract = LineageContract.model_validate(raw)
        self._cache[key] = contract

        logger.debug(
            "Loaded lineage contract: pipeline=%s, chains=%d",
            contract.pipeline_id,
            len(contract.chains),
        )
        return contract

    def load_from_string(self, yaml_str: str) -> LineageContract:
        """Load a contract from a YAML string (convenience for testing).

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Validated ``LineageContract`` instance.
        """
        raw = yaml.safe_load(yaml_str)
        return LineageContract.model_validate(raw)
