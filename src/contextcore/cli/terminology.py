"""ContextCore CLI - Terminology management commands."""

import json
import sys
from typing import Optional

import click
import yaml


@click.group()
def terminology():
    """Manage Wayfinder terminology definitions as OTel spans."""
    pass


@terminology.command("emit")
@click.option("--path", "-p", required=True, help="Path to terminology directory")
@click.option("--endpoint", envvar="OTEL_EXPORTER_OTLP_ENDPOINT", default="localhost:4317", help="OTLP endpoint")
@click.option("--dry-run", is_flag=True, help="Show what would be emitted without sending")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table")
def terminology_emit(path: str, endpoint: str, dry_run: bool, output_format: str):
    """Emit terminology definitions to Tempo for discovery."""
    from contextcore.terminology import TerminologyParser, TerminologyEmitter

    try:
        parser = TerminologyParser()
        manifest, terms, distinctions, avoid_terms = parser.parse_directory(path)

        click.echo(f"Parsed terminology: {manifest.terminology_id}")
        click.echo(f"  Schema version: {manifest.schema_version}")
        click.echo(f"  Last updated: {manifest.last_updated}")
        click.echo(f"  Status: {manifest.status}")
        click.echo()
        click.echo(f"  Terms: {len(terms)}")
        click.echo(f"  Distinctions: {len(distinctions)}")
        click.echo(f"  Routing entries: {len(manifest.routing)}")
        click.echo(f"  Terms to avoid: {len(avoid_terms)}")
        click.echo(f"  Total tokens: {manifest.total_tokens}")
        click.echo()

        if dry_run:
            click.echo("Dry run - would emit:")
            click.echo()
            click.echo("Terms:")
            for term in terms:
                click.echo(f"  - {term.id} ({term.type}): {term.name}")

            click.echo()
            click.echo("Distinctions:")
            for dist in distinctions:
                click.echo(f"  - {dist.id}: {dist.question[:50]}...")

            click.echo()
            click.echo("Routing table sample:")
            for keyword, term_id in list(manifest.routing.items())[:5]:
                click.echo(f"  - {keyword} -> {term_id}")
            if len(manifest.routing) > 5:
                click.echo(f"  ... and {len(manifest.routing) - 5} more")

            return

        # Set up OTel
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({
            "service.name": "contextcore-terminology",
            "service.version": "1.0.0"
        })
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Emit
        emitter = TerminologyEmitter()
        trace_id, span_ids = emitter.emit_terminology(
            manifest, terms, distinctions, avoid_terms
        )

        # Force flush before exit
        provider.force_flush()

        click.echo(f"Emitted to Tempo:")
        click.echo(f"  Trace ID: {trace_id}")
        click.echo(f"  Span count: {len(span_ids) + 1}")  # +1 for manifest span
        click.echo()

        click.echo("Example TraceQL queries:")
        click.echo(f'  {{ name = "terminology:{manifest.terminology_id}" }}')
        click.echo('  { term.type = "implementation" }')
        click.echo('  { term.category = "core_concepts" }')
        click.echo('  { distinction.question =~ ".*ContextCore.*" }')
        click.echo('  { routing.keyword = "suite" }')

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error emitting terminology: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@terminology.command("list")
@click.option("--path", "-p", required=True, help="Path to terminology directory")
@click.option("--format", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table")
def terminology_list(path: str, output_format: str):
    """List all terms in a terminology directory."""
    from contextcore.terminology import TerminologyParser

    try:
        parser = TerminologyParser()
        manifest, terms, distinctions, avoid_terms = parser.parse_directory(path)

        if output_format == "json":
            data = {
                "terminology_id": manifest.terminology_id,
                "terms": [{"id": t.id, "name": t.name, "type": t.type, "category": t.category} for t in terms],
                "distinctions": [{"id": d.id, "question": d.question} for d in distinctions],
            }
            click.echo(json.dumps(data, indent=2))
        elif output_format == "yaml":
            data = {
                "terminology_id": manifest.terminology_id,
                "terms": [{"id": t.id, "name": t.name, "type": t.type, "category": t.category} for t in terms],
                "distinctions": [{"id": d.id, "question": d.question} for d in distinctions],
            }
            click.echo(yaml.dump(data, default_flow_style=False))
        else:
            click.echo(f"Terminology: {manifest.terminology_id}")
            click.echo(f"Status: {manifest.status}")
            click.echo()
            click.echo(f"{'ID':<25} {'Name':<20} {'Type':<15} {'Category'}")
            click.echo("-" * 80)
            for term in sorted(terms, key=lambda t: (t.category or "", t.id)):
                click.echo(f"{term.id:<25} {term.name:<20} {term.type:<15} {term.category or '-'}")

            if distinctions:
                click.echo()
                click.echo("Distinctions:")
                for dist in distinctions:
                    click.echo(f"  - {dist.id}: {dist.question}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@terminology.command("lookup")
@click.option("--path", "-p", required=True, help="Path to terminology directory")
@click.argument("term_id")
@click.option("--format", "output_format", type=click.Choice(["text", "json", "yaml"]), default="text")
def terminology_lookup(path: str, term_id: str, output_format: str):
    """Look up a specific term by ID."""
    from contextcore.terminology import TerminologyParser

    try:
        parser = TerminologyParser()
        manifest, terms, distinctions, _ = parser.parse_directory(path)

        # Check quick lookup first
        if term_id in manifest.quick_lookup:
            entry = manifest.quick_lookup[term_id]
            if output_format == "json":
                click.echo(json.dumps({
                    "id": term_id,
                    "type": entry.type,
                    "one_liner": entry.one_liner,
                    "analogy": entry.analogy,
                    "producer": entry.producer,
                    "source": "quick_lookup"
                }, indent=2))
            elif output_format == "yaml":
                click.echo(yaml.dump({
                    "id": term_id,
                    "type": entry.type,
                    "one_liner": entry.one_liner,
                    "analogy": entry.analogy,
                    "producer": entry.producer,
                    "source": "quick_lookup"
                }, default_flow_style=False))
            else:
                click.echo(f"Term: {term_id}")
                click.echo(f"Type: {entry.type}")
                click.echo(f"Definition: {entry.one_liner}")
                if entry.analogy:
                    click.echo(f"Analogy: {entry.analogy}")
                if entry.producer:
                    click.echo(f"Producer: {entry.producer}")
                click.echo("(from quick_lookup)")
            return

        # Check routing table
        if term_id in manifest.routing:
            resolved_id = manifest.routing[term_id]
            click.echo(f"'{term_id}' routes to '{resolved_id}'")
            term_id = resolved_id

        # Find full term
        term = next((t for t in terms if t.id == term_id), None)
        if not term:
            click.echo(f"Term not found: {term_id}", err=True)
            click.echo()
            click.echo("Available terms:")
            for t in terms:
                click.echo(f"  - {t.id}")
            sys.exit(1)

        if output_format == "json":
            click.echo(json.dumps({
                "id": term.id,
                "name": term.name,
                "type": term.type,
                "definition": term.definition,
                "category": term.category,
                "triggers": term.triggers,
                "related_terms": term.related_terms,
            }, indent=2))
        elif output_format == "yaml":
            click.echo(yaml.dump({
                "id": term.id,
                "name": term.name,
                "type": term.type,
                "definition": term.definition,
                "category": term.category,
                "triggers": term.triggers,
                "related_terms": term.related_terms,
            }, default_flow_style=False))
        else:
            click.echo(f"Term: {term.name}")
            click.echo(f"ID: {term.id}")
            click.echo(f"Type: {term.type}")
            click.echo(f"Category: {term.category or '-'}")
            click.echo()
            click.echo("Definition:")
            click.echo(term.definition.strip())
            if term.triggers:
                click.echo()
                click.echo(f"Triggers: {', '.join(term.triggers)}")
            if term.related_terms:
                click.echo(f"Related: {', '.join(term.related_terms)}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@terminology.command("routing")
@click.option("--path", "-p", required=True, help="Path to terminology directory")
@click.option("--format", "output_format", type=click.Choice(["table", "yaml"]), default="table")
def terminology_routing(path: str, output_format: str):
    """Show the keyword routing table."""
    from contextcore.terminology import TerminologyParser

    try:
        parser = TerminologyParser()
        manifest, _, _, _ = parser.parse_directory(path)

        if output_format == "yaml":
            click.echo(yaml.dump(manifest.routing, default_flow_style=False))
        else:
            click.echo(f"Routing table for {manifest.terminology_id}:")
            click.echo()
            click.echo(f"{'Keyword':<30} {'Term ID'}")
            click.echo("-" * 55)
            for keyword, term_id in sorted(manifest.routing.items()):
                click.echo(f"{keyword:<30} {term_id}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
