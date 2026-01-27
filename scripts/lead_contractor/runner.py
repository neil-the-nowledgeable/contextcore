"""
Workflow runner utilities for Lead Contractor.
"""

import json
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from opentelemetry import trace

from .config import (
    LEAD_AGENT,
    DRAFTER_AGENT,
    MAX_ITERATIONS,
    PASS_THRESHOLD,
    OUTPUT_DIR,
    PYTHON_CONTEXT,
    TYPESCRIPT_CONTEXT,
    PYTHON_INTEGRATION,
    TYPESCRIPT_INTEGRATION,
)


@dataclass
class Feature:
    """A feature to be implemented by the Lead Contractor workflow."""
    task: str
    name: str
    is_typescript: bool = False
    output_subdir: Optional[str] = None

    @property
    def context(self) -> Dict[str, str]:
        return TYPESCRIPT_CONTEXT if self.is_typescript else PYTHON_CONTEXT

    @property
    def integration_instructions(self) -> str:
        return TYPESCRIPT_INTEGRATION if self.is_typescript else PYTHON_INTEGRATION

    @property
    def file_extension(self) -> str:
        return ".ts" if self.is_typescript else ".py"


# OpenTelemetry tracer for cost tracking (BLC-009)
tracer = trace.get_tracer("contextcore.lead_contractor")


@dataclass
class WorkflowResult:
    """Result from a Lead Contractor workflow run."""
    feature_name: str
    success: bool
    implementation: str
    summary: Dict[str, Any]
    error: Optional[str]
    total_cost: float
    iterations: int
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


def run_workflow(feature: Feature, verbose: bool = True) -> WorkflowResult:
    """
    Run the Lead Contractor workflow for a single feature.

    Args:
        feature: The feature to implement
        verbose: Whether to print progress

    Returns:
        WorkflowResult with implementation and metrics
    """
    try:
        from startd8.workflows.builtin.lead_contractor_workflow import LeadContractorWorkflow
    except ImportError:
        print("Error: startd8 SDK not found. Please ensure it's installed.")
        print("Install via: pip install startd8")
        print("Or set $STARTD8_SDK_ROOT and add $STARTD8_SDK_ROOT/src to PYTHONPATH")
        return WorkflowResult(
            feature_name=feature.name,
            success=False,
            implementation="",
            summary={},
            error="startd8 SDK not found",
            total_cost=0,
            iterations=0,
        )

    if verbose:
        print(f"\n{'='*60}")
        print(f"Running Lead Contractor: {feature.name}")
        print(f"Language: {'TypeScript' if feature.is_typescript else 'Python'}")
        print(f"{'='*60}\n")

    # Wrap execution in OpenTelemetry span for cost tracking (BLC-009)
    with tracer.start_as_current_span("lead_contractor.code_generation") as span:
        span.set_attribute("gen_ai.operation.name", "code_generation")
        span.set_attribute("contextcore.feature.name", feature.name)
        span.set_attribute("contextcore.feature.language", "typescript" if feature.is_typescript else "python")

        workflow = LeadContractorWorkflow()

        config = {
            "task_description": feature.task,
            "context": feature.context,
            "lead_agent": LEAD_AGENT,
            "drafter_agent": DRAFTER_AGENT,
            "max_iterations": MAX_ITERATIONS,
            "pass_threshold": PASS_THRESHOLD,
            "integration_instructions": feature.integration_instructions,
        }

        result = workflow.run(config=config)

        # Extract metrics from result
        total_cost = result.metrics.total_cost if result.metrics else 0
        iterations = result.metadata.get("total_iterations", 0)

        # Extract token counts if available from metrics
        input_tokens = 0
        output_tokens = 0
        model = ""
        if result.metrics:
            input_tokens = getattr(result.metrics, "input_tokens", 0) or 0
            output_tokens = getattr(result.metrics, "output_tokens", 0) or 0
            model = getattr(result.metrics, "model", "") or LEAD_AGENT

        # Emit cost tracking span attributes (BLC-009)
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        span.set_attribute("gen_ai.request.model", model or LEAD_AGENT)
        span.set_attribute("contextcore.cost.usd", total_cost)
        span.set_attribute("contextcore.iterations", iterations)
        span.set_attribute("contextcore.success", result.success)

        if result.error:
            span.set_attribute("error.message", result.error)

        return WorkflowResult(
            feature_name=feature.name,
            success=result.success,
            implementation=result.output.get("final_implementation", ""),
            summary=result.output.get("summary", {}),
            error=result.error,
            total_cost=total_cost,
            iterations=iterations,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model or LEAD_AGENT,
        )


def extract_code(text: str, language: str = "python") -> str:
    """Extract code from markdown code blocks."""
    # Try language-specific blocks
    for lang in ([language] if language != "typescript" else ["typescript", "ts"]):
        pattern = rf'```{lang}\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return "\n\n".join(matches)

    # Try generic blocks
    pattern = r'```\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return "\n\n".join(matches)

    return text


def get_result_file_path(feature: Feature, output_dir: Optional[Path] = None) -> Path:
    """Get the path to the result JSON file for a feature."""
    base_dir = output_dir or OUTPUT_DIR
    if feature.output_subdir:
        base_dir = base_dir / feature.output_subdir
    slug = feature.name.replace(" ", "_").lower()
    return base_dir / f"{slug}_result.json"


def load_existing_result(feature: Feature, output_dir: Optional[Path] = None) -> Optional[WorkflowResult]:
    """
    Load an existing successful result for a feature if it exists.
    
    Returns:
        WorkflowResult if found and successful, None otherwise
    """
    result_file = get_result_file_path(feature, output_dir)
    
    if not result_file.exists():
        return None
    
    try:
        with open(result_file, "r") as f:
            data = json.load(f)
        
        # Only return if it was successful
        if data.get("success", False):
            return WorkflowResult(
                feature_name=data.get("feature", feature.name),
                success=True,
                implementation="",  # Don't load code, just metadata
                summary=data.get("summary", {}),
                error=data.get("error"),
                total_cost=data.get("total_cost", 0),
                iterations=data.get("iterations", 0),
                input_tokens=data.get("input_tokens", 0),
                output_tokens=data.get("output_tokens", 0),
                model=data.get("model", ""),
            )
    except (json.JSONDecodeError, KeyError, IOError):
        # If file is corrupted or missing fields, treat as not found
        return None
    
    return None


def save_result(result: WorkflowResult, feature: Feature, output_dir: Optional[Path] = None):
    """Save workflow result to files."""
    base_dir = output_dir or OUTPUT_DIR
    if feature.output_subdir:
        base_dir = base_dir / feature.output_subdir
    base_dir.mkdir(parents=True, exist_ok=True)

    slug = feature.name.replace(" ", "_").lower()

    # Save metadata as JSON (including BLC-009 cost tracking fields)
    meta_file = base_dir / f"{slug}_result.json"
    with open(meta_file, "w") as f:
        json.dump({
            "feature": result.feature_name,
            "success": result.success,
            "summary": result.summary,
            "error": result.error,
            "total_cost": result.total_cost,
            "iterations": result.iterations,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "model": result.model,
        }, f, indent=2)

    # Save implementation code
    lang = "typescript" if feature.is_typescript else "python"
    code = extract_code(result.implementation, lang)
    code_file = base_dir / f"{slug}_code{feature.file_extension}"
    with open(code_file, "w") as f:
        f.write(code)

    print(f"Saved: {meta_file}")
    print(f"Saved: {code_file}")

    return meta_file, code_file


def run_features(
    features: List[Feature],
    output_dir: Optional[Path] = None,
    verbose: bool = True,
    stop_on_error: bool = False,
    skip_existing: bool = True,
    force: bool = False,
) -> List[WorkflowResult]:
    """
    Run Lead Contractor workflow for multiple features.

    Args:
        features: List of features to implement
        output_dir: Output directory for generated code
        verbose: Whether to print progress
        stop_on_error: Whether to stop on first error
        skip_existing: Skip features that already have successful results
        force: Force regeneration even if successful result exists (overrides skip_existing)

    Returns:
        List of WorkflowResults
    """
    results = []
    skipped_count = 0

    for i, feature in enumerate(features, 1):
        if verbose:
            print(f"\n[{i}/{len(features)}] Processing {feature.name}")

        # Check for existing successful result
        if skip_existing and not force:
            existing = load_existing_result(feature, output_dir)
            if existing:
                if verbose:
                    print(f"  ✓ Skipping (already completed successfully)")
                    print(f"    Previous cost: ${existing.total_cost:.4f}, Iterations: {existing.iterations}")
                results.append(existing)
                skipped_count += 1
                continue

        try:
            result = run_workflow(feature, verbose)
            results.append(result)
            save_result(result, feature, output_dir)

            if verbose:
                print(f"\nResult: {'SUCCESS' if result.success else 'FAILED'}")
                print(f"  Iterations: {result.iterations}")
                print(f"  Cost: ${result.total_cost:.4f}")
                if result.error:
                    print(f"  Error: {result.error}")

            if not result.success and stop_on_error:
                print("\nStopping due to error (--stop-on-error)")
                break

        except Exception as e:
            print(f"\nException running {feature.name}: {e}")
            traceback.print_exc()
            if stop_on_error:
                break

    # Print summary
    if verbose and len(results) > 1:
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Total features: {len(features)}")
        print(f"  Skipped (already completed): {skipped_count}")
        print(f"  Run: {len(results) - skipped_count}")
        print(f"  Successful: {sum(1 for r in results if r.success)}")
        print(f"  Failed: {sum(1 for r in results if not r.success)}")
        # Only count cost for newly run features (not skipped ones)
        new_cost = sum(r.total_cost for r in results if r.iterations > 0)
        print(f"  Cost (this run): ${new_cost:.4f}")

    return results
