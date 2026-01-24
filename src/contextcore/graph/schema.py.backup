"""Knowledge graph schema definitions.

This module defines the data models for the ContextCore knowledge graph,
which represents ProjectContext relationships for impact analysis and
cross-project intelligence.
"""

__all__ = [
    "NodeType",
    "EdgeType",
    "Node",
    "Edge",
    "Graph",
]

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeType(Enum):
    """Types of nodes in the knowledge graph."""

    PROJECT = "project"
    RESOURCE = "k8s_resource"
    TEAM = "team"
    ADR = "adr"
    CONTRACT = "api_contract"
    RISK = "risk"
    REQUIREMENT = "requirement"
    INSIGHT = "insight"


class EdgeType(Enum):
    """Types of relationships between nodes."""

    MANAGES = "manages"  # Project -> Resource
    DEPENDS_ON = "depends_on"  # Project -> Project (inferred from targets)
    OWNED_BY = "owned_by"  # Project -> Team
    IMPLEMENTS = "implements"  # Project -> ADR
    EXPOSES = "exposes"  # Project -> Contract
    HAS_RISK = "has_risk"  # Project -> Risk
    HAS_REQUIREMENT = "has_requirement"  # Project -> Requirement
    GENERATED = "generated"  # Project -> Insight
    CALLS = "calls"  # Resource -> Resource (from traces)


@dataclass
class Node:
    """A node in the knowledge graph.

    Attributes:
        id: Unique identifier for the node (e.g., "project:my-service")
        type: The type of node (PROJECT, RESOURCE, TEAM, etc.)
        name: Human-readable display name
        attributes: Arbitrary metadata about the node
        created_at: When the node was created
        updated_at: When the node was last updated
    """

    id: str
    type: NodeType
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to a serializable dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class Edge:
    """An edge (relationship) in the knowledge graph.

    Attributes:
        source_id: ID of the source node
        target_id: ID of the target node
        type: The type of relationship
        attributes: Arbitrary metadata about the edge
        weight: Weight for graph algorithms (default 1.0)
    """

    source_id: str
    target_id: str
    type: EdgeType
    attributes: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert edge to a serializable dictionary."""
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.type.value,
            "attributes": self.attributes,
            "weight": self.weight,
        }


@dataclass
class Graph:
    """The complete knowledge graph.

    A graph consists of nodes (entities) and edges (relationships).
    Provides methods for adding and querying graph elements.

    Attributes:
        nodes: Dictionary mapping node ID to Node objects
        edges: List of Edge objects representing relationships
    """

    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        """Add a node to the graph.

        If a node with the same ID already exists, it will be replaced.

        Args:
            node: The node to add
        """
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the graph.

        Args:
            edge: The edge to add
        """
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID.

        Args:
            node_id: The ID of the node to retrieve

        Returns:
            The node if found, None otherwise
        """
        return self.nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> List[Edge]:
        """Get all edges originating from a node.

        Args:
            node_id: The source node ID

        Returns:
            List of edges with source_id matching node_id
        """
        return [e for e in self.edges if e.source_id == node_id]

    def get_edges_to(self, node_id: str) -> List[Edge]:
        """Get all edges pointing to a node.

        Args:
            node_id: The target node ID

        Returns:
            List of edges with target_id matching node_id
        """
        return [e for e in self.edges if e.target_id == node_id]

    def to_dict(self) -> Dict[str, Any]:
        """Convert graph to a serializable dictionary.

        Returns:
            Dictionary with 'nodes' and 'edges' lists
        """
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }
