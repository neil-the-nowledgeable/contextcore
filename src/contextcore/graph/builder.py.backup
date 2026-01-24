"""Build knowledge graph from ProjectContext CRDs.

This module provides classes for building and maintaining a knowledge graph
from ProjectContext custom resources.
"""

__all__ = [
    "GraphBuilder",
    "GraphWatcher",
]

import hashlib
from typing import Any, Dict, List, Optional

from contextcore.graph.schema import Edge, EdgeType, Graph, Node, NodeType


class GraphBuilder:
    """Builds and maintains knowledge graph from ProjectContexts.

    Example:
        builder = GraphBuilder()
        graph = builder.build_from_contexts(contexts)
        print(f"Built graph with {len(graph.nodes)} nodes")
    """

    def __init__(self) -> None:
        """Initialize the graph builder."""
        self.graph = Graph()
        self._resource_to_project: Dict[str, List[str]] = {}

    def build_from_contexts(self, contexts: List[Dict[str, Any]]) -> Graph:
        """Build complete graph from list of ProjectContexts.

        Args:
            contexts: List of ProjectContext dictionaries

        Returns:
            The completed knowledge graph
        """
        self.graph = Graph()
        self._resource_to_project = {}

        for ctx in contexts:
            self._process_context(ctx)

        # Infer dependencies after all contexts processed
        self._infer_dependencies()

        return self.graph

    def _process_context(self, ctx: Dict[str, Any]) -> None:
        """Process a single ProjectContext into graph nodes and edges.

        Args:
            ctx: ProjectContext dictionary with metadata and spec
        """
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
                "epic": (
                    spec.get("project", {}).get("epic")
                    if isinstance(spec.get("project"), dict)
                    else None
                ),
            },
        )
        self.graph.add_node(project_node)

        # Process business context -> Team node
        business = spec.get("business", {})
        if business.get("owner"):
            team_node = Node(
                id=f"team:{business['owner']}",
                type=NodeType.TEAM,
                name=business["owner"],
                attributes={"cost_center": business.get("costCenter")},
            )
            self.graph.add_node(team_node)
            self.graph.add_edge(
                Edge(
                    source_id=project_node.id,
                    target_id=team_node.id,
                    type=EdgeType.OWNED_BY,
                )
            )

        # Process targets -> Resource nodes
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
            self.graph.add_edge(
                Edge(
                    source_id=project_node.id,
                    target_id=resource_id,
                    type=EdgeType.MANAGES,
                )
            )

            # Track resource -> project mapping for dependency inference
            if resource_id not in self._resource_to_project:
                self._resource_to_project[resource_id] = []
            self._resource_to_project[resource_id].append(project_node.id)

        # Process design -> ADR and Contract nodes
        design = spec.get("design", {})
        if design.get("adr"):
            adr_node = Node(
                id=f"adr:{design['adr']}",
                type=NodeType.ADR,
                name=design["adr"],
                attributes={"url": design.get("doc")},
            )
            self.graph.add_node(adr_node)
            self.graph.add_edge(
                Edge(
                    source_id=project_node.id,
                    target_id=adr_node.id,
                    type=EdgeType.IMPLEMENTS,
                )
            )

        if design.get("apiContract"):
            contract_node = Node(
                id=f"contract:{self._hash_url(design['apiContract'])}",
                type=NodeType.CONTRACT,
                name=design["apiContract"],
                attributes={"url": design["apiContract"]},
            )
            self.graph.add_node(contract_node)
            self.graph.add_edge(
                Edge(
                    source_id=project_node.id,
                    target_id=contract_node.id,
                    type=EdgeType.EXPOSES,
                )
            )

        # Process requirements -> Requirement nodes
        requirements = spec.get("requirements", {})
        if requirements:
            req_id = f"requirement:{project_id}"
            req_node = Node(
                id=req_id,
                type=NodeType.REQUIREMENT,
                name=f"{project_id} requirements",
                attributes={
                    "availability": requirements.get("availability"),
                    "latencyP99": requirements.get("latencyP99"),
                    "latencyP50": requirements.get("latencyP50"),
                    "throughput": requirements.get("throughput"),
                    "errorBudget": requirements.get("errorBudget"),
                },
            )
            self.graph.add_node(req_node)
            self.graph.add_edge(
                Edge(
                    source_id=project_node.id,
                    target_id=req_id,
                    type=EdgeType.HAS_REQUIREMENT,
                )
            )

        # Process risks -> Risk nodes
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
                    "scope": risk.get("scope"),
                },
            )
            self.graph.add_node(risk_node)
            self.graph.add_edge(
                Edge(
                    source_id=project_node.id,
                    target_id=risk_id,
                    type=EdgeType.HAS_RISK,
                    weight=self._risk_weight(risk.get("priority")),
                )
            )

    def _infer_dependencies(self) -> None:
        """Infer project-to-project dependencies from shared resources.

        Currently identifies Service resources. Future enhancement will
        use trace data for actual call dependencies.
        """
        # Find Service resources that might indicate dependencies
        service_nodes = [
            n
            for n in self.graph.nodes.values()
            if n.type == NodeType.RESOURCE and n.attributes.get("kind") == "Service"
        ]

        # For each service, check if multiple projects reference it
        for service in service_nodes:
            managing_projects = self._resource_to_project.get(service.id, [])
            # If multiple projects manage the same service, they may be related
            # Real implementation would use trace data to find actual callers

    def _get_project_id(self, spec: Dict[str, Any], default: str) -> str:
        """Extract project ID from spec.

        Args:
            spec: The ProjectContext spec
            default: Default value if not found

        Returns:
            The project ID
        """
        project = spec.get("project", {})
        if isinstance(project, dict):
            return project.get("id", default)
        return project or default

    def _make_resource_id(self, target: Dict[str, Any], default_ns: str) -> str:
        """Create a unique resource ID.

        Args:
            target: The target dictionary with kind, name, namespace
            default_ns: Default namespace if not specified

        Returns:
            Resource ID in format "resource:{ns}/{kind}/{name}"
        """
        kind = target.get("kind", "Unknown")
        name = target.get("name", "unknown")
        ns = target.get("namespace", default_ns)
        return f"resource:{ns}/{kind}/{name}"

    def _hash_url(self, url: str) -> str:
        """Create a short hash for URL-based IDs.

        Args:
            url: The URL to hash

        Returns:
            First 12 characters of MD5 hash
        """
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _risk_weight(self, priority: Optional[str]) -> float:
        """Convert risk priority to edge weight.

        Args:
            priority: Priority string (P1, P2, P3, P4)

        Returns:
            Weight value (higher for higher priority)
        """
        weights = {"P1": 4.0, "P2": 3.0, "P3": 2.0, "P4": 1.0}
        return weights.get(priority, 1.0)


class GraphWatcher:
    """Watch ProjectContext changes and update graph in real-time.

    This is a stub implementation. Full implementation requires
    a running Kubernetes cluster with the ProjectContext CRD installed.
    """

    def __init__(self, builder: GraphBuilder) -> None:
        """Initialize the watcher.

        Args:
            builder: The GraphBuilder instance to use
        """
        self.builder = builder
        self._running = False

    def start(self) -> None:
        """Start watching ProjectContext changes.

        Requires kubernetes client to be configured.
        """
        try:
            from kubernetes import client, config, watch

            config.load_incluster_config()
        except Exception:
            try:
                from kubernetes import config

                config.load_kube_config()
            except Exception:
                print("[GraphWatcher] Could not load kubernetes config")
                return

        from kubernetes import client, watch

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
        """Stop watching for changes."""
        self._running = False

    def _remove_context(self, ctx: Dict[str, Any]) -> None:
        """Remove a context from the graph.

        Args:
            ctx: The ProjectContext to remove
        """
        metadata = ctx.get("metadata", {})
        spec = ctx.get("spec", {})
        project_id = self.builder._get_project_id(spec, metadata.get("name", "unknown"))
        project_node_id = f"project:{project_id}"

        # Remove the project node
        if project_node_id in self.builder.graph.nodes:
            del self.builder.graph.nodes[project_node_id]

        # Remove all edges connected to this node
        self.builder.graph.edges = [
            e
            for e in self.builder.graph.edges
            if e.source_id != project_node_id and e.target_id != project_node_id
        ]
