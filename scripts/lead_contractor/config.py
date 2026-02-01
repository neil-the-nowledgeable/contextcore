"""
Shared configuration for Lead Contractor workflows.
"""

import os
import sys
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "generated" / "phase3"
STARTD8_SDK_PATH = Path(
    os.environ.get("STARTD8_SDK_PATH", PROJECT_ROOT.parent / "startd8-sdk" / "src")
)

# Add startd8 SDK to path
if STARTD8_SDK_PATH.exists():
    sys.path.insert(0, str(STARTD8_SDK_PATH))

# Agent configuration
LEAD_AGENT = "anthropic:claude-sonnet-4-20250514"
DRAFTER_AGENT = "openai:gpt-4o-mini"
MAX_ITERATIONS = 3
PASS_THRESHOLD = 80

# Language contexts
PYTHON_CONTEXT = {
    "language": "Python 3.9+",
    "framework": "Click CLI, Pydantic v2, OpenTelemetry SDK",
    "project": "ContextCore",
    "style": "PEP 8, type hints, docstrings, dataclasses"
}

TYPESCRIPT_CONTEXT = {
    "language": "TypeScript 5.0+",
    "framework": "VSCode Extension API",
    "project": "ContextCore VSCode Extension",
    "style": "ESLint, strict TypeScript, JSDoc comments"
}

# Integration instructions
PYTHON_INTEGRATION = """
Finalize the code for production use:
1. Ensure all imports are at the top
2. Add proper __all__ export list
3. Verify type hints are complete
4. Add inline comments for complex logic
5. Ensure the code is self-contained and can be dropped into the project
6. Use only standard library imports unless specified otherwise
"""

TYPESCRIPT_INTEGRATION = """
Finalize the code for production use:
1. Ensure all imports are at the top
2. Export all public interfaces and classes
3. Use proper TypeScript types (no 'any')
4. Add JSDoc comments for public APIs
5. Follow VSCode extension best practices
6. Handle errors gracefully with try/catch
7. Implement Disposable pattern for cleanup
"""
