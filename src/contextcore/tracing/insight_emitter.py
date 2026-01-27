# src/contextcore/tracing/insight_emitter.py
"""Insight emitter using OpenTelemetry spans with provider/model tracking."""

import os
from contextlib import contextmanager
from typing import Optional, Tuple, Any, Dict
from opentelemetry import trace

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
        service_name = (self._get_clean_env("OTEL_SERVICE_NAME", "") or "").lower()
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
