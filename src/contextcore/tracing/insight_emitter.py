# src/contextcore/tracing/insight_emitter.py
import os
from contextlib import contextmanager
from typing import Optional, Tuple, Any, Dict
from opentelemetry import trace
from opentelemetry.trace import Span
__all__ = ['InsightEmitter', 'InsightsAPI', 'insight', 'emit']


__all__ = ['InsightEmitter']

class InsightEmitter:
    """Emits insights as OpenTelemetry spans with provider and model tracking."""
    
    def emit(
        self,
        insight_type: str,
        summary: str,
        confidence: float,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """
        Emit an insight span with optional provider and model tracking.
        
        Args:
            insight_type: Type of insight being emitted
            summary: Human-readable summary of the insight
            confidence: Confidence score (0.0 to 1.0)
            provider: LLM provider name (e.g., "anthropic", "openai")
            model: LLM model name (e.g., "claude-opus-4-5-20251101")
            **kwargs: Additional span attributes
        """
        # Auto-detect provider/model if not explicitly provided
        detected_provider, detected_model = self._detect_provider_model()
        final_provider = provider or detected_provider
        final_model = model or detected_model
        
        # Create span with dual-emit architecture
        with self._create_insight_span(insight_type, summary, confidence, 
                                     final_provider, final_model, **kwargs) as span:
            # Core insight emission logic
            span.add_event("insight.generated", {
                "insight.summary": summary,
                "insight.confidence": confidence
            })

    def _detect_provider_model(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Auto-detect provider and model from environment variables and service name.
        
        Returns:
            Tuple of (provider, model) or (None, None) if detection fails
        """
        # Primary detection from explicit environment variables
        provider = self._get_clean_env("LLM_PROVIDER")
        model = self._get_clean_env("LLM_MODEL")
        
        # If both are set, return immediately
        if provider and model:
            return provider, model
            
        # Fallback to service name detection
        service_name = self._get_clean_env("OTEL_SERVICE_NAME", "").lower()
        if service_name and not provider:
            if "claude" in service_name:
                provider = "anthropic"
                # Extract model suffix after claude
                if "claude-" in service_name:
                    model_part = service_name.split("claude-", 1)[1]
                    if model_part:
                        model = f"claude-{model_part}"
            elif "gpt" in service_name:
                provider = "openai"
                # Extract model name containing gpt
                if "gpt-" in service_name:
                    model_part = service_name.split("gpt-", 1)[1].split("-")[0]
                    if model_part:
                        model = f"gpt-{model_part}"
            elif "gemini" in service_name:
                provider = "google"
                if "gemini-" in service_name:
                    model_part = service_name.split("gemini-", 1)[1]
                    if model_part:
                        model = f"gemini-{model_part}"
        
        return provider, model

    def _get_clean_env(self, key: str, default: str = "") -> Optional[str]:
        """Get environment variable with whitespace cleaning."""
        value = os.environ.get(key, default).strip()
        return value if value else None

    @contextmanager
    def _create_insight_span(
        self,
        insight_type: str,
        summary: str,
        confidence: float,
        provider: Optional[str],
        model: Optional[str],
        **kwargs: Any
    ):
        """
        Create OpenTelemetry span with insight attributes using dual-emit pattern.
        
        This is the dual-emit layer that adds semantic convention attributes.
        """
        tracer = trace.get_tracer("contextcore.insights")
        
        # Build span attributes
        attributes: Dict[str, Any] = {
            "insight.type": insight_type,
            "insight.summary": summary,
            "insight.confidence": confidence,
        }
        
        # Add provider/model attributes using semantic conventions
        if provider:
            attributes["gen_ai.provider.name"] = provider
        if model:
            attributes["gen_ai.request.model"] = model
            
        # Add any additional attributes
        attributes.update(kwargs)
        
        # Create and yield span
        with tracer.start_as_current_span(
            f"insight.{insight_type}",
            attributes=attributes
        ) as span:
            yield span


# src/contextcore/api/insights.py
from typing import Optional, Any
from .tracing.insight_emitter import InsightEmitter

__all__ = ['InsightsAPI']

class InsightsAPI:
    """API layer for insight operations."""
    
    def __init__(self):
        self._emitter = InsightEmitter()
    
    def emit_insight(
        self,
        insight_type: str,
        summary: str,
        confidence: float,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """
        Emit an insight through the API layer.
        
        Args:
            insight_type: Type of insight
            summary: Summary description
            confidence: Confidence score (0.0-1.0)
            provider: Optional LLM provider name
            model: Optional LLM model name
            **kwargs: Additional attributes
        """
        self._emitter.emit(
            insight_type=insight_type,
            summary=summary,
            confidence=confidence,
            provider=provider,
            model=model,
            **kwargs
        )


# src/contextcore/cli/insight.py
import click
from typing import Optional
from ..api.insights import InsightsAPI

@click.group()
def insight():
    """Insight management commands."""
    pass

@insight.command()
@click.option('--type', 'insight_type', required=True, 
              help='Type of insight (e.g., decision, analysis)')
@click.option('--summary', required=True,
              help='Human-readable summary of the insight')
@click.option('--confidence', type=float, required=True,
              help='Confidence score between 0.0 and 1.0')
@click.option('--provider', 
              help='LLM provider name (e.g., anthropic, openai)')
@click.option('--model',
              help='LLM model name (e.g., claude-opus-4-5-20251101)')
def emit(
    insight_type: str,
    summary: str, 
    confidence: float,
    provider: Optional[str],
    model: Optional[str]
) -> None:
    """
    Emit an insight with optional provider and model tracking.
    
    Examples:
        contextcore insight emit --type decision --summary "Selected option A" --confidence 0.85
        contextcore insight emit --type decision --summary "Selected option A" --confidence 0.85 --provider anthropic --model claude-opus-4-5
    """
    # Validate confidence range
    if not 0.0 <= confidence <= 1.0:
        click.echo("Error: Confidence must be between 0.0 and 1.0", err=True)
        raise click.Abort()
    
    api = InsightsAPI()
    try:
        api.emit_insight(
            insight_type=insight_type,
            summary=summary,
            confidence=confidence,
            provider=provider,
            model=model
        )
        click.echo(f"✓ Insight '{insight_type}' emitted successfully")
    except Exception as e:
        click.echo(f"Error emitting insight: {e}", err=True)
        raise click.Abort()


# docs/semantic_conventions.md
"""
# Semantic Conventions for Insight Tracking

## Overview
ContextCore uses OpenTelemetry semantic conventions to track LLM provider and model 
information in insight spans, enabling detailed analysis and filtering.

## Attributes

### Required Insight Attributes
- `insight.type`: The type of insight (e.g., "decision", "analysis", "recommendation")
- `insight.summary`: Human-readable summary of the insight
- `insight.confidence`: Confidence score as a float between 0.0 and 1.0

### Optional LLM Tracking Attributes  
- `gen_ai.provider.name`: LLM provider name following standard conventions
  - "anthropic" for Claude models
  - "openai" for GPT models  
  - "google" for Gemini models
- `gen_ai.request.model`: Specific model identifier
  - "claude-opus-4-5-20251101"
  - "gpt-4-turbo"
  - "gemini-pro"

## Auto-Detection

The system automatically detects provider and model from:

1. **Environment Variables** (preferred):
   

# Explicit provider/model
api.emit_insight("decision", "Selected option A", 0.85, 
                provider="anthropic", model="claude-opus-4-5")

# Auto-detection
api.emit_insight("decision", "Selected option A", 0.85)
