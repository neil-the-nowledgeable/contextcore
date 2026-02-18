"""
YAML contract loader for semantic convention contracts.

Inherits from ``BaseContractLoader`` for caching and validation.

Usage::

    from contextcore.contracts.semconv.loader import ConventionLoader

    loader = ConventionLoader()
    contract = loader.load(Path("otel-semconv.contract.yaml"))
"""

from __future__ import annotations

from contextcore.contracts._loader_base import BaseContractLoader
from contextcore.contracts.semconv.schema import ConventionContract


class ConventionLoader(BaseContractLoader[ConventionContract]):
    """Loads and caches semantic convention contracts from YAML files."""

    _model_class = ConventionContract

    def _log_loaded(self, contract: ConventionContract, key: str) -> None:
        self._logger.debug(
            "Loaded convention contract: namespace=%s, attributes=%d, enums=%d",
            contract.namespace,
            len(contract.attributes),
            len(contract.enums),
        )
