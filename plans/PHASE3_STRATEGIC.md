# Phase 3: Strategic Implementation Plan

**Estimated Effort**: Weeks per feature
**Total Phase Duration**: 1-2 months
**Dependencies**: Phase 1 & 2 complete, significant new infrastructure

---

## Overview

Phase 3 focuses on strategic capabilities that transform ContextCore from a metadata store into an intelligent platform. These features require substantial investment but deliver transformative value: enabling cross-project intelligence, developer-native experiences, and continuous learning.

---

## Feature 3.1: Project Knowledge Graph

**Effort**: 2-3 weeks
**Architecture Impact**: New data model, query API, visualization layer

### Goal

Build a queryable knowledge graph from ProjectContext relationships, enabling impact analysis, dependency visualization, and cross-project intelligence.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Knowledge Graph System                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐      │
│  │ Graph Builder│───▶│  Graph Store │───▶│ Query API (GraphQL)  │      │
│  │              │    │  (Neo4j/     │    │                      │      │
│  │ - Watch CRDs │    │   In-memory) │    │ - Impact analysis    │      │
│  │ - Extract    │    │              │    │ - Dependency queries │      │
│  │   relations  │    │ Nodes:       │    │ - Path finding       │      │
│  │ - Build edges│    │ - Projects   │    │                      │      │
│  └──────────────┘    │ - Resources  │    └──────────────────────┘      │
│                      │ - Teams      │               │                   │
│                      │ - ADRs       │               ▼                   │
│                      │              │    ┌──────────────────────┐      │
│                      │ Edges:       │    │ Grafana Plugin       │      │
│                      │ - manages    │    │ (Graph Visualization)│      │
│                      │ - depends_on │    └──────────────────────┘      │
│                      │ - owned_by   │                                   │
│                      │ - implements │                                   │
│                      └──────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation Steps

#### Step 1: Define Graph Schema

```python
# src/contextcore/graph/schema.py
"""Knowledge graph schema definitions."""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


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
    MANAGES = "manages"           # Project → Resource
    DEPENDS_ON = "depends_on"     # Project → Project (inferred from targets)
    OWNED_BY = "owned_by"         # Project → Team
    IMPLEMENTS = "implements"     # Project → ADR
    EXPOSES = "exposes"          # Project → Contract
    HAS_RISK = "has_risk"        # Project → Risk
    HAS_REQUIREMENT = "has_requirement"  # Project → Requirement
    GENERATED = "generated"      # Project → Insight
    CALLS = "calls"              # Resource → Resource (from traces)


@dataclass
class Node:
    """A node in the knowledge graph."""
    id: str
    type: NodeType
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
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
    """An edge (relationship) in the knowledge graph."""
    source_id: str
    target_id: str
    type: EdgeType
    attributes: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0  # For weighted graph algorithms

    def to_dict(self) -> Dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.type.value,
            "attributes": self.attributes,
            "weight": self.weight,
        }


@dataclass
class Graph:
    """The complete knowledge graph."""
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.source_id == node_id]

    def get_edges_to(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.target_id == node_id]

    def to_dict(self) -> Dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }
```

#### Step 2: Build Graph from ProjectContexts

```python
# src/contextcore/graph/builder.py
"""Build knowledge graph from ProjectContext CRDs."""

from typing import List, Dict, Any, Optional
from kubernetes import client, config, watch
import hashlib

from contextcore.graph.schema import (
    Graph, Node, Edge, NodeType, EdgeType
)


class GraphBuilder:
    """Builds and maintains knowledge graph from ProjectContexts."""

    def __init__(self):
        self.graph = Graph()
        self._resource_to_project: Dict[str, List[str]] = {}

    def build_from_contexts(self, contexts: List[Dict]) -> Graph:
        """Build complete graph from list of ProjectContexts."""
        self.graph = Graph()
        self._resource_to_project = {}

        for ctx in contexts:
            self._process_context(ctx)

        # Infer dependencies after all contexts processed
        self._infer_dependencies()

        return self.graph

    def _process_context(self, ctx: Dict) -> None:
        """Process a single ProjectContext into graph nodes and edges."""
        metadata = ctx.get("metadata", {})
        spec = ctx.get("spec", {})

        project_id = self._get_project_id(spec, metadata.get("name", "unknown"))
        namespace = metadata.get("namespace", "default")

        # Create project node
        project_node = Node(
            id=f"project:{project_id}",
            type=NodeType.PROJECT,
            name=project_id,
            attributes={
                "namespace": namespace,
                "criticality": spec.get("business", {}).get("criticality"),
                "value": spec.get("business", {}).get("value"),
                "epic": spec.get("project", {}).get("epic") if isinstance(spec.get("project"), dict) else None,
            }
        )
        self.graph.add_node(project_node)

        # Process business context → Team node
        business = spec.get("business", {})
        if business.get("owner"):
            team_node = Node(
                id=f"team:{business['owner']}",
                type=NodeType.TEAM,
                name=business["owner"],
                attributes={"cost_center": business.get("costCenter")},
            )
            self.graph.add_node(team_node)
            self.graph.add_edge(Edge(
                source_id=project_node.id,
                target_id=team_node.id,
                type=EdgeType.OWNED_BY,
            ))

        # Process targets → Resource nodes
        for target in spec.get("targets", []):
            resource_id = self._make_resource_id(target, namespace)
            resource_node = Node(
                id=resource_id,
                type=NodeType.RESOURCE,
                name=target.get("name", "unknown"),
                attributes={
                    "kind": target.get("kind"),
                    "namespace": target.get("namespace", namespace),
                },
            )
            self.graph.add_node(resource_node)
            self.graph.add_edge(Edge(
                source_id=project_node.id,
                target_id=resource_id,
                type=EdgeType.MANAGES,
            ))

            # Track resource → project mapping for dependency inference
            if resource_id not in self._resource_to_project:
                self._resource_to_project[resource_id] = []
            self._resource_to_project[resource_id].append(project_node.id)

        # Process design → ADR and Contract nodes
        design = spec.get("design", {})
        if design.get("adr"):
            adr_node = Node(
                id=f"adr:{design['adr']}",
                type=NodeType.ADR,
                name=design["adr"],
                attributes={"url": design.get("doc")},
            )
            self.graph.add_node(adr_node)
            self.graph.add_edge(Edge(
                source_id=project_node.id,
                target_id=adr_node.id,
                type=EdgeType.IMPLEMENTS,
            ))

        if design.get("apiContract"):
            contract_node = Node(
                id=f"contract:{self._hash_url(design['apiContract'])}",
                type=NodeType.CONTRACT,
                name=design["apiContract"],
                attributes={"url": design["apiContract"]},
            )
            self.graph.add_node(contract_node)
            self.graph.add_edge(Edge(
                source_id=project_node.id,
                target_id=contract_node.id,
                type=EdgeType.EXPOSES,
            ))

        # Process risks → Risk nodes
        for i, risk in enumerate(spec.get("risks", [])):
            risk_id = f"risk:{project_id}:{i}"
            risk_node = Node(
                id=risk_id,
                type=NodeType.RISK,
                name=f"{risk.get('type', 'unknown')} risk",
                attributes={
                    "type": risk.get("type"),
                    "priority": risk.get("priority"),
                    "description": risk.get("description"),
                },
            )
            self.graph.add_node(risk_node)
            self.graph.add_edge(Edge(
                source_id=project_node.id,
                target_id=risk_id,
                type=EdgeType.HAS_RISK,
                weight=self._risk_weight(risk.get("priority")),
            ))

    def _infer_dependencies(self) -> None:
        """Infer project-to-project dependencies from shared resources."""
        # TODO: Enhance with trace data for actual call dependencies

        # For now, infer from Service targets - if project A has a Service
        # and project B targets that Service, B depends on A
        service_nodes = [
            n for n in self.graph.nodes.values()
            if n.type == NodeType.RESOURCE and n.attributes.get("kind") == "Service"
        ]

        for service in service_nodes:
            managing_projects = self._resource_to_project.get(service.id, [])
            # This is simplistic - real implementation would use trace data
            # to find actual callers

    def _get_project_id(self, spec: Dict, default: str) -> str:
        project = spec.get("project", {})
        if isinstance(project, dict):
            return project.get("id", default)
        return project or default

    def _make_resource_id(self, target: Dict, default_ns: str) -> str:
        kind = target.get("kind", "Unknown")
        name = target.get("name", "unknown")
        ns = target.get("namespace", default_ns)
        return f"resource:{ns}/{kind}/{name}"

    def _hash_url(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _risk_weight(self, priority: Optional[str]) -> float:
        weights = {"P1": 4.0, "P2": 3.0, "P3": 2.0, "P4": 1.0}
        return weights.get(priority, 1.0)


class GraphWatcher:
    """Watch ProjectContext changes and update graph in real-time."""

    def __init__(self, builder: GraphBuilder):
        self.builder = builder
        self._running = False

    def start(self) -> None:
        """Start watching ProjectContext changes."""
        config.load_incluster_config()
        api = client.CustomObjectsApi()

        self._running = True
        w = watch.Watch()

        for event in w.stream(
            api.list_cluster_custom_object,
            group="contextcore.io",
            version="v1",
            plural="projectcontexts",
        ):
            if not self._running:
                break

            event_type = event["type"]
            obj = event["object"]

            if event_type in ["ADDED", "MODIFIED"]:
                self.builder._process_context(obj)
            elif event_type == "DELETED":
                self._remove_context(obj)

    def stop(self) -> None:
        self._running = False

    def _remove_context(self, ctx: Dict) -> None:
        """Remove a context from the graph."""
        # Implementation: remove project node and all connected edges
        pass
```

#### Step 3: Impact Analysis & Queries

```python
# src/contextcore/graph/queries.py
"""Query operations on the knowledge graph."""

from dataclasses import dataclass
from typing import List, Set, Dict, Optional
from collections import deque

from contextcore.graph.schema import Graph, Node, Edge, NodeType, EdgeType


@dataclass
class ImpactReport:
    """Report of impact from a change."""
    source_project: str
    affected_projects: List[str]
    affected_teams: List[str]
    critical_projects: List[str]  # Criticality = critical
    total_blast_radius: int
    dependency_paths: List[List[str]]  # Paths showing how impact propagates


@dataclass
class DependencyReport:
    """Report of project dependencies."""
    project_id: str
    upstream: List[str]    # Projects this depends on
    downstream: List[str]  # Projects that depend on this
    shared_resources: List[str]
    shared_adrs: List[str]


class GraphQueries:
    """Query operations on the knowledge graph."""

    def __init__(self, graph: Graph):
        self.graph = graph

    def impact_analysis(self, project_id: str, max_depth: int = 5) -> ImpactReport:
        """
        Analyze impact of changes to a project.

        Uses BFS to find all reachable nodes through dependency edges.
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

            # Traverse edges
            for edge in self.graph.get_edges_from(current_id):
                if edge.type in [EdgeType.DEPENDS_ON, EdgeType.MANAGES]:
                    target_node = self.graph.get_node(edge.target_id)
                    if target_node and target_node.type == NodeType.PROJECT:
                        queue.append((
                            edge.target_id,
                            path + [target_node.name],
                            depth + 1
                        ))

            # Also traverse reverse edges (who depends on this)
            for edge in self.graph.get_edges_to(current_id):
                if edge.type == EdgeType.DEPENDS_ON:
                    source_node = self.graph.get_node(edge.source_id)
                    if source_node and source_node.type == NodeType.PROJECT:
                        queue.append((
                            edge.source_id,
                            path + [source_node.name],
                            depth + 1
                        ))

        return ImpactReport(
            source_project=project_id,
            affected_projects=list(affected_projects),
            affected_teams=list(affected_teams),
            critical_projects=critical_projects,
            total_blast_radius=len(affected_projects),
            dependency_paths=paths,
        )

    def get_dependencies(self, project_id: str) -> DependencyReport:
        """Get upstream and downstream dependencies for a project."""
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
        """Find shortest path between two projects."""
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
        """Get risk exposure summary for a team's projects."""
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

    def to_visualization_format(self) -> Dict:
        """Export graph in format suitable for visualization libraries."""
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
```

#### Step 4: CLI Commands

```python
# In cli.py, add graph group:

@cli.group()
def graph():
    """Knowledge graph commands."""
    pass

@graph.command("build")
@click.option("--output", "-o", type=click.Path(), help="Output JSON file")
def graph_build_cmd(output: str):
    """Build knowledge graph from all ProjectContexts."""
    from contextcore.graph.builder import GraphBuilder

    contexts = list_all_project_contexts()
    builder = GraphBuilder()
    g = builder.build_from_contexts(contexts)

    click.echo(f"Built graph with {len(g.nodes)} nodes and {len(g.edges)} edges")

    if output:
        import json
        with open(output, "w") as f:
            json.dump(g.to_dict(), f, indent=2)
        click.echo(f"Graph exported to {output}")

@graph.command("impact")
@click.option("--project", "-p", required=True, help="Project to analyze")
@click.option("--depth", "-d", default=3, help="Max traversal depth")
def graph_impact_cmd(project: str, depth: int):
    """Analyze impact of changes to a project."""
    from contextcore.graph.builder import GraphBuilder
    from contextcore.graph.queries import GraphQueries

    contexts = list_all_project_contexts()
    builder = GraphBuilder()
    g = builder.build_from_contexts(contexts)
    queries = GraphQueries(g)

    report = queries.impact_analysis(project, max_depth=depth)

    click.echo(f"Impact Analysis: {project}")
    click.echo(f"  Affected Projects: {len(report.affected_projects)}")
    click.echo(f"  Critical Projects: {len(report.critical_projects)}")
    click.echo(f"  Affected Teams: {len(report.affected_teams)}")
    click.echo(f"  Blast Radius: {report.total_blast_radius}")

    if report.critical_projects:
        click.echo(f"\n  ⚠️ Critical projects affected: {', '.join(report.critical_projects)}")

@graph.command("deps")
@click.option("--project", "-p", required=True, help="Project to query")
def graph_deps_cmd(project: str):
    """Show dependencies for a project."""
    from contextcore.graph.builder import GraphBuilder
    from contextcore.graph.queries import GraphQueries

    contexts = list_all_project_contexts()
    builder = GraphBuilder()
    g = builder.build_from_contexts(contexts)
    queries = GraphQueries(g)

    deps = queries.get_dependencies(project)

    click.echo(f"Dependencies: {project}")
    click.echo(f"  Upstream (depends on): {', '.join(deps.upstream) or 'none'}")
    click.echo(f"  Downstream (depended by): {', '.join(deps.downstream) or 'none'}")
    click.echo(f"  Shared Resources: {', '.join(deps.shared_resources) or 'none'}")
    click.echo(f"  Shared ADRs: {', '.join(deps.shared_adrs) or 'none'}")
```

### Acceptance Criteria

- [ ] `contextcore graph build` creates graph from all ProjectContexts
- [ ] `contextcore graph impact --project <id>` shows affected projects
- [ ] `contextcore graph deps --project <id>` shows upstream/downstream
- [ ] Graph includes team ownership relationships
- [ ] Graph includes ADR implementation relationships
- [ ] Critical projects highlighted in impact analysis
- [ ] Export format compatible with D3.js/vis.js visualization

---

## Feature 3.2: IDE Integration (VSCode Extension)

**Effort**: 2-3 weeks
**New Repository**: `contextcore-vscode`

### Goal

Create a VSCode extension that surfaces ProjectContext information directly in the development environment, providing real-time awareness of requirements, risks, and constraints.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     ContextCore VSCode Extension                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐      │
│  │ File Watcher │───▶│Context Mapper│───▶│ Decoration Provider  │      │
│  │              │    │              │    │                      │      │
│  │ - Detect     │    │ - Map file   │    │ - Inline hints       │      │
│  │   workspace  │    │   to project │    │ - CodeLens           │      │
│  │   files      │    │ - Load spec  │    │ - Gutter icons       │      │
│  └──────────────┘    └──────────────┘    └──────────────────────┘      │
│                                                     │                   │
│  ┌──────────────┐                                   │                   │
│  │ K8s Client   │◀──────────────────────────────────┘                   │
│  │              │                                                        │
│  │ - Fetch CRDs │    ┌──────────────────────────────────────────┐      │
│  │ - Watch      │    │               UI Components               │      │
│  │   changes    │    │                                          │      │
│  └──────────────┘    │ - Status Bar (criticality badge)         │      │
│                      │ - Side Panel (full context view)         │      │
│                      │ - Hover cards (requirement details)      │      │
│                      │ - Problem matcher (constraint violations)│      │
│                      └──────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation Steps

#### Step 1: Extension Manifest

```json
// package.json
{
  "name": "contextcore-vscode",
  "displayName": "ContextCore",
  "description": "ProjectContext awareness in your editor",
  "version": "0.1.0",
  "engines": {
    "vscode": "^1.85.0"
  },
  "categories": ["Other"],
  "activationEvents": [
    "workspaceContains:**/projectcontext.yaml",
    "workspaceContains:**/.contextcore"
  ],
  "main": "./out/extension.js",
  "contributes": {
    "configuration": {
      "title": "ContextCore",
      "properties": {
        "contextcore.kubeconfig": {
          "type": "string",
          "description": "Path to kubeconfig file"
        },
        "contextcore.namespace": {
          "type": "string",
          "default": "default",
          "description": "Kubernetes namespace for ProjectContexts"
        },
        "contextcore.showInlineHints": {
          "type": "boolean",
          "default": true,
          "description": "Show inline requirement hints"
        }
      }
    },
    "viewsContainers": {
      "activitybar": [
        {
          "id": "contextcore",
          "title": "ContextCore",
          "icon": "resources/contextcore.svg"
        }
      ]
    },
    "views": {
      "contextcore": [
        {
          "id": "contextcore.projectView",
          "name": "Project Context"
        },
        {
          "id": "contextcore.risksView",
          "name": "Risks"
        },
        {
          "id": "contextcore.requirementsView",
          "name": "Requirements"
        }
      ]
    },
    "commands": [
      {
        "command": "contextcore.refresh",
        "title": "Refresh Context",
        "category": "ContextCore"
      },
      {
        "command": "contextcore.showImpact",
        "title": "Show Impact Analysis",
        "category": "ContextCore"
      }
    ]
  }
}
```

#### Step 2: Context Detection & Mapping

```typescript
// src/contextMapper.ts
import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as yaml from 'yaml';

interface ProjectContext {
  projectId: string;
  namespace: string;
  spec: ProjectContextSpec;
  source: 'local' | 'kubernetes';
}

interface ProjectContextSpec {
  project: { id: string; epic?: string };
  business?: {
    criticality?: string;
    value?: string;
    owner?: string;
  };
  requirements?: {
    availability?: string;
    latencyP99?: string;
    latencyP50?: string;
    throughput?: string;
  };
  risks?: Array<{
    type: string;
    description: string;
    priority: string;
    scope?: string;
  }>;
  targets?: Array<{
    kind: string;
    name: string;
  }>;
}

export class ContextMapper {
  private contexts: Map<string, ProjectContext> = new Map();
  private fileToProject: Map<string, string> = new Map();

  async initialize(workspaceRoot: string): Promise<void> {
    // Load local .contextcore file if exists
    const localConfigPath = path.join(workspaceRoot, '.contextcore');
    if (fs.existsSync(localConfigPath)) {
      await this.loadLocalConfig(localConfigPath);
    }

    // Load from kubernetes if available
    await this.loadFromKubernetes();

    // Build file-to-project mapping
    this.buildFileMapping(workspaceRoot);
  }

  private async loadLocalConfig(configPath: string): Promise<void> {
    const content = fs.readFileSync(configPath, 'utf-8');
    const config = yaml.parse(content);

    if (config.projectId) {
      // Fetch from kubernetes using project ID
      const ctx = await this.fetchContext(config.projectId, config.namespace);
      if (ctx) {
        this.contexts.set(config.projectId, ctx);
      }
    }
  }

  private buildFileMapping(workspaceRoot: string): void {
    // Map files to projects based on:
    // 1. .contextcore local config
    // 2. Risk scope patterns
    // 3. Target resource names

    for (const [projectId, ctx] of this.contexts) {
      // Map by risk scope patterns
      for (const risk of ctx.spec.risks || []) {
        if (risk.scope) {
          // e.g., scope: "src/auth/**"
          this.fileToProject.set(risk.scope, projectId);
        }
      }
    }
  }

  getContextForFile(filePath: string): ProjectContext | undefined {
    // Check exact matches first
    for (const [pattern, projectId] of this.fileToProject) {
      if (this.matchesPattern(filePath, pattern)) {
        return this.contexts.get(projectId);
      }
    }

    // Default to first context (single-project workspace)
    if (this.contexts.size === 1) {
      return this.contexts.values().next().value;
    }

    return undefined;
  }

  private matchesPattern(filePath: string, pattern: string): boolean {
    // Simple glob matching
    const regex = pattern
      .replace(/\*\*/g, '.*')
      .replace(/\*/g, '[^/]*');
    return new RegExp(regex).test(filePath);
  }

  // ... kubernetes client methods
}
```

#### Step 3: Inline Decorations

```typescript
// src/decorationProvider.ts
import * as vscode from 'vscode';
import { ContextMapper, ProjectContext } from './contextMapper';

export class ContextDecorationProvider {
  private criticalDecorationType: vscode.TextEditorDecorationType;
  private requirementDecorationType: vscode.TextEditorDecorationType;

  constructor(private contextMapper: ContextMapper) {
    this.criticalDecorationType = vscode.window.createTextEditorDecorationType({
      gutterIconPath: 'resources/critical.svg',
      gutterIconSize: '80%',
    });

    this.requirementDecorationType = vscode.window.createTextEditorDecorationType({
      after: {
        color: new vscode.ThemeColor('editorCodeLens.foreground'),
        fontStyle: 'italic',
        margin: '0 0 0 1em',
      },
    });
  }

  updateDecorations(editor: vscode.TextEditor): void {
    const context = this.contextMapper.getContextForFile(editor.document.uri.fsPath);
    if (!context) {
      return;
    }

    const decorations: vscode.DecorationOptions[] = [];

    // Add requirement hints
    if (context.spec.requirements) {
      const req = context.spec.requirements;

      // Find relevant code patterns and add hints
      const text = editor.document.getText();

      // Example: Add latency hint near HTTP handlers
      const httpHandlerRegex = /def\s+(get|post|put|delete|handle)/gi;
      let match;
      while ((match = httpHandlerRegex.exec(text)) !== null) {
        const position = editor.document.positionAt(match.index);
        const line = editor.document.lineAt(position.line);

        if (req.latencyP99) {
          decorations.push({
            range: line.range,
            renderOptions: {
              after: {
                contentText: `  // SLO: P99 < ${req.latencyP99}`,
              },
            },
          });
        }
      }
    }

    editor.setDecorations(this.requirementDecorationType, decorations);
  }
}
```

#### Step 4: Status Bar & Side Panel

```typescript
// src/statusBar.ts
import * as vscode from 'vscode';
import { ContextMapper, ProjectContext } from './contextMapper';

export class ContextStatusBar {
  private statusBarItem: vscode.StatusBarItem;

  constructor(private contextMapper: ContextMapper) {
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.statusBarItem.command = 'contextcore.showDetails';
  }

  update(editor: vscode.TextEditor | undefined): void {
    if (!editor) {
      this.statusBarItem.hide();
      return;
    }

    const context = this.contextMapper.getContextForFile(editor.document.uri.fsPath);
    if (!context) {
      this.statusBarItem.text = '$(info) No Context';
      this.statusBarItem.tooltip = 'No ProjectContext found for this file';
      this.statusBarItem.show();
      return;
    }

    const criticality = context.spec.business?.criticality || 'unknown';
    const icon = this.getCriticalityIcon(criticality);
    const riskCount = context.spec.risks?.length || 0;

    this.statusBarItem.text = `${icon} ${context.projectId}`;
    this.statusBarItem.tooltip = new vscode.MarkdownString(
      `**Project**: ${context.projectId}\n\n` +
      `**Criticality**: ${criticality}\n\n` +
      `**Risks**: ${riskCount}\n\n` +
      `Click for details`
    );
    this.statusBarItem.backgroundColor = this.getCriticalityColor(criticality);
    this.statusBarItem.show();
  }

  private getCriticalityIcon(criticality: string): string {
    const icons: Record<string, string> = {
      critical: '$(flame)',
      high: '$(warning)',
      medium: '$(info)',
      low: '$(check)',
    };
    return icons[criticality] || '$(question)';
  }

  private getCriticalityColor(criticality: string): vscode.ThemeColor | undefined {
    if (criticality === 'critical') {
      return new vscode.ThemeColor('statusBarItem.errorBackground');
    }
    if (criticality === 'high') {
      return new vscode.ThemeColor('statusBarItem.warningBackground');
    }
    return undefined;
  }

  dispose(): void {
    this.statusBarItem.dispose();
  }
}
```

### Acceptance Criteria

- [ ] Extension activates when .contextcore file present
- [ ] Status bar shows project criticality
- [ ] Side panel shows full ProjectContext details
- [ ] Inline hints show SLO requirements near relevant code
- [ ] Gutter icons indicate files in risk scope
- [ ] Hover cards show requirement details
- [ ] Works with both local and kubernetes-sourced contexts

---

## Feature 3.3: Agent Learning Loop

**Effort**: 2-3 weeks
**Files to Create**:
- `src/contextcore/learning/lesson_store.py`
- `src/contextcore/learning/lesson_retriever.py`
- `src/contextcore/learning/lesson_emitter.py`

### Goal

Enable agents to learn from past work by storing lessons as insights and retrieving relevant lessons before starting new work, creating a continuous improvement loop.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Agent Learning Loop                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     Agent Work Session                          │    │
│  │                                                                  │    │
│  │  1. Before Task ─────────────────┐                              │    │
│  │     │                            │                              │    │
│  │     ▼                            ▼                              │    │
│  │  ┌──────────────┐    ┌──────────────────┐                       │    │
│  │  │Query Lessons │    │ Apply to Work    │                       │    │
│  │  │ - By file    │───▶│ - Avoid mistakes │                       │    │
│  │  │ - By task    │    │ - Use patterns   │                       │    │
│  │  │ - By error   │    │ - Follow advice  │                       │    │
│  │  └──────────────┘    └──────────────────┘                       │    │
│  │                                                                  │    │
│  │  2. During Task ────────────────────────────────────────────────│    │
│  │     │                                                            │    │
│  │     ▼                                                            │    │
│  │  ┌──────────────────────────────────────────────────────────┐   │    │
│  │  │ Work + Encounter Issues + Solve Problems                 │   │    │
│  │  └──────────────────────────────────────────────────────────┘   │    │
│  │                                                                  │    │
│  │  3. After Task ─────────────────┐                               │    │
│  │     │                           │                               │    │
│  │     ▼                           ▼                               │    │
│  │  ┌──────────────┐    ┌──────────────────┐                       │    │
│  │  │Emit Lessons  │    │ Store in Tempo   │                       │    │
│  │  │ - Blockers   │───▶│ as OTel spans    │                       │    │
│  │  │ - Solutions  │    │ with attributes  │                       │    │
│  │  │ - Patterns   │    │                  │                       │    │
│  │  └──────────────┘    └──────────────────┘                       │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│                              ▲         │                                 │
│                              │         │                                 │
│                    ┌─────────┴─────────┴─────────┐                      │
│                    │     Tempo (Lesson Store)    │                      │
│                    │                             │                      │
│                    │  TraceQL queries:           │                      │
│                    │  - insight.type="lesson"    │                      │
│                    │  - insight.applies_to=~"*"  │                      │
│                    │  - insight.category="X"     │                      │
│                    └─────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation Steps

#### Step 1: Lesson Data Model

```python
# src/contextcore/learning/models.py
"""Data models for agent learning system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class LessonCategory(Enum):
    """Categories for organizing lessons."""
    ARCHITECTURE = "architecture"
    TESTING = "testing"
    DEBUGGING = "debugging"
    PERFORMANCE = "performance"
    SECURITY = "security"
    DEPLOYMENT = "deployment"
    DOCUMENTATION = "documentation"
    REFACTORING = "refactoring"
    ERROR_HANDLING = "error_handling"
    INTEGRATION = "integration"


class LessonSource(Enum):
    """How the lesson was learned."""
    BLOCKER_RESOLVED = "blocker_resolved"
    ERROR_FIXED = "error_fixed"
    PATTERN_DISCOVERED = "pattern_discovered"
    REVIEW_FEEDBACK = "review_feedback"
    HUMAN_GUIDANCE = "human_guidance"
    DOCUMENTATION = "documentation"


@dataclass
class Lesson:
    """A single lesson learned by an agent."""
    id: str
    summary: str
    category: LessonCategory
    source: LessonSource

    # Where this lesson applies
    applies_to: List[str]  # File patterns, e.g., ["src/auth/**", "*.test.py"]
    project_id: Optional[str]  # Specific project, or None for global

    # Confidence and validation
    confidence: float  # 0.0-1.0
    validated_by_human: bool = False
    success_count: int = 0  # Times applied successfully
    failure_count: int = 0  # Times didn't help

    # Context
    context: str = ""  # Extended description/explanation
    code_example: Optional[str] = None
    anti_pattern: Optional[str] = None  # What NOT to do

    # Metadata
    agent_id: str = ""
    trace_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

    @property
    def effectiveness_score(self) -> float:
        """Calculate lesson effectiveness based on usage."""
        total = self.success_count + self.failure_count
        if total == 0:
            return self.confidence
        return (self.success_count / total) * self.confidence


@dataclass
class LessonQuery:
    """Query parameters for retrieving lessons."""
    project_id: Optional[str] = None
    file_pattern: Optional[str] = None
    category: Optional[LessonCategory] = None
    min_confidence: float = 0.5
    include_global: bool = True
    max_results: int = 10
    time_range: str = "30d"  # e.g., "1h", "7d", "30d"


@dataclass
class LessonApplication:
    """Record of applying a lesson."""
    lesson_id: str
    applied_at: datetime
    context: str  # Where/how it was applied
    success: bool
    feedback: Optional[str] = None
```

#### Step 2: Lesson Emitter (Store)

```python
# src/contextcore/learning/emitter.py
"""Emit lessons as OpenTelemetry spans for storage in Tempo."""

from typing import List, Optional
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.trace import SpanKind

from contextcore.learning.models import (
    Lesson, LessonCategory, LessonSource, LessonApplication
)


class LessonEmitter:
    """Emit lessons as OTel spans for storage and retrieval."""

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        session_id: Optional[str] = None
    ):
        self.project_id = project_id
        self.agent_id = agent_id
        self.session_id = session_id or f"session-{datetime.now().timestamp()}"
        self._tracer = trace.get_tracer("contextcore.learning")

    def emit_lesson(
        self,
        summary: str,
        category: LessonCategory,
        source: LessonSource,
        applies_to: List[str],
        confidence: float = 0.8,
        context: str = "",
        code_example: Optional[str] = None,
        anti_pattern: Optional[str] = None,
        global_lesson: bool = False,
    ) -> Lesson:
        """
        Emit a lesson learned during agent work.

        Args:
            summary: Brief description of the lesson (1-2 sentences)
            category: Category for organization/filtering
            source: How this lesson was learned
            applies_to: File patterns where this lesson applies
            confidence: How confident agent is in this lesson
            context: Extended description/explanation
            code_example: Example code demonstrating the lesson
            anti_pattern: Example of what NOT to do
            global_lesson: If True, applies to all projects
        """
        lesson_id = f"lesson-{datetime.now().timestamp()}"

        # Create span with lesson attributes
        with self._tracer.start_as_current_span(
            name="lesson.emit",
            kind=SpanKind.INTERNAL,
        ) as span:
            # Core identification
            span.set_attribute("insight.type", "lesson")
            span.set_attribute("lesson.id", lesson_id)
            span.set_attribute("lesson.summary", summary)

            # Classification
            span.set_attribute("lesson.category", category.value)
            span.set_attribute("lesson.source", source.value)

            # Scope
            span.set_attribute("lesson.applies_to", applies_to)
            if not global_lesson:
                span.set_attribute("project.id", self.project_id)
            span.set_attribute("lesson.is_global", global_lesson)

            # Confidence
            span.set_attribute("lesson.confidence", confidence)

            # Content
            if context:
                span.set_attribute("lesson.context", context)
            if code_example:
                span.set_attribute("lesson.code_example", code_example)
            if anti_pattern:
                span.set_attribute("lesson.anti_pattern", anti_pattern)

            # Agent context
            span.set_attribute("agent.id", self.agent_id)
            span.set_attribute("agent.session_id", self.session_id)

            # Add event for searchability
            span.add_event("lesson_created", attributes={
                "category": category.value,
                "applies_to_count": len(applies_to),
            })

        lesson = Lesson(
            id=lesson_id,
            summary=summary,
            category=category,
            source=source,
            applies_to=applies_to,
            project_id=None if global_lesson else self.project_id,
            confidence=confidence,
            context=context,
            code_example=code_example,
            anti_pattern=anti_pattern,
            agent_id=self.agent_id,
            trace_id=span.get_span_context().trace_id,
        )

        return lesson

    def emit_blocker_resolution(
        self,
        blocker_summary: str,
        resolution: str,
        applies_to: List[str],
        confidence: float = 0.9,
    ) -> Lesson:
        """Convenience method for lessons learned from resolving blockers."""
        return self.emit_lesson(
            summary=f"Resolved: {blocker_summary}",
            category=LessonCategory.DEBUGGING,
            source=LessonSource.BLOCKER_RESOLVED,
            applies_to=applies_to,
            confidence=confidence,
            context=resolution,
        )

    def emit_pattern_discovery(
        self,
        pattern_name: str,
        description: str,
        applies_to: List[str],
        code_example: str,
        anti_pattern: Optional[str] = None,
    ) -> Lesson:
        """Convenience method for pattern discoveries."""
        return self.emit_lesson(
            summary=f"Pattern: {pattern_name}",
            category=LessonCategory.ARCHITECTURE,
            source=LessonSource.PATTERN_DISCOVERED,
            applies_to=applies_to,
            confidence=0.85,
            context=description,
            code_example=code_example,
            anti_pattern=anti_pattern,
        )

    def record_application(
        self,
        lesson_id: str,
        success: bool,
        context: str,
        feedback: Optional[str] = None
    ) -> None:
        """Record that a lesson was applied (for effectiveness tracking)."""
        with self._tracer.start_as_current_span(
            name="lesson.applied",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute("lesson.id", lesson_id)
            span.set_attribute("lesson.applied", True)
            span.set_attribute("lesson.success", success)
            span.set_attribute("lesson.application_context", context)
            if feedback:
                span.set_attribute("lesson.feedback", feedback)
```

#### Step 3: Lesson Retriever (Query)

```python
# src/contextcore/learning/retriever.py
"""Retrieve lessons from Tempo for agent work sessions."""

import json
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.request import Request, urlopen

from contextcore.learning.models import (
    Lesson, LessonQuery, LessonCategory, LessonSource
)


class LessonRetriever:
    """Query lessons from Tempo for agent work sessions."""

    def __init__(self, tempo_url: str = "http://localhost:3200"):
        self.tempo_url = tempo_url.rstrip("/")

    def retrieve(self, query: LessonQuery) -> List[Lesson]:
        """
        Retrieve lessons matching query criteria.

        Args:
            query: Query parameters for filtering lessons

        Returns:
            List of matching lessons, sorted by effectiveness
        """
        # Build TraceQL query
        traceql = self._build_traceql(query)

        # Query Tempo
        raw_results = self._query_tempo(traceql, query.time_range)

        # Parse into Lesson objects
        lessons = self._parse_results(raw_results)

        # Filter by confidence
        lessons = [l for l in lessons if l.confidence >= query.min_confidence]

        # Sort by effectiveness
        lessons.sort(key=lambda l: l.effectiveness_score, reverse=True)

        return lessons[:query.max_results]

    def get_lessons_for_file(
        self,
        file_path: str,
        project_id: Optional[str] = None,
        category: Optional[LessonCategory] = None,
    ) -> List[Lesson]:
        """Get lessons applicable to a specific file."""
        query = LessonQuery(
            project_id=project_id,
            file_pattern=file_path,
            category=category,
            include_global=True,
        )
        return self.retrieve(query)

    def get_lessons_for_task(
        self,
        task_type: str,
        project_id: Optional[str] = None,
    ) -> List[Lesson]:
        """Get lessons applicable to a type of task."""
        # Map task type to likely categories
        category_mapping = {
            "testing": LessonCategory.TESTING,
            "debugging": LessonCategory.DEBUGGING,
            "refactoring": LessonCategory.REFACTORING,
            "security": LessonCategory.SECURITY,
            "performance": LessonCategory.PERFORMANCE,
        }
        category = category_mapping.get(task_type.lower())

        query = LessonQuery(
            project_id=project_id,
            category=category,
            include_global=True,
        )
        return self.retrieve(query)

    def get_global_lessons(
        self,
        category: Optional[LessonCategory] = None,
        min_confidence: float = 0.9,
    ) -> List[Lesson]:
        """Get high-confidence global lessons."""
        query = LessonQuery(
            project_id=None,
            category=category,
            min_confidence=min_confidence,
            include_global=True,
        )
        return self.retrieve(query)

    def _build_traceql(self, query: LessonQuery) -> str:
        """Build TraceQL query from LessonQuery."""
        conditions = ['span.insight.type = "lesson"']

        if query.project_id:
            if query.include_global:
                conditions.append(
                    f'(span.project.id = "{query.project_id}" || span.lesson.is_global = true)'
                )
            else:
                conditions.append(f'span.project.id = "{query.project_id}"')
        elif query.include_global:
            conditions.append('span.lesson.is_global = true')

        if query.category:
            conditions.append(f'span.lesson.category = "{query.category.value}"')

        if query.file_pattern:
            # Use regex matching for file patterns
            conditions.append(f'span.lesson.applies_to =~ ".*{query.file_pattern}.*"')

        return "{ " + " && ".join(conditions) + " }"

    def _query_tempo(self, traceql: str, time_range: str) -> List[dict]:
        """Execute TraceQL query against Tempo."""
        # Parse time range
        duration = self._parse_time_range(time_range)
        start = datetime.now() - duration
        end = datetime.now()

        url = f"{self.tempo_url}/api/search"
        params = {
            "q": traceql,
            "start": int(start.timestamp()),
            "end": int(end.timestamp()),
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query_string}"

        try:
            req = Request(full_url)
            with urlopen(req, timeout=30) as response:
                data = json.loads(response.read())
                return data.get("traces", [])
        except Exception as e:
            print(f"[LessonRetriever] Query failed: {e}")
            return []

    def _parse_results(self, raw_results: List[dict]) -> List[Lesson]:
        """Parse raw Tempo results into Lesson objects."""
        lessons = []

        for trace_data in raw_results:
            for span in trace_data.get("spans", []):
                attrs = span.get("attributes", {})

                if attrs.get("insight.type") != "lesson":
                    continue

                # Parse applies_to (stored as JSON string)
                applies_to_raw = attrs.get("lesson.applies_to", "[]")
                if isinstance(applies_to_raw, str):
                    applies_to = json.loads(applies_to_raw)
                else:
                    applies_to = applies_to_raw

                lesson = Lesson(
                    id=attrs.get("lesson.id", ""),
                    summary=attrs.get("lesson.summary", ""),
                    category=LessonCategory(attrs.get("lesson.category", "debugging")),
                    source=LessonSource(attrs.get("lesson.source", "pattern_discovered")),
                    applies_to=applies_to,
                    project_id=attrs.get("project.id"),
                    confidence=float(attrs.get("lesson.confidence", 0.5)),
                    context=attrs.get("lesson.context", ""),
                    code_example=attrs.get("lesson.code_example"),
                    anti_pattern=attrs.get("lesson.anti_pattern"),
                    agent_id=attrs.get("agent.id", ""),
                    trace_id=trace_data.get("traceId", ""),
                )
                lessons.append(lesson)

        return lessons

    def _parse_time_range(self, time_range: str) -> timedelta:
        """Parse time range string to timedelta."""
        import re
        match = re.match(r"(\d+)([hdwm])", time_range)
        if not match:
            return timedelta(days=7)  # Default

        value = int(match.group(1))
        unit = match.group(2)

        units = {
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
            "w": timedelta(weeks=value),
            "m": timedelta(days=value * 30),
        }
        return units.get(unit, timedelta(days=7))
```

#### Step 4: Learning Loop Integration

```python
# src/contextcore/learning/loop.py
"""Integration point for agent learning loop."""

from typing import List, Optional, Callable
from contextcore.learning.emitter import LessonEmitter
from contextcore.learning.retriever import LessonRetriever
from contextcore.learning.models import Lesson, LessonCategory


class LearningLoop:
    """
    Integrate learning into agent work sessions.

    Usage:
        loop = LearningLoop(project_id="my-project", agent_id="claude-code")

        # Before starting work
        lessons = loop.before_task(
            task_type="testing",
            files=["src/auth/oauth.py"]
        )
        for lesson in lessons:
            print(f"Tip: {lesson.summary}")

        # Do work...

        # After completing work
        if encountered_blocker:
            loop.after_task_blocker(
                blocker="OAuth token refresh failed in tests",
                resolution="Mock the token refresh endpoint in conftest.py",
                affected_files=["tests/conftest.py", "src/auth/oauth.py"]
            )
    """

    def __init__(
        self,
        project_id: str,
        agent_id: str,
        tempo_url: str = "http://localhost:3200",
    ):
        self.project_id = project_id
        self.emitter = LessonEmitter(project_id, agent_id)
        self.retriever = LessonRetriever(tempo_url)

    def before_task(
        self,
        task_type: str,
        files: Optional[List[str]] = None,
        custom_query: Optional[Callable] = None,
    ) -> List[Lesson]:
        """
        Retrieve relevant lessons before starting a task.

        Args:
            task_type: Type of task (testing, debugging, refactoring, etc.)
            files: Files that will be modified
            custom_query: Optional custom query function

        Returns:
            Relevant lessons sorted by effectiveness
        """
        lessons = []

        # Get task-type lessons
        task_lessons = self.retriever.get_lessons_for_task(
            task_type, self.project_id
        )
        lessons.extend(task_lessons)

        # Get file-specific lessons
        if files:
            for file_path in files:
                file_lessons = self.retriever.get_lessons_for_file(
                    file_path, self.project_id
                )
                lessons.extend(file_lessons)

        # Get global lessons
        global_lessons = self.retriever.get_global_lessons(min_confidence=0.9)
        lessons.extend(global_lessons)

        # Deduplicate
        seen_ids = set()
        unique_lessons = []
        for lesson in lessons:
            if lesson.id not in seen_ids:
                seen_ids.add(lesson.id)
                unique_lessons.append(lesson)

        # Sort by effectiveness
        unique_lessons.sort(key=lambda l: l.effectiveness_score, reverse=True)

        return unique_lessons[:10]

    def after_task_blocker(
        self,
        blocker: str,
        resolution: str,
        affected_files: List[str],
        confidence: float = 0.9,
    ) -> Lesson:
        """Record a lesson from resolving a blocker."""
        return self.emitter.emit_blocker_resolution(
            blocker_summary=blocker,
            resolution=resolution,
            applies_to=affected_files,
            confidence=confidence,
        )

    def after_task_discovery(
        self,
        pattern_name: str,
        description: str,
        affected_files: List[str],
        code_example: str,
        anti_pattern: Optional[str] = None,
    ) -> Lesson:
        """Record a pattern discovery."""
        return self.emitter.emit_pattern_discovery(
            pattern_name=pattern_name,
            description=description,
            applies_to=affected_files,
            code_example=code_example,
            anti_pattern=anti_pattern,
        )

    def after_task_general(
        self,
        summary: str,
        category: LessonCategory,
        affected_files: List[str],
        context: str = "",
        is_global: bool = False,
    ) -> Lesson:
        """Record a general lesson."""
        from contextcore.learning.models import LessonSource
        return self.emitter.emit_lesson(
            summary=summary,
            category=category,
            source=LessonSource.PATTERN_DISCOVERED,
            applies_to=affected_files,
            context=context,
            global_lesson=is_global,
        )

    def record_lesson_success(self, lesson_id: str, context: str) -> None:
        """Record that a retrieved lesson was helpful."""
        self.emitter.record_application(lesson_id, success=True, context=context)

    def record_lesson_failure(
        self, lesson_id: str, context: str, feedback: str
    ) -> None:
        """Record that a retrieved lesson was not helpful."""
        self.emitter.record_application(
            lesson_id, success=False, context=context, feedback=feedback
        )
```

### Acceptance Criteria

- [ ] Agents can emit lessons after resolving blockers
- [ ] Agents can query lessons before starting tasks
- [ ] Lessons are stored as OTel spans in Tempo
- [ ] TraceQL queries return relevant lessons
- [ ] Lesson effectiveness tracking works
- [ ] Global lessons retrievable across projects
- [ ] File pattern matching works for applies_to

---

## Verification Checklist

After implementing all Phase 3 features:

- [ ] Knowledge graph builds from test ProjectContexts
- [ ] Impact analysis identifies correct affected projects
- [ ] VSCode extension shows context in status bar
- [ ] VSCode extension provides inline hints
- [ ] Agent learning loop stores lessons
- [ ] Agent learning loop retrieves relevant lessons
- [ ] All features work together end-to-end

---

## Quick Implementation Prompt

```
Implement ContextCore Phase 3 strategic features:

1. Create src/contextcore/graph/ package with:
   - schema.py: Node, Edge, Graph dataclasses with NodeType, EdgeType enums
   - builder.py: GraphBuilder that creates graph from ProjectContexts
   - queries.py: GraphQueries with impact_analysis, get_dependencies, find_path
   Add CLI commands: contextcore graph build, impact, deps

2. Create VSCode extension (new repo contextcore-vscode):
   - ContextMapper class that maps files to ProjectContexts
   - Status bar showing project criticality
   - Side panel with full context view
   - Inline decorations with SLO hints near relevant code

3. Create src/contextcore/learning/ package with:
   - models.py: Lesson, LessonQuery, LessonCategory dataclasses
   - emitter.py: LessonEmitter using OTel spans
   - retriever.py: LessonRetriever using TraceQL queries
   - loop.py: LearningLoop integration class with before_task/after_task methods

Reference: PHASE3_STRATEGIC.md for detailed implementation steps.
```
