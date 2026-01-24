"""Knowledge Graph Schema module for ContextCore.
__all__ = ['NodeType', 'EdgeType', 'Node', 'Edge', 'Graph']


This module defines the data models for a knowledge graph that represents
ProjectContext relationships, enabling impact analysis and cross-project intelligence.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional

__all__ = [
    "NodeType",
    "EdgeType", 
    "Node",
    "Edge",
    "Graph"
]


class NodeType(Enum):
    """Enumeration for the different types of nodes in the knowledge graph."""
    PROJECT = "project"
    RESOURCE = "resource"
    TEAM = "team"
    ADR = "adr"
    CONTRACT = "contract"
    RISK = "risk"
    REQUIREMENT = "requirement"
    INSIGHT = "insight"


class EdgeType(Enum):
    """Enumeration for the different types of edges representing relationships between nodes."""
    MANAGES = "manages"              # Project -> Resource
    DEPENDS_ON = "depends_on"        # Project -> Project (inferred from targets)
    OWNED_BY = "owned_by"           # Project -> Team
    IMPLEMENTS = "implements"        # Project -> ADR
    EXPOSES = "exposes"             # Project -> Contract
    HAS_RISK = "has_risk"           # Project -> Risk
    HAS_REQUIREMENT = "has_requirement"  # Project -> Requirement
    GENERATED = "generated"          # Project -> Insight
    CALLS = "calls"                 # Resource -> Resource (from traces)


@dataclass(frozen=True)
class Node:
    """Immutable representation of a node in the knowledge graph.

    Attributes:
        id: Unique identifier for the node
        type: Type of the node (NodeType enum)
        name: Human-readable name of the node
        attributes: Additional metadata as key-value pairs
        created_at: Creation timestamp in UTC
        updated_at: Last update timestamp in UTC
    """
    id: str
    type: NodeType
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Node instance to a JSON-serializable dictionary.

        Returns:
            Dict containing all node data with datetime fields as ISO strings
        """
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "attributes": self.attributes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class Edge:
    """Immutable representation of an edge in the knowledge graph.

    Attributes:
        source_id: ID of the source node
        target_id: ID of the target node
        type: Type of relationship (EdgeType enum)
        attributes: Additional metadata as key-value pairs
        weight: Numerical weight for graph algorithms (default 1.0)
    """
    source_id: str
    target_id: str
    type: EdgeType
    attributes: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert Edge instance to a JSON-serializable dictionary.

        Returns:
            Dict containing all edge data
        """
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type.value,
            "attributes": self.attributes,
            "weight": self.weight,
        }


@dataclass
class Graph:
    """Container for nodes and edges forming a knowledge graph.

    Provides efficient operations for building and querying graph structures
    with O(1) node lookup and O(n) edge traversal operations.

    Attributes:
        nodes: Dictionary mapping node IDs to Node instances for O(1) lookup
        edges: List of all edges in the graph
    """
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        """Add or update a node in the graph.

        If a node with the same ID already exists, it will be replaced.

        Args:
            node: Node instance to add to the graph
        """
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the graph with validation.

        Validates that both source and target nodes exist before adding the edge.

        Args:
            edge: Edge instance to add to the graph

        Raises:
            ValueError: If source_id or target_id does not exist in the graph
        """
        if edge.source_id not in self.nodes:
            raise ValueError(f"Source node '{edge.source_id}' does not exist in graph")
        if edge.target_id not in self.nodes:
            raise ValueError(f"Target node '{edge.target_id}' does not exist in graph")
        
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Retrieve a node by its ID.

        Args:
            node_id: The unique identifier of the node

        Returns:
            The Node instance if found, None otherwise
        """
        return self.nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> List[Edge]:
        """Get all outgoing edges from a specified node.

        Args:
            node_id: The ID of the source node

        Returns:
            List of edges where the node is the source
        """
        return [edge for edge in self.edges if edge.source_id == node_id]

    def get_edges_to(self, node_id: str) -> List[Edge]:
        """Get all incoming edges to a specified node.

        Args:
            node_id: The ID of the target node

        Returns:
            List of edges where the node is the target
        """
        return [edge for edge in self.edges if edge.target_id == node_id]

    def to_dict(self) -> Dict[str, List[Dict[str, Any]]]:
        """Convert the entire graph to a JSON-serializable dictionary.

        Returns:
            Dictionary with 'nodes' and 'edges' keys containing lists of
            serialized node and edge data respectively
        """
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }
