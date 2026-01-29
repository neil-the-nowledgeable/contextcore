"""
Pydantic models for Wayfinder Terminology management.

These models define the schema for storing terminology definitions as OTel spans,
enabling TraceQL-based discovery and agent guidance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TermType(str, Enum):
    """Classification of terminology entries."""
    STANDARD = "standard"          # A specification or metadata model (e.g., ContextCore)
    IMPLEMENTATION = "implementation"  # A product implementing a standard (e.g., Wayfinder)
    PARADIGM = "paradigm"          # A way of thinking (e.g., Business Observability)
    ERA = "era"                    # A time period (e.g., Language Model 1.0)
    PACKAGE = "package"            # A software component (e.g., Spider, Rabbit)
    PRINCIPLE = "principle"        # A guideline for decisions


class QuickLookupEntry(BaseModel):
    """Inline definition for common terms (from MANIFEST quick_lookup)."""
    type: str = Field(..., description="Term type")
    one_liner: str = Field(..., description="Brief definition")
    analogy: Optional[str] = Field(None, description="Clarifying analogy")
    producer: Optional[str] = Field(None, description="Producing organization")


class TermNameOrigin(BaseModel):
    """Etymology and inspiration for a term name."""
    inspiration: str = Field(..., description="Source of name inspiration")
    meaning: str = Field(..., description="What the name represents")
    reflects: List[str] = Field(default_factory=list, description="Values the name reflects")
    acknowledgment: Optional[str] = Field(None, description="Cultural acknowledgment if needed")
    note: Optional[str] = Field(None, description="Additional notes")


class TerminologyTerm(BaseModel):
    """
    A terminology definition.

    Corresponds to files in terminology/definitions/*.yaml
    """
    model_config = ConfigDict(extra="allow")

    # Identity
    id: str = Field(..., description="Unique term identifier")
    name: str = Field(..., description="Display name")
    type: str = Field(..., description="Term type (see TermType)")
    version: str = Field(default="1.0.0", description="Term definition version")

    # Definition
    definition: str = Field(..., description="Full text definition")
    codename: Optional[str] = Field(None, description="Internal codename if any")
    producer: Optional[str] = Field(None, description="Producing organization")

    # Metadata
    category: Optional[str] = Field(None, description="Category (core_concepts, expansion_packs, etc.)")
    name_origin: Optional[TermNameOrigin] = Field(None, description="Etymology and inspiration")

    # For packages
    anishinaabe_name: Optional[str] = Field(None, description="Anishinaabe (Ojibwe) name")
    package_name: Optional[str] = Field(None, description="Package name (contextcore-{animal})")
    purpose: Optional[str] = Field(None, description="Package purpose description")

    # Components (for implementation type)
    components: Optional[List[Dict[str, str]]] = Field(None, description="Component packages")

    # Clarifications
    is_not: Optional[List[str]] = Field(None, description="Common misconceptions clarified")

    # Discovery
    triggers: List[str] = Field(default_factory=list, description="Keywords for routing")
    related_terms: List[str] = Field(default_factory=list, description="Related term IDs")

    # Persistence config
    tempo_query: Optional[str] = Field(None, description="Example Tempo query")
    loki_query: Optional[str] = Field(None, description="Example Loki query")

    # Token budget (estimated)
    token_budget: int = Field(default=150, description="Estimated token cost")

    # Source tracking
    source_file: Optional[str] = Field(None, description="Source YAML file path")


class TerminologyDistinction(BaseModel):
    """
    A clarification distinguishing commonly confused terms.

    Corresponds to entries in _index.yaml distinctions section.
    """
    id: str = Field(..., description="Distinction identifier (e.g., contextcore_vs_wayfinder)")
    question: str = Field(..., description="The question this distinction answers")
    answer: str = Field(..., description="The clarifying answer")
    analogy: Optional[str] = Field(None, description="Helpful analogy")
    terms_involved: List[str] = Field(default_factory=list, description="Term IDs involved")


class TermToAvoid(BaseModel):
    """A term to avoid in product naming."""
    term: str = Field(..., description="The term to avoid")
    reason: str = Field(..., description="Why to avoid it")
    alternatives: List[str] = Field(default_factory=list, description="Suggested alternatives")


class CategoryEntry(BaseModel):
    """A term reference within a category."""
    id: str
    file: str
    tokens: Optional[int] = None


class TermCategory(BaseModel):
    """A category of related terms."""
    description: str
    terms: List[CategoryEntry] = Field(default_factory=list)


class TerminologyManifest(BaseModel):
    """
    The MANIFEST.yaml structure - primary entry point for terminology.

    Follows progressive disclosure: agents read MANIFEST first,
    then load full definitions on demand.
    """
    model_config = ConfigDict(extra="allow")

    # Identity
    terminology_id: str = Field(..., description="Terminology set identifier")
    schema_version: str = Field(default="1.0.0", description="Schema version")
    last_updated: str = Field(..., description="Last update date (YYYY-MM-DD)")
    status: str = Field(default="authoritative", description="Status indicator")

    # Quick lookup (inline definitions)
    quick_lookup: Dict[str, QuickLookupEntry] = Field(
        default_factory=dict,
        description="Inline definitions for common terms"
    )

    # Categories with term references
    categories: Dict[str, TermCategory] = Field(
        default_factory=dict,
        description="Term categories with file references"
    )

    # Routing table (keyword -> term_id)
    routing: Dict[str, str] = Field(
        default_factory=dict,
        description="Keyword to term ID mapping"
    )

    # Constraints
    constraints: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Usage constraints"
    )

    # Token budget
    manifest_tokens: int = Field(default=200, description="Tokens for MANIFEST.yaml")
    index_tokens: int = Field(default=250, description="Tokens for _index.yaml")
    total_tokens: int = Field(default=0, description="Total tokens for all definitions")

    # Source tracking
    source_path: Optional[str] = Field(None, description="Source directory path")


class TerminologyIndex(BaseModel):
    """
    The _index.yaml structure - routing and distinctions.
    """
    model_config = ConfigDict(extra="allow")

    terminology_id: str
    index_version: str = "1.0.0"

    # Term type definitions
    term_types: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Key distinctions
    distinctions: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Hierarchy view
    hierarchy: Dict[str, Any] = Field(default_factory=dict)

    # Anishinaabe translations
    anishinaabe_translations: Dict[str, str] = Field(default_factory=dict)

    # Terms to avoid
    avoid: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Agent summary
    agent_summary: Optional[str] = None
