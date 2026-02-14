"""ContextCore CLI - Insight management commands."""

import json
from typing import Optional

import click
import yaml


@click.group()
def insight():
    """Emit and query agent insights (persistent memory)."""
    pass


@insight.command("emit")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="contextcore", help="Project ID")
@click.option("--agent", "-a", envvar="CONTEXTCORE_AGENT", default="claude", help="Agent ID")
@click.option("--type", "insight_type", type=click.Choice(["decision", "recommendation", "lesson", "blocker", "discovery", "analysis", "risk", "progress"]), required=True)
@click.option("--summary", "-s", required=True, help="Brief summary of the insight")
@click.option("--confidence", "-c", type=float, default=0.9, help="Confidence score (0.0-1.0)")
@click.option("--rationale", "-r", help="Reasoning behind the insight")
@click.option("--category", help="Category for lessons")
@click.option("--applies-to", multiple=True, help="File paths this applies to")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local storage path")
def insight_emit(project: str, agent: str, insight_type: str, summary: str, confidence: float,
                 rationale: Optional[str], category: Optional[str], applies_to: tuple, local_storage: Optional[str]):
    """Emit an insight for future sessions."""
    from contextcore.agent import InsightEmitter

    emitter = InsightEmitter(project_id=project, agent_id=agent, local_storage_path=local_storage)

    emit_methods = {
        "decision": emitter.emit_decision,
        "recommendation": emitter.emit_recommendation,
        "lesson": emitter.emit_lesson,
        "blocker": emitter.emit_blocker,
        "discovery": emitter.emit_discovery,
        "progress": emitter.emit_progress,
    }

    kwargs = {"rationale": rationale} if rationale else {}

    if insight_type == "lesson":
        if not category:
            category = "general"
        insight = emitter.emit_lesson(summary=summary, category=category, confidence=confidence,
                                      applies_to=list(applies_to) if applies_to else None, **kwargs)
    elif insight_type in emit_methods:
        insight = emit_methods[insight_type](summary=summary, confidence=confidence, **kwargs)
    else:
        from contextcore.agent.insights import InsightType
        insight = emitter.emit(InsightType(insight_type), summary=summary, confidence=confidence,
                               applies_to=list(applies_to) if applies_to else None, category=category, **kwargs)

    click.echo(f"Emitted {insight_type}: {insight.id}")
    click.echo(f"  Summary: {summary}")
    click.echo(f"  Confidence: {confidence}")
    click.echo(f"  Trace ID: {insight.trace_id}")
    if applies_to:
        click.echo(f"  Applies to: {', '.join(applies_to)}")
    if local_storage:
        click.echo(f"  Saved locally: {local_storage}/{project}_insights.json")


@insight.command("query")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", help="Filter by project")
@click.option("--agent", "-a", help="Filter by agent ID")
@click.option("--type", "insight_type", type=click.Choice(["decision", "recommendation", "lesson", "blocker", "discovery", "analysis", "risk", "progress"]))
@click.option("--category", help="Filter by category")
@click.option("--applies-to", help="Filter by file path")
@click.option("--min-confidence", type=float, help="Minimum confidence score")
@click.option("--time-range", "-t", default="30d", help="Time range")
@click.option("--limit", "-l", type=int, default=20, help="Maximum results")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local storage path")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table")
def insight_query(project: Optional[str], agent: Optional[str], insight_type: Optional[str], category: Optional[str],
                  applies_to: Optional[str], min_confidence: Optional[float], time_range: str, limit: int,
                  tempo_url: str, local_storage: Optional[str], output_format: str):
    """Query insights from Tempo or local storage."""
    from contextcore.agent import InsightQuerier

    querier = InsightQuerier(tempo_url=tempo_url if not local_storage else None, local_storage_path=local_storage)

    insights = querier.query(project_id=project, insight_type=insight_type, agent_id=agent, min_confidence=min_confidence,
                             time_range=time_range, limit=limit, applies_to=applies_to, category=category)

    if not insights:
        click.echo("No insights found matching criteria.")
        return

    if output_format == "json":
        data = [{"id": i.id, "type": i.type.value, "summary": i.summary, "confidence": i.confidence,
                 "project_id": i.project_id, "agent_id": i.agent_id, "rationale": i.rationale,
                 "applies_to": i.applies_to, "category": i.category, "trace_id": i.trace_id,
                 "timestamp": i.timestamp.isoformat() if i.timestamp else None} for i in insights]
        click.echo(json.dumps(data, indent=2))
    elif output_format == "yaml":
        data = [{"id": i.id, "type": i.type.value, "summary": i.summary, "confidence": i.confidence,
                 "project_id": i.project_id, "agent_id": i.agent_id, "rationale": i.rationale,
                 "applies_to": i.applies_to, "category": i.category} for i in insights]
        click.echo(yaml.dump(data, default_flow_style=False))
    else:
        click.echo(f"Found {len(insights)} insights:")
        click.echo()
        click.echo(f"{'Type':<12} {'Confidence':<10} {'Summary':<50} {'Agent'}")
        click.echo("-" * 90)
        for i in insights:
            summary = i.summary[:47] + "..." if len(i.summary) > 50 else i.summary
            click.echo(f"{i.type.value:<12} {i.confidence:<10.2f} {summary:<50} {i.agent_id}")


@insight.command("list")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", required=True, help="Project ID")
@click.option("--type", "-t", "insight_type",
              type=click.Choice(["decision", "recommendation", "lesson", "blocker",
                                 "discovery", "analysis", "risk", "progress"]))
@click.option("--agent", "-a", help="Filter by agent ID")
@click.option("--audience", type=click.Choice(["agent", "human", "both"]), help="Filter by audience")
@click.option("--min-confidence", type=float, help="Minimum confidence score (0.0-1.0)")
@click.option("--time-range", default="24h", help="Time range (1h, 24h, 7d, 30d)")
@click.option("--limit", "-n", type=int, default=20, help="Maximum results")
@click.option("--format", "-f", "output_format", type=click.Choice(["text", "json", "detail"]), default="text")
@click.option("--verbose", "-v", is_flag=True, help="Show full details")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local storage path")
def insight_list(project: str, insight_type: Optional[str], agent: Optional[str],
                 audience: Optional[str], min_confidence: Optional[float],
                 time_range: str, limit: int, output_format: str, verbose: bool,
                 tempo_url: str, local_storage: Optional[str]):
    """List recent insights for a project (default: last 24h).

    The default \"what's new\" view — shows recent insights ordered by recency.

    Examples:
        contextcore insight list -p my-project
        contextcore insight list -p my-project --type decision --min-confidence 0.8
        contextcore insight list -p my-project --format json | jq '.[].summary'
    """
    from contextcore.agent import InsightQuerier

    querier = InsightQuerier(
        tempo_url=tempo_url if not local_storage else None,
        local_storage_path=local_storage,
    )

    insights = querier.query(
        project_id=project,
        insight_type=insight_type,
        agent_id=agent,
        audience=audience,
        min_confidence=min_confidence,
        time_range=time_range,
        limit=limit,
    )

    if not insights:
        click.echo("No insights found for the specified criteria.")
        return

    if output_format == "json":
        data = [
            {
                "id": i.id,
                "type": i.type.value if hasattr(i.type, "value") else str(i.type),
                "summary": i.summary,
                "confidence": i.confidence,
                "project_id": i.project_id,
                "agent_id": i.agent_id,
                "rationale": i.rationale,
                "applies_to": i.applies_to,
                "category": i.category,
                "trace_id": i.trace_id,
                "timestamp": i.timestamp.isoformat() if i.timestamp else None,
            }
            for i in insights
        ]
        click.echo(json.dumps(data, indent=2))

    elif output_format == "detail":
        click.echo(f"Insights for {project} (last {time_range}, {len(insights)} found):\n")
        for idx, i in enumerate(insights, 1):
            type_val = i.type.value if hasattr(i.type, "value") else str(i.type)
            ts = i.timestamp.strftime("%Y-%m-%d %H:%M") if i.timestamp else "unknown"
            click.echo(f"[{idx}] {type_val.upper()} — {i.summary}")
            click.echo(f"    Agent: {i.agent_id}  Confidence: {i.confidence:.0%}  Time: {ts}")
            if i.rationale:
                click.echo(f"    Rationale: {i.rationale}")
            if i.applies_to:
                click.echo(f"    Applies to: {', '.join(i.applies_to)}")
            if i.category:
                click.echo(f"    Category: {i.category}")
            if i.evidence:
                click.echo(f"    Evidence: {len(i.evidence)} item(s)")
                for ev in i.evidence:
                    desc = f": {ev.description}" if ev.description else ""
                    click.echo(f"      [{ev.type}] {ev.ref}{desc}")
            if i.trace_id:
                click.echo(f"    Trace: {i.trace_id}")
            click.echo()

    else:  # text
        click.echo(f"Insights for {project} (last {time_range}, {len(insights)} found):\n")
        click.echo(f"  {'Time':<17} {'Type':<14} {'Conf':<6} {'Summary':<50} {'Agent'}")
        click.echo(f"  {'-'*17} {'-'*14} {'-'*6} {'-'*50} {'-'*10}")
        for i in insights:
            type_val = i.type.value if hasattr(i.type, "value") else str(i.type)
            ts = i.timestamp.strftime("%Y-%m-%d %H:%M") if i.timestamp else "?"
            max_len = 120 if verbose else 47
            summary = i.summary[:max_len] + "..." if len(i.summary) > max_len + 3 else i.summary
            click.echo(f"  {ts:<17} {type_val:<14} {i.confidence:<6.0%} {summary:<50} {i.agent_id}")


@insight.command("search")
@click.argument("query", required=False)
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", help="Scope to project")
@click.option("--type", "-t", "insight_type",
              type=click.Choice(["decision", "recommendation", "lesson", "blocker",
                                 "discovery", "analysis", "risk", "progress"]))
@click.option("--agent", "-a", help="Filter by agent ID")
@click.option("--applies-to", help="Filter by file path (partial match)")
@click.option("--category", help="Filter by category")
@click.option("--min-confidence", type=float, help="Minimum confidence score")
@click.option("--time-range", default="7d", help="Time range (default: 7d)")
@click.option("--limit", "-n", type=int, default=50, help="Maximum results")
@click.option("--format", "-f", "output_format", type=click.Choice(["text", "json", "detail"]), default="text")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local storage path")
def insight_search(query: Optional[str], project: Optional[str], insight_type: Optional[str],
                   agent: Optional[str], applies_to: Optional[str], category: Optional[str],
                   min_confidence: Optional[float], time_range: str, limit: int,
                   output_format: str, tempo_url: str, local_storage: Optional[str]):
    """Search for insights by keyword or structured filters.

    More targeted than 'list' — answers \"what did agents decide about X?\"
    or \"are there blockers in project Y?\"

    Examples:
        contextcore insight search \"authentication\"
        contextcore insight search --applies-to tracker.py
        contextcore insight search --type blocker --project my-project
        contextcore insight search --category testing --min-confidence 0.8
    """
    from contextcore.agent import InsightQuerier

    querier = InsightQuerier(
        tempo_url=tempo_url if not local_storage else None,
        local_storage_path=local_storage,
    )

    insights = querier.query(
        project_id=project,
        insight_type=insight_type,
        agent_id=agent,
        min_confidence=min_confidence,
        time_range=time_range,
        limit=limit,
        applies_to=applies_to,
        category=category,
    )

    # Client-side keyword filtering (Tempo doesn't support full-text search)
    if query and insights:
        query_lower = query.lower()
        insights = [
            i for i in insights
            if query_lower in i.summary.lower()
            or (i.rationale and query_lower in i.rationale.lower())
            or (i.category and query_lower in i.category.lower())
        ]

    if not insights:
        click.echo("No insights found matching criteria.")
        return

    scope = f"project={project}" if project else "all projects"
    click.echo(f"Search results ({len(insights)} found, {scope}, last {time_range}):")

    if output_format == "json":
        data = [
            {
                "id": i.id,
                "type": i.type.value if hasattr(i.type, "value") else str(i.type),
                "summary": i.summary,
                "confidence": i.confidence,
                "project_id": i.project_id,
                "agent_id": i.agent_id,
                "rationale": i.rationale,
                "applies_to": i.applies_to,
                "category": i.category,
                "trace_id": i.trace_id,
                "timestamp": i.timestamp.isoformat() if i.timestamp else None,
            }
            for i in insights
        ]
        click.echo(json.dumps(data, indent=2))

    elif output_format == "detail":
        click.echo()
        for idx, i in enumerate(insights, 1):
            type_val = i.type.value if hasattr(i.type, "value") else str(i.type)
            ts = i.timestamp.strftime("%Y-%m-%d %H:%M") if i.timestamp else "unknown"
            click.echo(f"[{idx}] {type_val.upper()} — {i.summary}")
            click.echo(f"    Project: {i.project_id}  Agent: {i.agent_id}  Confidence: {i.confidence:.0%}  Time: {ts}")
            if i.rationale:
                click.echo(f"    Rationale: {i.rationale}")
            if i.applies_to:
                click.echo(f"    Applies to: {', '.join(i.applies_to)}")
            if i.category:
                click.echo(f"    Category: {i.category}")
            click.echo()

    else:  # text
        click.echo()
        click.echo(f"  {'Time':<17} {'Type':<14} {'Conf':<6} {'Project':<20} {'Summary'}")
        click.echo(f"  {'-'*17} {'-'*14} {'-'*6} {'-'*20} {'-'*40}")
        for i in insights:
            type_val = i.type.value if hasattr(i.type, "value") else str(i.type)
            ts = i.timestamp.strftime("%Y-%m-%d %H:%M") if i.timestamp else "?"
            summary = i.summary[:60] + "..." if len(i.summary) > 63 else i.summary
            proj = i.project_id[:18] + ".." if len(i.project_id) > 20 else i.project_id
            click.echo(f"  {ts:<17} {type_val:<14} {i.confidence:<6.0%} {proj:<20} {summary}")


@insight.command("lessons")
@click.option("--project", "-p", envvar="CONTEXTCORE_PROJECT", default="contextcore", help="Project ID")
@click.option("--applies-to", help="Filter by file path")
@click.option("--category", help="Filter by category")
@click.option("--time-range", "-t", default="30d", help="Time range")
@click.option("--tempo-url", envvar="TEMPO_URL", default="http://localhost:3200", help="Tempo URL")
@click.option("--local-storage", envvar="CONTEXTCORE_LOCAL_STORAGE", help="Local storage path")
def insight_lessons(project: str, applies_to: Optional[str], category: Optional[str], time_range: str,
                    tempo_url: str, local_storage: Optional[str]):
    """List lessons learned for a project."""
    from contextcore.agent import InsightQuerier

    querier = InsightQuerier(tempo_url=tempo_url if not local_storage else None, local_storage_path=local_storage)

    lessons = querier.get_lessons(project_id=project, applies_to=applies_to, category=category, time_range=time_range)

    if not lessons:
        click.echo("No lessons found.")
        return

    click.echo(f"Lessons Learned ({len(lessons)} total):")
    click.echo()

    for i, lesson in enumerate(lessons, 1):
        click.echo(f"{i}. {lesson.summary}")
        if lesson.category:
            click.echo(f"   Category: {lesson.category}")
        if lesson.applies_to:
            click.echo(f"   Applies to: {', '.join(lesson.applies_to)}")
        click.echo(f"   Confidence: {lesson.confidence:.0%}")
        click.echo()
