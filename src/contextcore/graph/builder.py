"""
Knowledge Graph Builder module for ContextCore.
__all__ = ['GraphBuilder', 'GraphWatcher']


This module builds a knowledge graph from ProjectContext CRDs, extracting nodes and edges
from the structured metadata to create a comprehensive view of project relationships,
resources, risks, and dependencies.
"""

import hashlib
from typing import Any, Dict, List, Optional

# Import required classes from contextcore.graph.schema
from contextcore.graph.schema import Graph, Node, Edge, NodeType, EdgeType

# Kubernetes imports for the GraphWatcher stub
try:
    from kubernetes import client, config, watch
except ImportError:
    # Graceful fallback if kubernetes client is not available
    client = config = watch = None

__all__ = ['GraphBuilder', 'GraphWatcher']


class GraphBuilder:
    """
    Builds a knowledge graph from ProjectContext CRDs.
    
    Extracts nodes and edges from structured metadata to create relationships
    between projects, teams, resources, ADRs, contracts, and risks.
    """
    
    def __init__(self) -> None:
        """Initialize empty graph and resource-to-project mapping."""
        self.graph = Graph()
        self._resource_to_project: Dict[str, List[str]] = {}

    def build_from_contexts(self, contexts: List[Dict[str, Any]]) -> Graph:
        """
        Build a complete knowledge graph from a list of ProjectContext CRDs.
        
        Args:
            contexts: List of ProjectContext CRD dictionaries
            
        Returns:
            Graph: The completed knowledge graph with all nodes and edges
        """
        # Reset graph and mappings for fresh build
        self.graph = Graph()
        self._resource_to_project.clear()
        
        # Process each context to extract nodes and edges
        for ctx in contexts:
            self._process_context(ctx)
        
        # Infer additional dependencies after all contexts are processed
        self._infer_dependencies()
        
        return self.graph

    def _process_context(self, ctx: Dict[str, Any]) -> None:
        """
        Process a single ProjectContext CRD to extract nodes and relationships.
        
        Args:
            ctx: ProjectContext CRD dictionary with metadata and spec
        """
        metadata = ctx.get("metadata", {})
        spec = ctx.get("spec", {})
        
        # Extract project identification
        project_name = metadata.get("name", "")
        project_namespace = metadata.get("namespace", "")
        project_id = self._get_project_id(spec.get("project", {}), project_name)
        
        # Create PROJECT node with business attributes
        business = spec.get("business", {})
        project_attrs = {
            "namespace": project_namespace,
            "criticality": business.get("criticality"),
            "value": business.get("value"),
            "epic": self._get_epic_from_project_spec(spec.get("project", {}))
        }
        self.graph.add_node(NodeType.PROJECT, project_id, project_attrs)
        
        # Create TEAM node and OWNED_BY relationship
        team_owner = business.get("owner")
        if team_owner:
            self.graph.add_node(NodeType.TEAM, team_owner, {})
            self.graph.add_edge(EdgeType.OWNED_BY, project_id, team_owner)
        
        # Process target resources and create MANAGES relationships
        targets = spec.get("targets", [])
        for target in targets:
            if not isinstance(target, dict) or not target.get("name"):
                continue
                
            resource_id = self._make_resource_id(target, project_namespace)
            resource_attrs = {
                "kind": target.get("kind", ""),
                "name": target.get("name", ""),
                "namespace": target.get("namespace", project_namespace)
            }
            self.graph.add_node(NodeType.RESOURCE, resource_id, resource_attrs)
            self.graph.add_edge(EdgeType.MANAGES, project_id, resource_id)
            
            # Track resource-to-project mapping for dependency inference
            if resource_id not in self._resource_to_project:
                self._resource_to_project[resource_id] = []
            self._resource_to_project[resource_id].append(project_id)
        
        # Process design elements
        design = spec.get("design", {})
        
        # Create ADR node and IMPLEMENTS relationship
        adr_url = design.get("adr")
        if adr_url:
            adr_id = f"adr-{project_name}"
            self.graph.add_node(NodeType.ADR, adr_id, {"url": adr_url})
            self.graph.add_edge(EdgeType.IMPLEMENTS, project_id, adr_id)
        
        # Create CONTRACT node and EXPOSES relationship
        api_contract = design.get("apiContract")
        if api_contract:
            contract_id = f"contract-{self._hash_url(api_contract)}"
            self.graph.add_node(NodeType.CONTRACT, contract_id, {"url": api_contract})
            self.graph.add_edge(EdgeType.EXPOSES, project_id, contract_id)
        
        # Process risks with priority-based weights
        risks = spec.get("risks", [])
        for i, risk in enumerate(risks):
            if not isinstance(risk, dict):
                continue
                
            risk_id = f"risk-{project_name}-{i}"
            risk_attrs = {
                "type": risk.get("type"),
                "priority": risk.get("priority"),
                "description": risk.get("description"),
                "scope": risk.get("scope")
            }
            self.graph.add_node(NodeType.RISK, risk_id, risk_attrs)
            
            # Add weighted HAS_RISK edge based on priority
            risk_weight = self._risk_weight(risk.get("priority"))
            self.graph.add_edge(EdgeType.HAS_RISK, project_id, risk_id, {"weight": risk_weight})

    def _get_project_id(self, spec: Dict[str, Any], default: str) -> str:
        """
        Extract project ID from spec, falling back to default name.
        
        Args:
            spec: Project specification dictionary
            default: Default project name to use if ID not found
            
        Returns:
            str: Project identifier
        """
        if isinstance(spec, str):
            return spec
        return spec.get("id", default)
    
    def _get_epic_from_project_spec(self, project_spec: Dict[str, Any]) -> Optional[str]:
        """Extract epic from project specification."""
        if isinstance(project_spec, dict):
            return project_spec.get("epic")
        return None

    def _make_resource_id(self, target: Dict[str, Any], default_ns: str) -> str:
        """
        Create standardized resource identifier.
        
        Args:
            target: Resource target dictionary with kind, name, namespace
            default_ns: Default namespace if not specified in target
            
        Returns:
            str: Resource ID in format "resource:{namespace}/{kind}/{name}"
        """
        namespace = target.get("namespace", default_ns)
        kind = target.get("kind", "")
        name = target.get("name", "")
        return f"resource:{namespace}/{kind}/{name}"

    def _hash_url(self, url: str) -> str:
        """
        Generate MD5 hash of URL, truncated to first 12 characters.
        
        Args:
            url: URL string to hash
            
        Returns:
            str: First 12 characters of MD5 hash
        """
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _risk_weight(self, priority: Optional[str]) -> float:
        """
        Convert risk priority to numeric weight for graph edges.
        
        Args:
            priority: Risk priority string (P1, P2, P3, P4)
            
        Returns:
            float: Numeric weight (P1=4.0, P2=3.0, P3=2.0, P4=1.0, default=1.0)
        """
        priority_weights = {
            "P1": 4.0,  # Critical
            "P2": 3.0,  # High
            "P3": 2.0,  # Medium
            "P4": 1.0   # Low
        }
        return priority_weights.get(priority, 1.0)

    def _infer_dependencies(self) -> None:
        """
        Infer additional dependencies between projects based on resources.
        
        Currently focuses on Service resources as potential dependency points.
        Future implementations could use distributed tracing data for more
        sophisticated dependency inference.
        """
        # Find Service resources that could indicate dependencies
        service_resources = [
            resource_id for resource_id in self._resource_to_project.keys()
            if "Service" in resource_id
        ]
        
        # Placeholder for future trace-based dependency inference
        # This could analyze distributed tracing data to identify
        # actual service-to-service communication patterns
        pass


class GraphWatcher:
    """
    Watches for changes to ProjectContext CRDs and updates the knowledge graph.
    
    This is a stub implementation that provides the interface for future
    Kubernetes-based watching capabilities.
    """
    
    def __init__(self, builder: GraphBuilder) -> None:
        """
        Initialize watcher with a GraphBuilder instance.
        
        Args:
            builder: GraphBuilder instance to use for graph updates
        """
        self.builder = builder
        self._watching = False

    def start(self) -> None:
        """
        Start watching for ProjectContext CRD changes.
        
        Placeholder implementation - in production this would use
        kubernetes.watch to monitor CRD changes and trigger graph updates.
        """
        if client is None:
            raise RuntimeError("Kubernetes client not available")
        
        self._watching = True
        # TODO: Implement actual Kubernetes watching logic
        # Example:
        # v1 = client.CustomObjectsApi()
        # w = watch.Watch()
        # for event in w.stream(v1.list_cluster_custom_object, ...):
        #     self._handle_event(event)

    def stop(self) -> None:
        """Stop watching for CRD changes."""
        self._watching = False

    def _remove_context(self, ctx: Dict[str, Any]) -> None:
        """
        Remove a project context from the knowledge graph.
        
        Args:
            ctx: ProjectContext CRD dictionary to remove
            
        This is a placeholder for future implementation that would
        identify and remove all nodes and edges associated with
        the given project context.
        """
        # TODO: Implement context removal logic
        # This would need to:
        # 1. Identify the project ID from the context
        # 2. Find all associated nodes (resources, risks, ADRs, etc.)
        # 3. Remove nodes and edges from the graph
        # 4. Update the resource-to-project mapping
        pass
