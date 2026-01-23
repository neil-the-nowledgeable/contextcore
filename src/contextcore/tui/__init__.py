"""
ContextCore Terminal User Interface.

This module provides an interactive TUI for ContextCore installation,
configuration, and monitoring using the Textual framework.

Usage:
    from contextcore.tui import ContextCoreTUI

    app = ContextCoreTUI()
    app.run()

CLI:
    contextcore tui launch
    contextcore tui install
    contextcore tui status

Dependencies:
    - textual>=0.47.0
    - click>=8.0.0
    - aiohttp>=3.9.0
"""

__version__ = "0.1.0"

try:
    from .app import ContextCoreTUI, get_env_config

    __all__ = [
        "ContextCoreTUI",
        "get_env_config",
    ]
except ImportError:
    # Graceful fallback when Textual not installed
    import warnings
    warnings.warn(
        "TUI components not available. Install with: pip install 'contextcore[tui]'",
        ImportWarning,
        stacklevel=2
    )
    __all__ = []
