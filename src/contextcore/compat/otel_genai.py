"""OpenTelemetry GenAI semantic conventions compatibility layer."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, NamedTuple
from unittest.mock import Mock
import click
import json
import os
import re
import unittest
import uuid
import warnings

__all__ = ['ATTRIBUTE_MAPPINGS', 'transform']
ATTRIBUTE_MAPPINGS = {
    "agent.session_id": "gen_ai.conversation.id"
}
__all__ = ['InsightRecord', 'InsightEmitter', 'InsightQuerier']
__all__ = ['InsightsAPI']
__all__ = ['insight_group']
__all__ = ['ATTRIBUTE_MAPPINGS', 'TOOL_ATTRIBUTES', 'DualEmitLayer']
ATTRIBUTE_MAPPINGS: Dict[str, str] = {
    "context.id": "gen_ai.request.id",
    "context.model": "gen_ai.request.model",
    "handoff.capability_id": "gen_ai.tool.name",
    "handoff.inputs": "gen_ai.tool.call.arguments", 
    "handoff.id": "gen_ai.tool.call.id",
}
TOOL_ATTRIBUTES: Dict[str, str] = {
    "gen_ai.tool.type": "agent_handoff",
}

"""
Dual-emit compatibility layer for ContextCore attribute emission.
This module allows ContextCore to emit both legacy (agent.*, insight.*, handoff.*)
and new (gen_ai.*) span attributes during the migration period.
"""

ATTRIBUTE_MAPPINGS = {
    "agent.id": "gen_ai.agent.id",
    "agent.type": "gen_ai.agent.type",
    "agent.session_id": "gen_ai.conversation.id",
    "handoff.capability_id": "gen_ai.tool.name",
    "handoff.inputs": "gen_ai.tool.call.arguments",
    "insight.type": "gen_ai.insight.type",
    "insight.value": "gen_ai.insight.value",
    "insight.confidence": "gen_ai.insight.confidence",
}

class AttributeInfo:
    """Represents a semantic attribute with its properties."""
    name: str
    description: str
    type: str
    required: bool
    example: str = ""


class DualEmitAttributes:
    """
    Handler for dual-emit attribute transformation based on emission mode.
    
    This class transforms span attributes according to the configured emission mode:
    - LEGACY: Only emit original attributes
    - DUAL: Emit both original and gen_ai.* attributes  
    - OTEL: Only emit gen_ai.* attributes (with warnings for legacy usage)
    """
    
    def __init__(self, mode: Optional[EmitMode] = None):
        """
        Initialize the dual-emit attributes handler.
        
        Args:
            mode: Override the emission mode. If None, uses get_emit_mode().
        """
        self.mode = mode or get_emit_mode()
        self._warned_attributes: Set[str] = set()  # Track warned attributes
    
    def transform(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform attributes based on emit mode.
        
        Args:
            attributes: Dictionary of span attributes to transform.
            
        Returns:
            Dict[str, Any]: Transformed attributes according to emission mode.
            
        Raises:
            TypeError: If attributes is not a dictionary.
            
        Examples:
            >>> emitter = DualEmitAttributes(EmitMode.DUAL)
            >>> attrs = {"agent.id": "test-agent", "custom.attr": "value"}
            >>> result = emitter.transform(attrs)
            >>> "agent.id" in result and "gen_ai.agent.id" in result
            True
        """
        if not isinstance(attributes, dict):
            raise TypeError("Attributes must be a dictionary")
        
        if self.mode == EmitMode.LEGACY:
            return self._legacy_mode(attributes)
        elif self.mode == EmitMode.DUAL:
            return self._dual_mode(attributes)
        else:  # EmitMode.OTEL
            return self._otel_mode(attributes)
    
    def _legacy_mode(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Return attributes unchanged for legacy mode."""
        return attributes.copy()
    
    def _dual_mode(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Return both legacy and gen_ai attributes for dual mode."""
        result = attributes.copy()
        
        # Add gen_ai equivalents for mapped legacy attributes
        for legacy_key, value in attributes.items():
            if legacy_key in ATTRIBUTE_MAPPINGS:
                gen_ai_key = ATTRIBUTE_MAPPINGS[legacy_key]
                result[gen_ai_key] = value
        
        return result
    
    def _otel_mode(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Convert legacy attributes to gen_ai equivalents for otel mode."""
        result = {}
        
        for key, value in attributes.items():
            if key in ATTRIBUTE_MAPPINGS:
                # Emit deprecation warning (once per attribute)
                if key not in self._warned_attributes:
                    warn_legacy_attribute(key)
                    self._warned_attributes.add(key)
                # Use gen_ai equivalent
                result[ATTRIBUTE_MAPPINGS[key]] = value
            else:
                # Pass through non-legacy attributes unchanged
                result[key] = value
        
        return result



class DualEmitLayer:
    """
    Transforms attributes to include both legacy and OpenTelemetry gen_ai conventions.
    Preserves original attributes while adding mapped equivalents.
    """
    
    def transform(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform attributes using dual-emit pattern.
        
        Args:
            attributes: Original attribute dictionary
            
        Returns:
            Dictionary containing both original and mapped attributes
        """
        # Start with original attributes (legacy support)
        result = attributes.copy()
        
        # Add mapped attributes for OTel compatibility
        for original_key, value in attributes.items():
            if original_key in ATTRIBUTE_MAPPINGS:
                mapped_key = ATTRIBUTE_MAPPINGS[original_key]
                result[mapped_key] = value
        
        return result


# File: contextcore/managers/handoff.py



class EmitMode(str, Enum):
    """Emission mode for span attributes."""
    LEGACY = "legacy"  # Only old attributes
    DUAL = "dual"      # Both old and new
    OTEL = "otel"      # Only new gen_ai.* attributes


# Cache for emission mode to avoid repeated environment variable lookups
_cached_mode: Optional[EmitMode] = None

class GapAnalysisGenerator:
    """Generates gap analysis between ContextCore and OTel GenAI conventions."""
    
    # OTel GenAI attributes based on specification
    OTEL_GENAI_ATTRIBUTES = {
        'gen_ai.system': 'The name of the GenAI system',
        'gen_ai.request.model': 'The name of the model being used',
        'gen_ai.request.max_tokens': 'Maximum number of tokens the model can return',
        'gen_ai.request.temperature': 'The temperature setting for the model',
        'gen_ai.request.top_p': 'The top_p sampling parameter',
        'gen_ai.response.id': 'The unique identifier for the AI response',
        'gen_ai.response.model': 'The name of the model that generated the response',
        'gen_ai.response.finish_reasons': 'Array of reasons the model stopped generating tokens',
        'gen_ai.usage.input_tokens': 'The number of tokens in the prompt',
        'gen_ai.usage.output_tokens': 'The number of tokens in the generated response',
        'gen_ai.token.type': 'The type of token being recorded',
        'gen_ai.prompt': 'The full prompt sent to the model',
        'gen_ai.completion': 'The full response received from the model',
    }

    def __init__(self):
        """Initialize the gap analysis generator."""
        self.contextcore_attributes: Dict[str, List[AttributeInfo]] = {}
        
    def _read_file(self, file_path: str) -> str:
        """Read file content safely."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except FileNotFoundError:
            print(f"Warning: File not found: {file_path}")
            return ""
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return ""

    def _extract_attributes_from_markdown(self, content: str, namespace: str) -> List[AttributeInfo]:
        """Extract attribute definitions from markdown content."""
        attributes = []
        
        # Pattern to match markdown tables with attribute definitions
        # Looks for tables with columns: Attribute | Type | Required | Description
        table_pattern = r'\|[^\|]*Attribute[^\|]*\|[^\n]*\n\|[-\s\|]*\n((?:\|[^\n]*\n)*)'
        
        table_matches = re.finditer(table_pattern, content, re.IGNORECASE | re.MULTILINE)
        
        for table_match in table_matches:
            table_content = table_match.group(1)
            
            # Extract rows from the table
            row_pattern = r'\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|'
            rows = re.finditer(row_pattern, table_content)
            
            for row in rows:
                attr_name = row.group(1).strip()
                attr_type = row.group(2).strip()
                required = row.group(3).strip().lower() in ['yes', 'true', 'required']
                description = row.group(4).strip()
                
                # Filter for attributes in the specified namespace
                if attr_name.startswith(namespace) and '.' in attr_name:
                    attributes.append(AttributeInfo(
                        name=attr_name,
                        description=description,
                        type=attr_type,
                        required=required
                    ))
        
        # Fallback: extract attributes by namespace prefix from any text
        if not attributes:
            namespace_pattern = rf'{re.escape(namespace)}\.[\w\.]+'
            matches = re.findall(namespace_pattern, content)
            
            for match in set(matches):  # Remove duplicates
                attributes.append(AttributeInfo(
                    name=match,
                    description="",
                    type="string",
                    required=False
                ))
        
        return attributes

    def analyze_contextcore_conventions(self) -> None:
        """Analyze ContextCore semantic conventions from documentation files."""
        doc_files = {
            'agent': ('docs/agent-semantic-conventions.md', 'agent.'),
            'insight': ('docs/semantic-conventions.md', 'insight.'),
            'handoff': ('docs/semantic-conventions.md', 'handoff.'),
            'general': ('docs/semantic-conventions.md', '')
        }
        
        for category, (file_path, namespace) in doc_files.items():
            content = self._read_file(file_path)
            if content:
                attributes = self._extract_attributes_from_markdown(content, namespace)
                if attributes:
                    self.contextcore_attributes[category] = attributes

    def _find_otel_equivalent(self, cc_attr: str) -> Optional[str]:
        """Find the closest OTel GenAI equivalent for a ContextCore attribute."""
        # Direct mapping rules based on semantic meaning
        mappings = {
            'agent.id': 'gen_ai.system',
            'agent.name': 'gen_ai.system',
            'agent.model': 'gen_ai.request.model',
            'agent.model.name': 'gen_ai.request.model',
            'agent.model.provider': None,  # No direct OTel equivalent
            'agent.temperature': 'gen_ai.request.temperature',
            'agent.max_tokens': 'gen_ai.request.max_tokens',
            'agent.top_p': 'gen_ai.request.top_p',
            'agent.prompt': 'gen_ai.prompt',
            'agent.response': 'gen_ai.completion',
            'agent.response.id': 'gen_ai.response.id',
            'agent.token.count.input': 'gen_ai.usage.input_tokens',
            'agent.token.count.output': 'gen_ai.usage.output_tokens',
            'agent.finish_reason': 'gen_ai.response.finish_reasons',
        }
        
        return mappings.get(cc_attr)

    def _get_recommendation(self, cc_attr: str, otel_equiv: Optional[str]) -> Tuple[str, str, int, str]:
        """Determine migration recommendation for an attribute."""
        if otel_equiv:
            # Has direct OTel equivalent
            if cc_attr.startswith('agent.'):
                return 'MIGRATE', 'MEDIUM', 3, 'Direct OTel equivalent available'
            else:
                return 'ALIAS', 'LOW', 2, 'Emit both during transition'
        elif cc_attr.startswith(('insight.', 'handoff.')):
            # ContextCore-specific functionality
            return 'PRESERVE', 'NONE', 1, 'ContextCore-specific, no OTel equivalent'
        else:
            # Consider adding new OTel attributes
            return 'ADD', 'LOW', 2, 'Consider proposing to OTel GenAI spec'

    def generate_attribute_mappings(self) -> Dict[str, List[MappingResult]]:
        """Generate attribute mappings for each category."""
        mappings = {}
        
        for category, attributes in self.contextcore_attributes.items():
            category_mappings = []
            
            for attr in attributes:
                otel_equiv = self._find_otel_equivalent(attr.name)
                recommendation, risk, complexity, notes = self._get_recommendation(attr.name, otel_equiv)
                
                category_mappings.append(MappingResult(
                    contextcore_attr=attr.name,
                    otel_equivalent=otel_equiv,
                    recommendation=recommendation,
                    breaking_risk=risk,
                    complexity=complexity,
                    notes=notes
                ))
            
            mappings[category] = category_mappings
        
        return mappings

    def generate_markdown_report(self, mappings: Dict[str, List[MappingResult]]) -> str:
        """Generate the final markdown gap analysis report."""
        report = []
        
        # Header
        report.append("# OTel GenAI Gap Analysis")
        report.append("")
        report.append("Analysis of ContextCore semantic conventions against OpenTelemetry GenAI conventions.")
        report.append("")
        
        # Executive Summary
        total_attrs = sum(len(attrs) for attrs in mappings.values())
        migrate_count = sum(1 for attrs in mappings.values() for attr in attrs if attr.recommendation == 'MIGRATE')
        preserve_count = sum(1 for attrs in mappings.values() for attr in attrs if attr.recommendation == 'PRESERVE')
        
        report.append("## Executive Summary")
        report.append("")
        report.append(f"- **Total ContextCore Attributes Analyzed**: {total_attrs}")
        report.append(f"- **Direct OTel Equivalents**: {migrate_count}")
        report.append(f"- **ContextCore-Specific Attributes**: {preserve_count}")
        report.append("")
        
        # Detailed Analysis by Category
        for category, category_mappings in mappings.items():
            if not category_mappings:
                continue
                
            report.append(f"## {category.title()} Namespace Analysis")
            report.append("")
            
            # Table header
            report.append("| ContextCore Attribute | OTel GenAI Equivalent | Recommendation | Breaking Risk | Complexity | Notes |")
            report.append("|----------------------|----------------------|---------------|--------------|------------|-------|")
            
            # Table rows
            for mapping in category_mappings:
                otel_equiv = mapping.otel_equivalent or 'N/A'
                report.append(f"| `{mapping.contextcore_attr}` | `{otel_equiv}` | {mapping.recommendation} | {mapping.breaking_risk} | {mapping.complexity} | {mapping.notes} |")
            
            report.append("")
        
        # Migration Recommendations
        report.append("## Migration Recommendations")
        report.append("")
        report.append("### Phase 1: Low-Risk Additions")
        report.append("- Add OTel GenAI attributes alongside existing ContextCore attributes")
        report.append("- Implement dual emission for attributes with direct equivalents")
        report.append("")
        report.append("### Phase 2: Gradual Migration")
        report.append("- Begin deprecation notices for attributes being migrated")
        report.append("- Update documentation to prefer OTel attributes")
        report.append("")
        report.append("### Phase 3: Cleanup")
        report.append("- Remove deprecated ContextCore attributes in major version bump")
        report.append("- Maintain ContextCore-specific attributes that add unique value")
        report.append("")
        
        # Timeline
        report.append("## Suggested Timeline")
        report.append("")
        report.append("- **Month 1-2**: Implement dual emission (ALIAS strategy)")
        report.append("- **Month 3-4**: Update tooling and dashboards")
        report.append("- **Month 5-6**: Begin deprecation process")
        report.append("- **Month 7-12**: Complete migration in next major release")
        report.append("")
        
        return "\n".join(report)

    def generate_report(self) -> str:
        """Generate the complete gap analysis report."""
        # Analyze ContextCore conventions
        self.analyze_contextcore_conventions()
        
        # Generate attribute mappings
        mappings = self.generate_attribute_mappings()
        
        # Create markdown report
        return self.generate_markdown_report(mappings)


class HandoffManager:
    """
    Manages agent handoffs with OpenTelemetry gen_ai tool convention support.
    """
    
    def __init__(self, tracer):
        """
        Initialize HandoffManager.
        
        Args:
            tracer: OpenTelemetry tracer instance
        """
        self._tracer = tracer
        self._dual_emit = DualEmitLayer()

    def create_handoff(self, capability_id: str, inputs: Dict[str, Any], 
                       context_id: str, priority: int = 0) -> str:
        """
        Create a new handoff with dual-emit attributes.
        
        Args:
            capability_id: Target capability identifier
            inputs: Input parameters for the capability
            context_id: Associated context identifier
            priority: Handoff priority (default: 0)
            
        Returns:
            Generated handoff identifier
            
        Raises:
            ValueError: If capability_id is None or empty
        """
        if not capability_id:
            raise ValueError("capability_id cannot be None or empty.")
        
        handoff_id = str(uuid.uuid4())
        
        # Build base attributes with legacy names
        attributes = {
            "handoff.id": handoff_id,
            "handoff.capability_id": capability_id,
            "handoff.inputs": json.dumps(inputs, default=str) if inputs else "{}",
            "handoff.context_id": context_id,
            "handoff.priority": priority,
            "handoff.status": "pending",
        }
        
        # Add tool-specific attributes (no legacy equivalent)
        attributes.update(TOOL_ATTRIBUTES)
        
        # Apply dual-emit transformation
        final_attributes = self._dual_emit.transform(attributes)

        # Create handoff span
        with self._tracer.start_as_current_span("handoff.create", attributes=final_attributes):
            # Additional handoff creation logic would go here
            pass

        return handoff_id

    def complete_handoff(self, handoff_id: str, result_trace_id: str) -> None:
        """
        Complete a handoff and record the result.
        
        Args:
            handoff_id: Handoff identifier to complete
            result_trace_id: Trace ID of the execution result
            
        Raises:
            ValueError: If handoff_id is None or empty
        """
        if not handoff_id:
            raise ValueError("handoff_id cannot be None or empty.")
        
        # Prepare result payload
        result_data = {
            "status": "success",
            "trace_id": result_trace_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Build completion attributes
        attributes = {
            "handoff.id": handoff_id,
            "handoff.status": "completed",
            "gen_ai.tool.call.result": json.dumps(result_data),
        }
        
        # Apply dual-emit transformation
        final_attributes = self._dual_emit.transform(attributes)
        
        # Create completion span
        with self._tracer.start_as_current_span("handoff.complete", attributes=final_attributes):
            # Additional completion logic would go here
            pass


# File: tests/unit/compat/test_otel_genai.py



class InsightEmitter:
    """Emits insights with OTel-compliant conversation tracking."""
    
    def emit(
        self,
        insight_type: str,
        summary: str,
        confidence: float,
        conversation_id: Optional[str] = None,  # NEW: Primary parameter
        session_id: Optional[str] = None,       # DEPRECATED: Alias
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """
        Emit insight with conversation tracking.
        
        Args:
            insight_type: Type of insight being emitted
            summary: Human-readable summary of the insight
            confidence: Confidence score (0.0-1.0)
            conversation_id: OTel-compliant conversation identifier
            session_id: DEPRECATED - Use conversation_id instead
            metadata: Additional metadata dict
            **kwargs: Additional attributes
        """
        # Handle deprecation with clear migration path
        if session_id is not None:
            warnings.warn(
                "Parameter 'session_id' is deprecated and will be removed in v2.0.0. "
                "Use 'conversation_id' instead for OTel compliance.",
                DeprecationWarning,
                stacklevel=2
            )
            # Prefer conversation_id if both provided
            conversation_id = conversation_id or session_id

        # Build base attributes
        attributes = {
            "insight.type": insight_type,
            "insight.summary": summary,
            "insight.confidence": confidence,
        }
        
        # Add conversation tracking if provided
        if conversation_id is not None:
            attributes["agent.session_id"] = conversation_id
            
        # Add metadata and kwargs
        if metadata:
            attributes.update(metadata)
        attributes.update(kwargs)

        # Apply dual-emit transformation
        transformed_attributes = transform(attributes, legacy_mode=False)
        
        # Emit to telemetry system (implementation would go here)
        self._emit_to_telemetry(transformed_attributes)
    
    def _emit_to_telemetry(self, attributes: Dict[str, Any]) -> None:
        """Internal method to emit to actual telemetry backend."""
        # Implementation would integrate with actual telemetry system
        pass


class InsightQuerier:
    """Query insights with OTel-compliant conversation tracking."""
    
    def query_by_conversation(
        self,
        conversation_id: Optional[str] = None,  # NEW: Primary parameter
        session_id: Optional[str] = None,       # DEPRECATED: Alias
        **filters
    ) -> List[InsightRecord]:
        """
        Query insights by conversation ID.
        
        Args:
            conversation_id: OTel-compliant conversation identifier
            session_id: DEPRECATED - Use conversation_id instead
            **filters: Additional query filters
            
        Returns:
            List of matching InsightRecord instances
        """
        # Handle deprecation
        if session_id is not None:
            warnings.warn(
                "Parameter 'session_id' is deprecated and will be removed in v2.0.0. "
                "Use 'conversation_id' instead for OTel compliance.",
                DeprecationWarning,
                stacklevel=2
            )
            conversation_id = conversation_id or session_id

        # Query implementation would go here
        query_params = {"conversation_id": conversation_id, **filters}
        return self._execute_query(query_params)
    
    def _execute_query(self, params: Dict[str, Any]) -> List[InsightRecord]:
        """Internal method to execute the actual query."""
        # Implementation would integrate with actual storage backend
        return []

# contextcore/handoff.py


class InsightRecord:
    """Represents an insight record with conversation tracking."""
    
    def __init__(self, insight_type: str, summary: str, confidence: float, 
                 conversation_id: Optional[str] = None, **kwargs):
        self.insight_type = insight_type
        self.summary = summary
        self.confidence = confidence
        self.conversation_id = conversation_id
        self.metadata = kwargs


class InsightsAPI:
    """API for insight emission and retrieval."""
    
    def emit_insight(
        self,
        insight_type: str,
        summary: str,
        confidence: float,
        conversation_id: Optional[str] = None,  # NEW: Primary parameter
        session_id: Optional[str] = None,       # DEPRECATED: Alias
        **kwargs
    ) -> None:
        """
        Emit insight via API with conversation tracking.
        
        Args:
            insight_type: Type of insight being emitted
            summary: Human-readable summary
            confidence: Confidence score (0.0-1.0)
            conversation_id: OTel-compliant conversation identifier
            session_id: DEPRECATED - Use conversation_id instead
            **kwargs: Additional attributes
        """
        # Handle deprecation
        if session_id is not None:
            warnings.warn(
                "Parameter 'session_id' is deprecated and will be removed in v2.0.0. "
                "Use 'conversation_id' instead for OTel compliance.",
                DeprecationWarning,
                stacklevel=2
            )
            conversation_id = conversation_id or session_id
            
        # Build attributes for emission
        attributes = {
            "insight.type": insight_type,
            "insight.summary": summary,
            "insight.confidence": confidence,
        }
        
        if conversation_id is not None:
            attributes["agent.session_id"] = conversation_id
            
        attributes.update(kwargs)

        # Apply dual-emit transformation and send to telemetry
        transformed_attributes = transform(attributes, legacy_mode=False)
        self._send_to_backend(transformed_attributes)
    
    def _send_to_backend(self, attributes: Dict[str, Any]) -> None:
        """Internal method to send to API backend."""
        # Implementation would integrate with actual API backend
        pass

# contextcore/cli/insight.py


class MappingResult(NamedTuple):
    """Result of comparing a ContextCore attribute to OTel GenAI."""
    contextcore_attr: str
    otel_equivalent: Optional[str]
    recommendation: str
    breaking_risk: str
    complexity: int
    notes: str


class TestDualEmitLayer(unittest.TestCase):
    """Test cases for OpenTelemetry gen_ai attribute mapping."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.transformer = DualEmitLayer()

    def test_dual_emit_preserves_original_attributes(self):
        """Test that original attributes are preserved in transformation."""
        input_attrs = {
            "handoff.id": "test-123",
            "handoff.capability_id": "data_processor",
            "custom.attribute": "preserved"
        }
        
        result = self.transformer.transform(input_attrs)
        
        # Original attributes should be preserved
        self.assertEqual(result["handoff.id"], "test-123")
        self.assertEqual(result["handoff.capability_id"], "data_processor")
        self.assertEqual(result["custom.attribute"], "preserved")

    def test_attribute_mapping_transformation(self):
        """Test that mapped attributes are correctly added."""
        input_attrs = {
            "context.id": "ctx-456",
            "handoff.capability_id": "process_data",
            "handoff.id": "handoff-789",
            "handoff.inputs": '{"param": "value"}'
        }
        
        result = self.transformer.transform(input_attrs)
        
        # Mapped attributes should be present
        self.assertEqual(result["gen_ai.request.id"], "ctx-456")
        self.assertEqual(result["gen_ai.tool.name"], "process_data")
        self.assertEqual(result["gen_ai.tool.call.id"], "handoff-789")
        self.assertEqual(result["gen_ai.tool.call.arguments"], '{"param": "value"}')
        
        # Original attributes should still exist
        self.assertEqual(result["context.id"], "ctx-456")
        self.assertEqual(result["handoff.capability_id"], "process_data")

    def test_tool_attributes_constants(self):
        """Test tool attributes are properly defined."""
        self.assertIn("gen_ai.tool.type", TOOL_ATTRIBUTES)
        self.assertEqual(TOOL_ATTRIBUTES["gen_ai.tool.type"], "agent_handoff")

    def test_empty_input_handling(self):
        """Test handling of empty inputs."""
        empty_dict = {}
        serialized = json.dumps(empty_dict, default=str)
        self.assertEqual(serialized, "{}")

    def test_unmapped_attributes_passthrough(self):
        """Test that unmapped attributes pass through unchanged."""
        input_attrs = {
            "custom.field": "value",
            "another.attribute": 42
        }
        
        result = self.transformer.transform(input_attrs)
        
        self.assertEqual(result["custom.field"], "value")
        self.assertEqual(result["another.attribute"], 42)



class TestHandoffManager(unittest.TestCase):
    """Test cases for HandoffManager with gen_ai tool support."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_tracer = Mock()
        self.mock_span = Mock()
        self.mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=self.mock_span)
        self.mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)
        
        self.manager = HandoffManager(self.mock_tracer)

    def test_create_handoff_success(self):
        """Test successful handoff creation."""
        result = self.manager.create_handoff(
            capability_id="test_capability",
            inputs={"param": "value"},
            context_id="ctx-123"
        )
        
        # Should return a valid UUID string
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 36)  # UUID string length
        
        # Should create a span
        self.mock_tracer.start_as_current_span.assert_called_once()

    def test_create_handoff_empty_capability_id(self):
        """Test handoff creation with empty capability_id raises ValueError."""
        with self.assertRaises(ValueError) as context:
            self.manager.create_handoff("", {}, "ctx-123")
        
        self.assertIn("capability_id cannot be None or empty", str(context.exception))

    def test_create_handoff_with_empty_inputs(self):
        """Test handoff creation with empty inputs."""
        result = self.manager.create_handoff(
            capability_id="test_capability",
            inputs={},
            context_id="ctx-123"
        )
        
        self.assertIsInstance(result, str)

    def test_complete_handoff_success(self):
        """Test successful handoff completion."""
        self.manager.complete_handoff("handoff-123", "trace-456")
        
        # Should create a completion span
        self.mock_tracer.start_as_current_span.assert_called_once()

    def test_complete_handoff_empty_id(self):
        """Test handoff completion with empty ID raises ValueError."""
        with self.assertRaises(ValueError) as context:
            self.manager.complete_handoff("", "trace-456")
        
        self.assertIn("handoff_id cannot be None or empty", str(context.exception))



def emit(insight_type: str, summary: str, confidence: float, 
         conversation_id: Optional[str] = None, session_id: Optional[str] = None,
         metadata: Optional[str] = None):
    """
    Emit an insight with conversation tracking.
    
    Examples:
        contextcore insight emit "user_intent" "User wants to book flight" 0.95 --conversation-id abc123
        contextcore insight emit "error" "API timeout" 0.8 --session-id xyz789  # deprecated
    """
    # Handle CLI-level deprecation warning
    if session_id is not None:
        click.echo(
            click.style(
                "Warning: --session-id is deprecated and will be removed in v2.0.0. "
                "Use --conversation-id instead for OTel compliance.",
                fg='yellow'
            ),
            err=True
        )
        conversation_id = conversation_id or session_id

    # Parse metadata if provided
    parsed_metadata = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError as e:
            click.echo(f"Error parsing metadata JSON: {e}", err=True)
            return

    # Emit the insight
    emitter = InsightEmitter()
    try:
        emitter.emit(
            insight_type=insight_type,
            summary=summary,
            confidence=confidence,
            conversation_id=conversation_id,
            metadata=parsed_metadata
        )
        click.echo(f"✓ Insight emitted successfully")
        if conversation_id:
            click.echo(f"  Conversation ID: {conversation_id}")
    except Exception as e:
        click.echo(f"Error emitting insight: {e}", err=True)


def get_emit_mode() -> EmitMode:
    """
    Get the current emission mode from CONTEXTCORE_EMIT_MODE environment variable.
    
    Returns:
        EmitMode: The current emission mode, defaults to DUAL during migration.
    
    Examples:
        >>> os.environ['CONTEXTCORE_EMIT_MODE'] = 'otel'
        >>> get_emit_mode()
        <EmitMode.OTEL: 'otel'>
    """
    global _cached_mode
    if _cached_mode is None:
        mode_str = os.getenv("CONTEXTCORE_EMIT_MODE", "dual").lower()
        try:
            _cached_mode = EmitMode(mode_str)
        except ValueError:
            warnings.warn(
                f"Invalid CONTEXTCORE_EMIT_MODE '{mode_str}'. Using 'dual' mode.",
                UserWarning,
                stacklevel=2
            )
            _cached_mode = EmitMode.DUAL
    return _cached_mode



def insight_group():
    """Insight management commands."""
    pass


def query(conversation_id: Optional[str] = None, session_id: Optional[str] = None, 
          limit: int = 10):
    """Query insights by conversation."""
    
    # Handle CLI-level deprecation warning
    if session_id is not None:
        click.echo(
            click.style(
                "Warning: --session-id is deprecated and will be removed in v2.0.0. "
                "Use --conversation-id instead for OTel compliance.",
                fg='yellow'
            ),
            err=True
        )
        conversation_id = conversation_id or session_id

    querier = InsightQuerier()
    try:
        results = querier.query_by_conversation(
            conversation_id=conversation_id,
            limit=limit
        )
        
        if results:
            click.echo(f"Found {len(results)} insights:")
            for i, record in enumerate(results, 1):
                click.echo(f"  {i}. {record.insight_type}: {record.summary} "
                          f"(confidence: {record.confidence})")
        else:
            click.echo("No insights found.")
            
    except Exception as e:
        click.echo(f"Error querying insights: {e}", err=True)

def transform(attributes: Dict[str, Any], legacy_mode: bool = False) -> Dict[str, Any]:
    """
    Transform attributes using dual-emit pattern for backward compatibility.
    
    In non-legacy mode, keeps original attributes and adds OTel standard equivalents.
    In legacy mode, only keeps original attributes.
    
    Args:
        attributes: Original attributes dict
        legacy_mode: If True, skip OTel transformations
        
    Returns:
        Transformed attributes dict with both old and new keys (when not in legacy mode)
    """
    result = attributes.copy()  # Never modify input dict
    
    if not legacy_mode:
        for old_key, new_key in ATTRIBUTE_MAPPINGS.items():
            if old_key in result:
                result[new_key] = result[old_key]  # Add new key, keep old
    
    return result


def transform_attributes(attributes: Dict[str, Any], mode: Optional[EmitMode] = None) -> Dict[str, Any]:
    """
    Convenience function to transform attributes using the specified or default emission mode.
    
    Args:
        attributes: Dictionary of span attributes to transform.
        mode: Override the emission mode. If None, uses get_emit_mode().
    Returns:
        Dict[str, Any]: Transformed attributes according to emission mode.
    Examples:
        >>> attrs = {"agent.id": "test", "handoff.inputs": "data"}
        >>> result = transform_attributes(attrs, EmitMode.OTEL)
        >>> list(result.keys())
        ['gen_ai.agent.id', 'gen_ai.tool.call.arguments']
    """
    emitter = DualEmitAttributes(mode)
    return emitter.transform(attributes)

# contextcore/insights.py


def warn_legacy_attribute(attr_name: str) -> None:
    """
    Emit deprecation warning for legacy attribute usage.
    
    Args:
        attr_name: Name of the legacy attribute being used.
        
    Examples:
        >>> warn_legacy_attribute("agent.id")
        # Emits: DeprecationWarning: Legacy attribute 'agent.id' is deprecated...
    """
    new_attr = ATTRIBUTE_MAPPINGS.get(attr_name, "gen_ai.*")
    warnings.warn(
        f"Legacy attribute '{attr_name}' is deprecated. "
        f"Use '{new_attr}' instead.",
        DeprecationWarning,
        stacklevel=3  # Skip this function and the transform method
    )



class AttributeMapper:
    """
    Attribute mapper for dual-emit compatibility.
    Provides map_attributes() method expected by insights.py.
    """

    def __init__(self):
        self._emitter = DualEmitAttributes()

    def map_attributes(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map attributes using dual-emit transformation.

        Args:
            attributes: Dictionary of span attributes

        Returns:
            Transformed attributes with both legacy and OTel keys
        """
        return self._emitter.transform(attributes)


# Singleton mapper instance for import
mapper = AttributeMapper()


__all__ = ['AttributeInfo', 'AttributeMapper', 'DualEmitAttributes', 'DualEmitLayer', 'EmitMode', 'GapAnalysisGenerator', 'HandoffManager', 'InsightEmitter', 'InsightQuerier', 'InsightRecord', 'InsightsAPI', 'MappingResult', 'TestDualEmitLayer', 'TestHandoffManager', 'emit', 'get_emit_mode', 'insight_group', 'mapper', 'query', 'transform', 'transform_attributes', 'warn_legacy_attribute', 'ATTRIBUTE_MAPPINGS', 'TOOL_ATTRIBUTES']