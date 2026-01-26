"""
Size Estimation for Code Generation.

Provides heuristics-based estimation of code output size to enable
proactive truncation prevention in agent handoffs.

The estimator analyzes task descriptions and inputs to predict:
- Line count
- Token count
- Complexity level
- Confidence in the estimate

Example:
    estimator = SizeEstimator()
    estimate = estimator.estimate(
        task="Implement a REST API client with methods for CRUD operations",
        inputs={"context_files": ["models.py"], "required_exports": ["APIClient"]}
    )

    if estimate.lines > 150:
        # Trigger decomposition
        pass
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SizeEstimate:
    """Estimated size of generated output.

    Attributes:
        lines: Estimated number of lines
        tokens: Estimated token count
        complexity: Complexity level ("low", "medium", "high")
        confidence: Confidence in estimate (0.0 to 1.0)
        reasoning: Human-readable explanation of the estimate
    """
    lines: int
    tokens: int
    complexity: str
    confidence: float
    reasoning: str


class SizeEstimator:
    """
    Estimates code output size based on task description and inputs.

    Uses heuristics based on:
    - Task keywords and patterns
    - Number of required exports
    - Context file count
    - Historical patterns (if available)
    """

    # Lines per construct (conservative estimates)
    LINES_PER_CLASS = 40
    LINES_PER_METHOD = 12
    LINES_PER_FUNCTION = 15
    LINES_PER_DATACLASS = 15
    LINES_PER_ENUM = 10
    LINES_PER_IMPORT = 1
    LINES_PER_DOCSTRING = 5

    # Complexity multipliers
    COMPLEXITY_MULTIPLIERS = {
        "low": 0.8,
        "medium": 1.0,
        "high": 1.4,
    }

    # Tokens per line (rough average for Python)
    TOKENS_PER_LINE = 3

    # Keywords that indicate larger output
    HIGH_COMPLEXITY_KEYWORDS = [
        "comprehensive", "complete", "full", "entire", "all methods",
        "with tests", "including tests", "crud", "api", "rest api",
        "async", "concurrent", "parallel", "error handling",
        "logging", "metrics", "observability", "telemetry",
    ]

    MEDIUM_COMPLEXITY_KEYWORDS = [
        "implement", "create", "build", "add", "multiple",
        "methods", "functions", "class", "module", "service",
    ]

    LOW_COMPLEXITY_KEYWORDS = [
        "fix", "patch", "update", "modify", "simple", "basic",
        "single", "one", "small", "minor", "quick",
    ]

    # Patterns for detecting specific constructs
    CONSTRUCT_PATTERNS = [
        (r'\bclass\b', 'class'),
        (r'\bdef\b', 'function'),
        (r'\basync\s+def\b', 'async_function'),
        (r'\b@dataclass\b', 'dataclass'),
        (r'\bEnum\b', 'enum'),
        (r'\bprotocol\b', 'protocol'),
        (r'\binterface\b', 'interface'),
    ]

    def __init__(self):
        """Initialize the size estimator."""
        pass

    def estimate(self, task: str, inputs: dict) -> SizeEstimate:
        """
        Estimate the size of generated output.

        Args:
            task: Description of what to generate
            inputs: Additional inputs (context_files, required_exports, etc.)

        Returns:
            SizeEstimate with predicted size and confidence
        """
        task_lower = task.lower()

        # Detect complexity
        complexity = self._detect_complexity(task_lower)

        # Count expected constructs
        construct_count = self._count_expected_constructs(task_lower, inputs)

        # Calculate base line estimate
        base_lines = self._calculate_base_lines(construct_count, inputs)

        # Apply complexity multiplier
        multiplier = self.COMPLEXITY_MULTIPLIERS[complexity]
        estimated_lines = int(base_lines * multiplier)

        # Calculate tokens
        estimated_tokens = estimated_lines * self.TOKENS_PER_LINE

        # Calculate confidence
        confidence = self._calculate_confidence(task_lower, inputs, construct_count)

        # Build reasoning
        reasoning = self._build_reasoning(
            task, construct_count, complexity, base_lines, estimated_lines
        )

        return SizeEstimate(
            lines=estimated_lines,
            tokens=estimated_tokens,
            complexity=complexity,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _detect_complexity(self, task_lower: str) -> str:
        """Detect task complexity from keywords."""
        high_score = sum(1 for kw in self.HIGH_COMPLEXITY_KEYWORDS if kw in task_lower)
        medium_score = sum(1 for kw in self.MEDIUM_COMPLEXITY_KEYWORDS if kw in task_lower)
        low_score = sum(1 for kw in self.LOW_COMPLEXITY_KEYWORDS if kw in task_lower)

        if high_score >= 2 or (high_score >= 1 and medium_score >= 2):
            return "high"
        elif low_score >= 2 and high_score == 0:
            return "low"
        else:
            return "medium"

    def _count_expected_constructs(self, task_lower: str, inputs: dict) -> dict:
        """Count expected constructs based on task and inputs."""
        counts = {
            "classes": 0,
            "functions": 0,
            "methods": 0,
            "dataclasses": 0,
            "enums": 0,
            "imports": 5,  # Base imports
        }

        # Count from required exports
        required_exports = inputs.get("required_exports") or []
        for export in required_exports:
            # Heuristic: CamelCase = class, lowercase = function
            if export and export[0].isupper():
                counts["classes"] += 1
            else:
                counts["functions"] += 1

        # Count from task description
        if "class" in task_lower:
            counts["classes"] = max(counts["classes"], 1)
        if "dataclass" in task_lower:
            counts["dataclasses"] = max(counts["dataclasses"], 1)
        if "enum" in task_lower:
            counts["enums"] = max(counts["enums"], 1)

        # Count methods mentioned
        method_matches = re.findall(r'method[s]?\s*(?:for\s+)?(\w+)', task_lower)
        counts["methods"] += len(method_matches)

        # Count functions mentioned
        if "function" in task_lower or "functions" in task_lower:
            # Try to extract count
            func_count = re.search(r'(\d+)\s*function', task_lower)
            if func_count:
                counts["functions"] += int(func_count.group(1))
            else:
                counts["functions"] = max(counts["functions"], 1)

        # CRUD operations imply 4 methods
        if "crud" in task_lower:
            counts["methods"] += 4

        # API client implies multiple methods
        if "api" in task_lower and "client" in task_lower:
            counts["methods"] = max(counts["methods"], 5)

        # Context files add imports
        context_files = inputs.get("context_files") or []
        counts["imports"] += len(context_files)

        return counts

    def _calculate_base_lines(self, construct_count: dict, inputs: dict) -> int:
        """Calculate base line estimate from construct counts."""
        lines = 0

        # Add lines for each construct type
        lines += construct_count["classes"] * self.LINES_PER_CLASS
        lines += construct_count["functions"] * self.LINES_PER_FUNCTION
        lines += construct_count["methods"] * self.LINES_PER_METHOD
        lines += construct_count["dataclasses"] * self.LINES_PER_DATACLASS
        lines += construct_count["enums"] * self.LINES_PER_ENUM
        lines += construct_count["imports"] * self.LINES_PER_IMPORT

        # Add docstrings if required
        if inputs.get("must_have_docstring", True):
            total_constructs = (
                construct_count["classes"] +
                construct_count["functions"] +
                1  # Module docstring
            )
            lines += total_constructs * self.LINES_PER_DOCSTRING

        # Minimum estimate
        lines = max(lines, 20)

        return lines

    def _calculate_confidence(
        self,
        task_lower: str,
        inputs: dict,
        construct_count: dict,
    ) -> float:
        """Calculate confidence in the estimate."""
        confidence = 0.5  # Base confidence

        # More specific = higher confidence
        if inputs.get("required_exports"):
            confidence += 0.2

        if inputs.get("context_files"):
            confidence += 0.1

        # Construct detection adds confidence
        total_constructs = sum(construct_count.values()) - construct_count["imports"]
        if total_constructs > 0:
            confidence += min(0.15, total_constructs * 0.03)

        # Vague tasks reduce confidence
        vague_words = ["something", "stuff", "things", "etc", "various"]
        if any(word in task_lower for word in vague_words):
            confidence -= 0.15

        # Cap confidence
        return max(0.2, min(0.9, confidence))

    def _build_reasoning(
        self,
        task: str,
        construct_count: dict,
        complexity: str,
        base_lines: int,
        estimated_lines: int,
    ) -> str:
        """Build human-readable reasoning for the estimate."""
        parts = []

        # Summarize constructs
        constructs = []
        if construct_count["classes"] > 0:
            constructs.append(f"{construct_count['classes']} class(es)")
        if construct_count["functions"] > 0:
            constructs.append(f"{construct_count['functions']} function(s)")
        if construct_count["methods"] > 0:
            constructs.append(f"{construct_count['methods']} method(s)")
        if construct_count["dataclasses"] > 0:
            constructs.append(f"{construct_count['dataclasses']} dataclass(es)")
        if construct_count["enums"] > 0:
            constructs.append(f"{construct_count['enums']} enum(s)")

        if constructs:
            parts.append(f"Expected: {', '.join(constructs)}")

        parts.append(f"Complexity: {complexity}")
        parts.append(f"Base estimate: {base_lines} lines")

        if complexity != "medium":
            parts.append(f"After {complexity} complexity adjustment: {estimated_lines} lines")

        return "; ".join(parts)


def estimate_from_spec(spec: "CodeGenerationSpec") -> SizeEstimate:
    """
    Convenience function to estimate size from a CodeGenerationSpec.

    Args:
        spec: Code generation specification

    Returns:
        SizeEstimate
    """
    estimator = SizeEstimator()
    return estimator.estimate(
        task=spec.description,
        inputs={
            "target_file": spec.target_file,
            "context_files": spec.context_files,
            "required_exports": spec.required_exports,
            "required_imports": spec.required_imports,
            "must_have_docstring": spec.must_have_docstring,
        },
    )
