"""Query operations on the knowledge graph.

This module provides query capabilities for the ContextCore knowledge graph,
including impact analysis, dependency discovery, and path finding.
"""

__all__ = [
    "ImpactReport",
    "DependencyReport",
    "GraphQueries",
]

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from contextcore.graph.schema import Edge, EdgeType, Graph, Node, NodeType


@dataclass
class ImpactReport:
    """Report of impact from a change to a project.

    Attributes:
        source_project: The project being changed
        affected_projects: List of projects affected by the change
        affected_teams: List of teams that own affected projects
        critical_projects: Projects with criticality='critical' that are affected
        total_blast_radius: Total number of affected projects
        dependency_paths: Paths showing how impact propagates
    """

    source_project: str
    affected_projects: List[str]
    affected_teams: List[str]
    critical_projects: List[str]
    total_blast_radius: int
    dependency_paths: List[List[str]]


@dataclass
class DependencyReport:
    """Report of project dependencies.

    Attributes:
        project_id: The project being analyzed
        upstream: Projects this project depends on
        downstream: Projects that depend on this project
        shared_resources: Resources managed by this project
        shared_adrs: ADRs implemented by this project
    """

    project_id: str
    upstream: List[str]
    downstream: List[str]
    shared_resources: List[str]
    shared_adrs: List[str]


class GraphQueries:
    """Query operations on the knowledge graph.

    Example:
        queries = GraphQueries(graph)
        impact = queries.impact_analysis("my-project")
        deps = queries.get_dependencies("my-project")
    """

    def __init__(self, graph: Graph) -> None:
        """Initialize with a graph.

        Args:
            graph: The knowledge graph to query
        """
        self.graph = graph

    def impact_analysis(self, project_id: str, max_depth: int = 5) -> ImpactReport:
        """Analyze impact of changes to a project.

        Uses BFS to find all reachable nodes through dependency edges.

        Args:
            project_id: The project to analyze
            max_depth: Maximum traversal depth

        Returns:
            ImpactReport with affected projects, teams, and paths

        Raises:
            ValueError: If project not found in graph
        """
        project_node_id = f"project:{project_id}"
        if project_node_id not in self.graph.nodes:
            raise ValueError(f"Project {project_id} not found in graph")

        affected_projects: Set[str] = set()
        affected_teams: Set[str] = set()
        critical_projects: List[str] = []
        paths: List[List[str]] = []

        # BFS traversal
        visited: Set[str] = set()
        queue: deque = deque([(project_node_id, [project_id], 0)])

        while queue:
            current_id, path, depth = queue.popleft()

            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            current_node = self.graph.get_node(current_id)
            if not current_node:
                continue

            # Track affected entities
            if current_node.type == NodeType.PROJECT and current_id != project_node_id:
                project_name = current_node.name
                affected_projects.add(project_name)
                paths.append(path)

                if current_node.attributes.get("criticality") == "critical":
                    critical_projects.append(project_name)

            if current_node.type == NodeType.TEAM:
                affected_teams.add(current_node.name)

            # Traverse outgoing edges
            for edge in self.graph.get_edges_from(current_id):
                if edge.type in [EdgeType.DEPENDS_ON, EdgeType.MANAGES]:
                    target_node = self.graph.get_node(edge.target_id)
                    if target_node and target_node.type == NodeType.PROJECT:
                        queue.append(
                            (edge.target_id, path + [target_node.name], depth + 1)
                        )

                # Also traverse to teams
                if edge.type == EdgeType.OWNED_BY:
                    target_node = self.graph.get_node(edge.target_id)
                    if target_node and target_node.type == NodeType.TEAM:
                        affected_teams.add(target_node.name)

            # Traverse reverse edges (who depends on this)
            for edge in self.graph.get_edges_to(current_id):
                if edge.type == EdgeType.DEPENDS_ON:
                    source_node = self.graph.get_node(edge.source_id)
                    if source_node and source_node.type == NodeType.PROJECT:
                        queue.append(
                            (edge.source_id, path + [source_node.name], depth + 1)
                        )

        return ImpactReport(
            source_project=project_id,
            affected_projects=list(affected_projects),
            affected_teams=list(affected_teams),
            critical_projects=critical_projects,
            total_blast_radius=len(affected_projects),
            dependency_paths=paths,
        )

    def get_dependencies(self, project_id: str) -> DependencyReport:
        """Get upstream and downstream dependencies for a project.

        Args:
            project_id: The project to analyze

        Returns:
            DependencyReport with upstream, downstream, and shared resources
        """
        project_node_id = f"project:{project_id}"

        upstream: Set[str] = set()
        downstream: Set[str] = set()
        shared_resources: Set[str] = set()
        shared_adrs: Set[str] = set()

        # Find edges from this project
        for edge in self.graph.get_edges_from(project_node_id):
            target = self.graph.get_node(edge.target_id)
            if not target:
                continue

            if edge.type == EdgeType.DEPENDS_ON and target.type == NodeType.PROJECT:
                upstream.add(target.name)

            if edge.type == EdgeType.MANAGES and target.type == NodeType.RESOURCE:
                shared_resources.add(target.name)

            if edge.type == EdgeType.IMPLEMENTS and target.type == NodeType.ADR:
                shared_adrs.add(target.name)

        # Find edges to this project
        for edge in self.graph.get_edges_to(project_node_id):
            source = self.graph.get_node(edge.source_id)
            if source and edge.type == EdgeType.DEPENDS_ON and source.type == NodeType.PROJECT:
                downstream.add(source.name)

        return DependencyReport(
            project_id=project_id,
            upstream=list(upstream),
            downstream=list(downstream),
            shared_resources=list(shared_resources),
            shared_adrs=list(shared_adrs),
        )

    def find_path(self, from_project: str, to_project: str) -> Optional[List[str]]:
        """Find shortest path between two projects.

        Args:
            from_project: Source project ID
            to_project: Target project ID

        Returns:
            List of project names in the path, or None if no path exists
        """
        start = f"project:{from_project}"
        end = f"project:{to_project}"

        if start not in self.graph.nodes or end not in self.graph.nodes:
            return None

        # BFS for shortest path
        visited: Set[str] = set()
        queue: deque = deque([(start, [from_project])])

        while queue:
            current, path = queue.popleft()

            if current == end:
                return path

            if current in visited:
                continue
            visited.add(current)

            # Traverse both directions for path finding
            for edge in self.graph.get_edges_from(current):
                target = self.graph.get_node(edge.target_id)
                if target and target.type == NodeType.PROJECT:
                    queue.append((edge.target_id, path + [target.name]))

            for edge in self.graph.get_edges_to(current):
                source = self.graph.get_node(edge.source_id)
                if source and source.type == NodeType.PROJECT:
                    queue.append((edge.source_id, path + [source.name]))

        return None

    def get_risk_exposure(self, team: str) -> Dict[str, int]:
        """Get risk exposure summary for a team's projects.

        Args:
            team: Team name to analyze

        Returns:
            Dictionary mapping risk types to counts
        """
        team_node_id = f"team:{team}"

        # Find all projects owned by team
        project_ids = []
        for edge in self.graph.get_edges_to(team_node_id):
            if edge.type == EdgeType.OWNED_BY:
                project_ids.append(edge.source_id)

        # Aggregate risks
        risk_counts: Dict[str, int] = {}
        for project_id in project_ids:
            for edge in self.graph.get_edges_from(project_id):
                if edge.type == EdgeType.HAS_RISK:
                    risk_node = self.graph.get_node(edge.target_id)
                    if risk_node:
                        risk_type = risk_node.attributes.get("type", "unknown")
                        risk_counts[risk_type] = risk_counts.get(risk_type, 0) + 1

        return risk_counts

    def get_projects_by_team(self, team: str) -> List[str]:
        """Get all projects owned by a team.

        Args:
            team: Team name

        Returns:
            List of project names
        """
        team_node_id = f"team:{team}"
        projects = []

        for edge in self.graph.get_edges_to(team_node_id):
            if edge.type == EdgeType.OWNED_BY:
                node = self.graph.get_node(edge.source_id)
                if node and node.type == NodeType.PROJECT:
                    projects.append(node.name)

        return projects

    def get_projects_by_criticality(self, criticality: str) -> List[str]:
        """Get all projects with a specific criticality.

        Args:
            criticality: Criticality level (critical, high, medium, low)

        Returns:
            List of project names
        """
        return [
            node.name
            for node in self.graph.nodes.values()
            if node.type == NodeType.PROJECT
            and node.attributes.get("criticality") == criticality
        ]

    def to_visualization_format(self) -> Dict[str, Any]:
        """Export graph in format suitable for visualization libraries.

        Returns:
            Dictionary with 'nodes' and 'links' arrays compatible with D3.js/vis.js
        """
        return {
            "nodes": [
                {
                    "id": node.id,
                    "label": node.name,
                    "group": node.type.value,
                    **node.attributes,
                }
                for node in self.graph.nodes.values()
            ],
            "links": [
                {
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "type": edge.type.value,
                    "value": edge.weight,
                }
                for edge in self.graph.edges
            ],
        }
