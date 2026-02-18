"""
YAML contract loader for capability propagation contracts.

Inherits from ``BaseContractLoader`` for caching and validation.

Usage::

    from contextcore.contracts.capability.loader import CapabilityLoader

    loader = CapabilityLoader()
    contract = loader.load(Path("artisan-pipeline.capability.yaml"))
"""

from __future__ import annotations

from contextcore.contracts._loader_base import BaseContractLoader
from contextcore.contracts.capability.schema import CapabilityContract


class CapabilityLoader(BaseContractLoader[CapabilityContract]):
    """Loads and caches capability propagation contracts from YAML files."""

    _model_class = CapabilityContract

    def _log_loaded(self, contract: CapabilityContract, key: str) -> None:
        self._logger.debug(
            "Loaded capability contract: pipeline=%s, capabilities=%d, "
            "phases=%d, chains=%d",
            contract.pipeline_id,
            len(contract.capabilities),
            len(contract.phases),
            len(contract.chains),
        )
