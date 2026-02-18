"""
ContextCore CLI - Manage ProjectContext resources and track tasks as spans.

Commands:
    contextcore create      Create a new ProjectContext
    contextcore annotate    Annotate K8s resources with context
    contextcore generate    Generate observability artifacts
    contextcore runbook     Generate operational runbook
    contextcore controller  Run the controller locally
    contextcore sync        Sync from external project tools
    contextcore task        Track project tasks as OTel spans
    contextcore sprint      Track sprints as parent spans
    contextcore metrics     View derived project metrics
    contextcore git         Git integration for automatic task linking
    contextcore demo        Demo data generation (microservices-demo)
    contextcore skill       Manage skill capabilities
    contextcore insight     Agent insights (persistent memory)
    contextcore knowledge   Convert markdown to queryable telemetry
    contextcore value       Value capability tracking
    contextcore docs        Documentation index (generate, query)
    contextcore terminology Manage Wayfinder terminology definitions
    contextcore rbac        Manage RBAC roles and permissions
    contextcore dashboards  Provision Grafana dashboards
    contextcore ops         Operational health and backup
    contextcore install     Installation verification
    contextcore graph       Knowledge graph commands (Phase 3)
"""

import click

# Import command groups
from .sync import sync
from .sprint import sprint
from .metrics import metrics
from .install import install
from .ops import ops
from .rbac import rbac
from .dashboards import dashboards
from .task import task
from .git import git
from .demo import demo
from .value import value
from .skill import skill
from .insight import insight
from .knowledge import knowledge
from .terminology import terminology
from .manifest import manifest
from .docs import docs
from .polish import polish
from .fix import fix
from .core import create, annotate, generate, runbook, controller

# Phase 2 commands
from .review import review
from .contract import contract
from .slo_tests import slo_tests
from .status import status
from .weaver import weaver

# Phase 3 commands
from .graph import graph

# Capability index commands
from .capability_index import capability_index

# TUI commands
from .tui import tui

# Discovery commands (from discovery module)
from contextcore.discovery import discovery_group


@click.group()
@click.version_option()
def main():
    """ContextCore - Unified metadata from project to operations."""
    pass


# Register standalone commands
main.add_command(create)
main.add_command(annotate)
main.add_command(generate)
main.add_command(runbook)
main.add_command(controller)

# Register command groups
main.add_command(sync)
main.add_command(sprint)
main.add_command(metrics)
main.add_command(install)
main.add_command(ops)
main.add_command(rbac)
main.add_command(dashboards)
main.add_command(task)
main.add_command(git)
main.add_command(demo)
main.add_command(value)
main.add_command(skill)
main.add_command(insight)
main.add_command(knowledge)
main.add_command(terminology)
main.add_command(manifest)
main.add_command(docs)
main.add_command(polish)
main.add_command(fix)

# Phase 2 command groups
main.add_command(review)
main.add_command(contract)
main.add_command(slo_tests, name="slo-tests")
main.add_command(status)
main.add_command(weaver)

# Phase 3 command groups
main.add_command(graph)

# TUI command group
main.add_command(tui)

# Capability index command group
main.add_command(capability_index, name="capability-index")

# Discovery command group
main.add_command(discovery_group, name="discovery")


if __name__ == "__main__":
    main()
