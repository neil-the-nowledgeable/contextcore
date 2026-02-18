"""
Generic base contract loader with per-path caching and YAML validation.

Provides ``BaseContractLoader[T]`` — the base class that L3-L7 contract
loaders inherit from.  Centralises:

- Per-path caching via class-level dict (each subclass gets its own)
- File existence checks
- YAML parsing with dict-type validation
- Pydantic ``model_validate`` dispatch

Subclasses set ``_model_class`` and optionally override ``_log_loaded()``
for domain-specific debug logging.

Usage::

    from contextcore.contracts._loader_base import BaseContractLoader
    from contextcore.contracts.semconv.schema import ConventionContract

    class ConventionLoader(BaseContractLoader[ConventionContract]):
        _model_class = ConventionContract

        def _log_loaded(self, contract: ConventionContract, key: str) -> None:
            self._logger.debug(
                "Loaded convention contract: namespace=%s",
                contract.namespace,
            )
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseContractLoader(Generic[T]):
    """Generic base for YAML contract loaders with per-path caching.

    Subclasses must set ``_model_class`` to the Pydantic model used
    for validation.  Override ``_log_loaded()`` for domain-specific
    debug messages after a successful load.
    """

    _model_class: type[T]  # Set by each subclass
    _cache: ClassVar[dict[str, BaseModel]] = {}
    _logger: ClassVar[logging.Logger]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Each subclass gets its own cache to avoid cross-domain collisions.
        cls._cache = {}
        cls._logger = logging.getLogger(cls.__module__)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the contract cache (useful in tests)."""
        cls._cache.clear()

    def load(self, path: Path) -> T:
        """Load a contract from a YAML file.

        Args:
            path: Path to the YAML contract file.

        Returns:
            Validated contract model instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            TypeError: If the YAML root is not a mapping.
            yaml.YAMLError: If the file contains invalid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        key = str(path.resolve())
        cached = self._cache.get(key)
        if cached is not None:
            self._logger.debug("%s cache hit: %s", type(self).__name__, key)
            return cached  # type: ignore[return-value]

        if not path.exists():
            raise FileNotFoundError(f"Contract file not found: {path}")

        with open(path) as fh:
            raw = yaml.safe_load(fh)

        if not isinstance(raw, dict):
            raise TypeError(
                f"Expected YAML mapping at root of {path}, "
                f"got {type(raw).__name__}"
            )

        contract = self._model_class.model_validate(raw)
        self._cache[key] = contract
        self._log_loaded(contract, key)
        return contract

    def load_from_string(self, yaml_str: str) -> T:
        """Load a contract from a YAML string (convenience for testing).

        Args:
            yaml_str: YAML content as a string.

        Returns:
            Validated contract model instance.

        Raises:
            TypeError: If the YAML root is not a mapping.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        raw = yaml.safe_load(yaml_str)
        if not isinstance(raw, dict):
            raise TypeError(
                f"Expected YAML mapping, got {type(raw).__name__}"
            )
        return self._model_class.model_validate(raw)

    def _log_loaded(self, contract: T, key: str) -> None:
        """Hook for subclass-specific debug logging after a load.

        Override to log domain-specific attributes (e.g. count of
        dependencies, capabilities, etc.).

        Args:
            contract: The loaded and validated contract.
            key: The resolved file path key.
        """
        self._logger.debug("Loaded %s from %s", type(self).__name__, key)
