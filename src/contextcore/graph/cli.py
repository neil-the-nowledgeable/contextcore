import click
from typing import List, Dict, Optional
import json
from contextcore.graph.builder import GraphBuilder
from contextcore.graph.queries import impact_analysis, get_dependencies, find_path
from pathlib import Path

__all__ = ["graph"]

@click.group(help="Knowledge graph commands.")
def graph() -> None:
    """Main command group for knowledge graph operations."""
    pass

@click.command("build")
@click.option('--output', '-o', type=click.Path(), help="Optional file path for JSON export")
def build(output: Optional[str]) -> None:
    """Build the knowledge graph from all project contexts."""
    try:
        # Load all available project contexts
        contexts = list_all_project_contexts()
        if not contexts:
            click.echo("⚠️  No project contexts found")
            return

        # Build the graph using GraphBuilder
        builder = GraphBuilder(contexts)
        graph_obj = builder.build()
        
        # Extract node and edge counts for summary
        node_count = len(graph_obj.nodes) if hasattr(graph_obj, 'nodes') else 0
        edge_count = len(graph_obj.edges) if hasattr(graph_obj, 'edges') else 0
        
        click.echo(f"Built graph with {node_count} nodes and {edge_count} edges")
        
        # Export to JSON if output path specified
        if output:
            graph_data = graph_obj.to_dict() if hasattr(graph_obj, 'to_dict') else {}
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, indent=2)
            click.echo(f"Graph exported to {output}")
            
    except Exception as e:
        click.echo(f"❌ Error building graph: {e}")

@click.command("impact")
@click.option('--project', '-p', required=True, help="Project ID to analyze")
@click.option('--depth', '-d', default=3, type=int, help="Max traversal depth")
def impact(project: str, depth: int) -> None:
    """Analyze the impact of changes to a project."""
    try:
        # Build graph from all contexts
        contexts = list_all_project_contexts()
        if not contexts:
            click.echo("⚠️  No project contexts available for analysis")
            return
            
        builder = GraphBuilder(contexts)
        graph_obj = builder.build()
        
        # Run impact analysis with specified depth
        results = impact_analysis(graph_obj, project, depth)
        
        # Print formatted impact report
        click.echo(f"Impact Analysis: {project}")
        click.echo(f"Affected Projects: {results.get('affected_projects', 0)}")
        click.echo(f"Critical Projects: {results.get('critical_projects', 0)}")
        click.echo(f"Affected Teams: {results.get('affected_teams', 0)}")
        click.echo(f"Blast Radius: {results.get('blast_radius', 0)}")
        
        # Warning for critical projects
        if results.get('critical_projects', 0) > 0:
            click.echo("⚠️  Critical projects detected in impact analysis")
            
    except Exception as e:
        click.echo(f"❌ Error during impact analysis: {e}")

@click.command("deps")
@click.option('--project', '-p', required=True, help="Project ID to query")
def deps(project: str) -> None:
    """Show dependencies for a project."""
    try:
        # Build graph from all contexts
        contexts = list_all_project_contexts()
        if not contexts:
            click.echo("⚠️  No project contexts available for dependency analysis")
            return
            
        builder = GraphBuilder(contexts)
        graph_obj = builder.build()
        
        # Get dependencies for the specified project
        dependencies = get_dependencies(graph_obj, project)
        
        # Print formatted dependency report
        click.echo(f"Dependencies: {project}")
        
        upstream = dependencies.get('upstream', [])
        click.echo(f"Upstream (depends on): {', '.join(upstream) if upstream else 'none'}")
        
        downstream = dependencies.get('downstream', [])
        click.echo(f"Downstream (depended by): {', '.join(downstream) if downstream else 'none'}")
        
        shared_resources = dependencies.get('shared_resources', [])
        click.echo(f"Shared Resources: {', '.join(shared_resources) if shared_resources else 'none'}")
        
        shared_adrs = dependencies.get('shared_adrs', [])
        click.echo(f"Shared ADRs: {', '.join(shared_adrs) if shared_adrs else 'none'}")
        
    except Exception as e:
        click.echo(f"❌ Error fetching dependencies: {e}")

@click.command("path")
@click.option('--from', '-f', 'from_project', required=True, help="Source project")
@click.option('--to', '-t', required=True, help="Target project")
def path(from_project: str, to_project: str) -> None:
    """Find dependency path between two projects."""
    try:
        # Build graph from all contexts
        contexts = list_all_project_contexts()
        if not contexts:
            click.echo("⚠️  No project contexts available for path analysis")
            return
            
        builder = GraphBuilder(contexts)
        graph_obj = builder.build()
        
        # Find path between the two projects
        path_result = find_path(graph_obj, from_project, to_project)
        
        # Print path result
        if path_result:
            path_str = ' -> '.join(path_result) if isinstance(path_result, list) else str(path_result)
            click.echo(f"Path: {path_str}")
        else:
            click.echo("No path found")
            
    except Exception as e:
        click.echo(f"❌ Error finding path: {e}")

def list_all_project_contexts() -> List[Dict]:
    """
    Load all project contexts from available sources.
    
    Attempts to load from Kubernetes first, falls back to empty list
    with warning if unavailable.
    
    Returns:
        List of project context dictionaries
    """
    try:
        # Try to load from Kubernetes or other primary source
        # This would typically import from contextcore.storage or similar
        # For now, return empty list as fallback
        click.echo("⚠️  Context loading not yet implemented, using empty context list")
        return []
    except Exception:
        click.echo("⚠️  Failed to load project contexts")
        return []

# Register all commands with the graph group
graph.add_command(build)
graph.add_command(impact)
graph.add_command(deps)
graph.add_command(path)
