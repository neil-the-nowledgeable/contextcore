"""
Knowledge Graph Queries module for ContextCore.
__all__ = ['ImpactReport', 'DependencyReport', 'GraphQueries']


Provides query operations on the knowledge graph for impact analysis,
dependency discovery, and path finding using BFS traversal.
"""
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from contextcore.graph.schema import Graph, Node, Edge, NodeType, EdgeType


@dataclass
class ImpactReport:
    """Report detailing the impact analysis of a project change."""
    source_project: str
    affected_projects: List[str]
    affected_teams: List[str]
    critical_projects: List[str]  # criticality == "critical"
    total_blast_radius: int
    dependency_paths: List[List[str]]  # paths showing impact propagation


@dataclass
class DependencyReport:
    """Report detailing the dependencies of a specific project."""
    project_id: str
    upstream: List[str]  # projects this depends on
    downstream: List[str]  # projects that depend on this
    shared_resources: List[str]
    shared_adrs: List[str]


class GraphQueries:
    """Provides query operations on the knowledge graph."""
    
    def __init__(self, graph: Graph):
        """Initialize with a Graph instance."""
        self.graph = graph

    def impact_analysis(self, project_id: str, max_depth: int = 5) -> ImpactReport:
        """
        Analyze the impact of changes to a project.
        
        Uses BFS to find all projects that would be affected by changes
        to the source project by following dependency relationships.
        
        Args:
            project_id: The source project to analyze
            max_depth: Maximum traversal depth (default: 5)
            
        Returns:
            ImpactReport with affected projects, teams, and paths
            
        Raises:
            ValueError: If project does not exist in the graph
        """
        if not self.graph.has_node(project_id):
            raise ValueError(f"Project {project_id} does not exist in the graph.")

        # BFS setup for impact analysis
        queue = deque([(project_id, 0, [project_id])])  # (node, depth, path)
        visited: Set[str] = {project_id}
        affected_projects = []
        affected_teams = set()
        critical_projects = []
        dependency_paths = []

        while queue:
            current_project, current_depth, current_path = queue.popleft()
            
            if current_depth < max_depth:
                # Find projects that depend on the current project (reverse direction)
                for edge in self.graph.edges:
                    if (edge.target == current_project and 
                        edge.type == EdgeType.DEPENDS_ON and 
                        edge.source not in visited):
                        
                        dependent_project = edge.source
                        visited.add(dependent_project)
                        affected_projects.append(dependent_project)
                        
                        # Get project node for additional information
                        project_node = self.graph.get_node(dependent_project)
                        if project_node:
                            affected_teams.add(project_node.team)
                            
                            # Check for critical projects
                            if hasattr(project_node, 'criticality') and project_node.criticality == "critical":
                                critical_projects.append(dependent_project)
                        
                        # Record the path to this affected project
                        new_path = current_path + [dependent_project]
                        dependency_paths.append(new_path)
                        
                        # Continue BFS from this node
                        queue.append((dependent_project, current_depth + 1, new_path))
                
                # Also follow MANAGES edges for shared resource impact
                for edge in self.graph.edges:
                    if (edge.source == current_project and 
                        edge.type == EdgeType.MANAGES):
                        
                        # Find other projects that manage the same resource
                        resource_id = edge.target
                        for other_edge in self.graph.edges:
                            if (other_edge.target == resource_id and 
                                other_edge.type == EdgeType.MANAGES and 
                                other_edge.source != current_project and 
                                other_edge.source not in visited):
                                
                                affected_project = other_edge.source
                                visited.add(affected_project)
                                affected_projects.append(affected_project)
                                
                                project_node = self.graph.get_node(affected_project)
                                if project_node:
                                    affected_teams.add(project_node.team)
                                    if hasattr(project_node, 'criticality') and project_node.criticality == "critical":
                                        critical_projects.append(affected_project)
                                
                                dependency_paths.append(current_path + [resource_id, affected_project])

        return ImpactReport(
            source_project=project_id,
            affected_projects=affected_projects,
            affected_teams=list(affected_teams),
            critical_projects=critical_projects,
            total_blast_radius=len(affected_projects),
            dependency_paths=dependency_paths
        )

    def get_dependencies(self, project_id: str) -> DependencyReport:
        """
        Get the dependency information for a project.
        
        Args:
            project_id: The project to analyze
            
        Returns:
            DependencyReport with upstream/downstream dependencies
            
        Raises:
            ValueError: If project does not exist in the graph
        """
        if not self.graph.has_node(project_id):
            raise ValueError(f"Project {project_id} does not exist in the graph.")

        upstream = []      # Projects this project depends on
        downstream = []    # Projects that depend on this project
        shared_resources = []
        shared_adrs = []

        for edge in self.graph.edges:
            # Upstream: edges FROM this project TO dependencies
            if edge.source == project_id and edge.type == EdgeType.DEPENDS_ON:
                upstream.append(edge.target)
            
            # Downstream: edges FROM other projects TO this project
            elif edge.target == project_id and edge.type == EdgeType.DEPENDS_ON:
                downstream.append(edge.source)
            
            # Shared resources: MANAGES edges from this project
            elif edge.source == project_id and edge.type == EdgeType.MANAGES:
                shared_resources.append(edge.target)
            
            # Shared ADRs: IMPLEMENTS edges from this project
            elif edge.source == project_id and edge.type == EdgeType.IMPLEMENTS:
                shared_adrs.append(edge.target)

        return DependencyReport(
            project_id=project_id,
            upstream=upstream,
            downstream=downstream,
            shared_resources=shared_resources,
            shared_adrs=shared_adrs
        )

    def find_path(self, from_project: str, to_project: str) -> Optional[List[str]]:
        """
        Find the shortest path between two projects using BFS.
        
        Args:
            from_project: Source project
            to_project: Target project
            
        Returns:
            List of project IDs forming the path, or None if no path exists
        """
        if not self.graph.has_node(from_project) or not self.graph.has_node(to_project):
            return None

        if from_project == to_project:
            return [from_project]

        queue = deque([from_project])
        visited: Set[str] = {from_project}
        predecessor: Dict[str, Optional[str]] = {from_project: None}
        
        while queue:
            current_project = queue.popleft()
            
            # Check all outgoing edges from current project
            for edge in self.graph.edges:
                if edge.source == current_project and edge.target not in visited:
                    visited.add(edge.target)
                    predecessor[edge.target] = current_project
                    queue.append(edge.target)
                    
                    # Check if we reached the target
                    if edge.target == to_project:
                        return self._reconstruct_path(predecessor, from_project, to_project)

        return None

    def _reconstruct_path(self, predecessor: Dict[str, Optional[str]], start: str, end: str) -> List[str]:
        """Reconstruct path from predecessor tracking."""
        path = []
        current = end
        while current is not None:
            path.append(current)
            current = predecessor[current]
        return path[::-1]  # Reverse to get start -> end order

    def get_risk_exposure(self, team: str) -> Dict[str, int]:
        """
        Get risk exposure counts for a team.
        
        Args:
            team: Team name to analyze
            
        Returns:
            Dictionary mapping risk types to counts
        """
        risk_counts: Dict[str, int] = {}

        # Find all projects owned by the team
        team_projects = []
        for edge in self.graph.edges:
            if edge.type == EdgeType.OWNED_BY and edge.target == team:
                team_projects.append(edge.source)

        # Aggregate risk counts from team's projects
        for project_id in team_projects:
            project_node = self.graph.get_node(project_id)
            if project_node and hasattr(project_node, 'risk_type'):
                risk_type = project_node.risk_type
                risk_counts[risk_type] = risk_counts.get(risk_type, 0) + 1

        return risk_counts

    def to_visualization_format(self) -> Dict[str, List[Dict]]:
        """
        Convert graph to visualization format for D3.js/vis.js.
        
        Returns:
            Dictionary with 'nodes' and 'links' arrays
        """
        nodes = []
        for node in self.graph.nodes:
            node_data = {
                "id": node.id,
                "label": getattr(node, 'label', node.id),
                "group": getattr(node, 'group', node.type.name if hasattr(node, 'type') else 'default')
            }
            # Add additional node attributes if they exist
            for attr in ['team', 'criticality', 'risk_type']:
                if hasattr(node, attr):
                    node_data[attr] = getattr(node, attr)
            nodes.append(node_data)

        links = []
        for edge in self.graph.edges:
            link_data = {
                "source": edge.source,
                "target": edge.target,
                "type": edge.type.name,
                "value": getattr(edge, 'weight', 1)  # Default weight of 1
            }
            links.append(link_data)

        return {"nodes": nodes, "links": links}


__all__ = [
    "ImpactReport",
    "DependencyReport", 
    "GraphQueries"
]
