"""
Prime Contractor Workflow - Continuous Integration Wrapper

The Prime Contractor wraps the Lead Contractor workflow to ensure:
1. Features are integrated immediately after development (not batched)
2. Integration checkpoints validate code before moving to next feature
3. Conflicts are detected and resolved before they compound
4. Regressions are prevented by keeping mainline always up-to-date

This prevents the "backlog integration nightmare" where multiple features
developed in isolation create merge conflicts and regressions when
integrated all at once.
"""

from .workflow import PrimeContractorWorkflow
from .checkpoint import IntegrationCheckpoint, CheckpointResult
from .feature_queue import FeatureQueue, FeatureSpec

__all__ = [
    "PrimeContractorWorkflow",
    "IntegrationCheckpoint",
    "CheckpointResult",
    "FeatureQueue",
    "FeatureSpec",
]
