"""
Task definitions for Lead Contractor workflows.

Phase 3: Strategic Features
- GRAPH_FEATURES: Knowledge Graph (4 Python features)
- LEARNING_FEATURES: Agent Learning Loop (4 Python features)
- VSCODE_FEATURES: VSCode Extension (8 TypeScript features)

Phase 4: A2A Protocol Alignment (standalone)
- NAMING_FEATURES: A2A-style naming conventions (4 Python features)
- STATE_FEATURES: State model enhancements (3 Python features)
- DISCOVERY_FEATURES: AgentCard & discovery (4 Python features)
- PARTS_FEATURES: Part model unification (4 Python features)
- A2A_ADAPTER_FEATURES: A2A protocol adapter (5 Python features)

Phase 4: Unified Protocol Alignment (combined OTel GenAI + A2A)
- FOUNDATION_FEATURES: Gap analysis, dual-emit layer (2 Python features)
- API_FEATURES: A2A-style API facades (4 Python features)
- CORE_OTEL_FEATURES: operation.name, conversation.id (2 Python features)
- EXTENDED_OTEL_FEATURES: provider/model, tool mapping (2 Python features)
- DOCS_FEATURES: Unified documentation update (1 feature)

Installation Tracking & Resume Plan
- INSTALL_TRACKING_FEATURES: Resumable installation system (6 Bash features)
"""

# Phase 3 features
from .graph import GRAPH_FEATURES
from .learning import LEARNING_FEATURES
from .vscode import VSCODE_FEATURES

# Phase 4 features (A2A standalone)
from .a2a_naming import NAMING_FEATURES
from .a2a_state import STATE_FEATURES
from .a2a_discovery import DISCOVERY_FEATURES
from .a2a_parts import PARTS_FEATURES
from .a2a_adapter import A2A_ADAPTER_FEATURES

# Phase 4 features (Unified: OTel GenAI + A2A)
from .unified_foundation import FOUNDATION_FEATURES
from .unified_api import API_FEATURES
from .unified_otel import CORE_OTEL_FEATURES, EXTENDED_OTEL_FEATURES
from .unified_docs import DOCS_FEATURES

# Installation Tracking & Resume Plan
from .install_tracking import INSTALL_TRACKING_FEATURES

# Dashboard & Persistence Architecture
from .dashboard_persistence import (
    DASHBOARD_PERSISTENCE_FEATURES,
    PHASES_1_3_FEATURES as DP_PHASES_1_3,
    PHASES_4_6_FEATURES as DP_PHASES_4_6,
    PHASES_7_9_FEATURES as DP_PHASES_7_9,
)

__all__ = [
    # Phase 3
    "GRAPH_FEATURES",
    "LEARNING_FEATURES",
    "VSCODE_FEATURES",
    # Phase 4 (A2A standalone)
    "NAMING_FEATURES",
    "STATE_FEATURES",
    "DISCOVERY_FEATURES",
    "PARTS_FEATURES",
    "A2A_ADAPTER_FEATURES",
    # Phase 4 (Unified)
    "FOUNDATION_FEATURES",
    "API_FEATURES",
    "CORE_OTEL_FEATURES",
    "EXTENDED_OTEL_FEATURES",
    "DOCS_FEATURES",
    # Installation Tracking
    "INSTALL_TRACKING_FEATURES",
    # Dashboard & Persistence
    "DASHBOARD_PERSISTENCE_FEATURES",
    "DP_PHASES_1_3",
    "DP_PHASES_4_6",
    "DP_PHASES_7_9",
]
