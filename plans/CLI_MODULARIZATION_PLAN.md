# CLI Modularization Plan

## Overview

The current `src/contextcore/cli.py` is a 3,837-line monolithic file containing 15 command groups and 85+ functions. This plan restructures it into a modular package for better maintainability by both humans and AI agents.

---

## Current State Analysis

### File Statistics
- **Lines:** 3,837
- **Command Groups:** 15
- **Functions:** 85+
- **Imports:** Primarily lazy (inside functions) - good for modularization

### Command Groups by Size

| Group | Lines | Commands | Description |
|-------|-------|----------|-------------|
| `generate` | ~245 | 1 | Generate observability artifacts |
| `knowledge` | ~402 | 2 | Knowledge management |
| `skill` | ~305 | 5 | Skill emission and query |
| `insight` | ~247 | 3 | Insight emission and query |
| `ops` | ~287 | 6 | Operations (doctor, health, backup) |
| `dashboards` | ~238 | 3 | Dashboard management |
| `rbac` | ~239 | 7 | Role-based access control |
| `install` | ~229 | 3 | Installation verification |
| `task` | ~229 | 8 | Task tracking as spans |
| `git` | ~218 | 3 | Git integration |
| `value` | ~297 | 4 | Value tracking |
| `metrics` | ~189 | 4 | Project metrics |
| `demo` | ~276 | 4 | Demo generation |
| `sprint` | ~79 | 2 | Sprint tracking |
| `sync` | ~38 | 2 | External sync |
| `main` | ~175 | 4 | Core commands |

### Helper Functions to Extract
- `_generate_service_monitor()` - 41 lines
- `_generate_prometheus_rule()` - 66 lines
- `_generate_dashboard()` - 63 lines
- `_get_tracker()` - 9 lines
- `parse_task_refs()` - 9 lines
- `parse_completion_refs()` - 10 lines

---

## Proposed Structure

```
src/contextcore/
├── cli/
│   ├── __init__.py          # Main entry point, registers all groups
│   ├── _common.py            # Shared utilities, decorators, output helpers
│   ├── _generators.py        # ServiceMonitor, PrometheusRule, Dashboard generators
│   │
│   ├── core.py               # create, annotate, generate, controller commands
│   ├── sync.py               # jira, github sync commands
│   ├── task.py               # Task tracking commands (start, update, block, etc.)
│   ├── sprint.py             # Sprint tracking commands
│   ├── metrics.py            # Metrics viewing commands
│   ├── git.py                # Git integration commands
│   ├── demo.py               # Demo generation commands
│   ├── skill.py              # Skill management commands
│   ├── insight.py            # Insight emission/query commands
│   ├── knowledge.py          # Knowledge graph commands
│   ├── rbac.py               # RBAC management commands
│   ├── value.py              # Value tracking commands
│   ├── dashboards.py         # Dashboard provisioning commands
│   ├── ops.py                # Operations commands (doctor, backup, etc.)
│   └── install.py            # Installation verification commands
│
├── cli.py                    # DEPRECATED: Thin wrapper for backwards compatibility
```

---

## Module Specifications

### 1. `cli/__init__.py` - Entry Point (~50 lines)

```python
"""ContextCore CLI - Manage ProjectContext resources and track tasks as spans."""

import click

from .core import create, annotate, generate, controller
from .sync import sync
from .task import task
from .sprint import sprint
from .metrics import metrics
from .git import git
from .demo import demo
from .skill import skill
from .insight import insight
from .knowledge import knowledge
from .rbac import rbac
from .value import value
from .dashboards import dashboards
from .ops import ops
from .install import install


@click.group()
@click.version_option()
def main():
    """ContextCore - Unified metadata from project to operations."""
    pass


# Register command groups
main.add_command(create)
main.add_command(annotate)
main.add_command(generate)
main.add_command(controller)
main.add_command(sync)
main.add_command(task)
main.add_command(sprint)
main.add_command(metrics)
main.add_command(git)
main.add_command(demo)
main.add_command(skill)
main.add_command(insight)
main.add_command(knowledge)
main.add_command(rbac)
main.add_command(value)
main.add_command(dashboards)
main.add_command(ops)
main.add_command(install)


if __name__ == "__main__":
    main()
```

### 2. `cli/_common.py` - Shared Utilities (~100 lines)

```python
"""Shared utilities for CLI commands."""

from typing import Any, Optional
import click
import json
import yaml


def output_data(data: Any, format: str = "yaml"):
    """Output data in specified format."""
    if format == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(yaml.dump(data, default_flow_style=False))


def echo_error(message: str):
    """Echo error message to stderr."""
    click.echo(click.style(f"Error: {message}", fg="red"), err=True)


def echo_success(message: str):
    """Echo success message."""
    click.echo(click.style(message, fg="green"))


def echo_warning(message: str):
    """Echo warning message."""
    click.echo(click.style(f"Warning: {message}", fg="yellow"))


# Common option decorators
def project_option(default: str = "default"):
    """Common --project option."""
    return click.option(
        "--project", "-p",
        envvar="CONTEXTCORE_PROJECT",
        default=default,
        help="Project identifier"
    )


def namespace_option(default: str = "default"):
    """Common --namespace option."""
    return click.option(
        "--namespace", "-ns",
        default=default,
        help="Kubernetes namespace"
    )


def tempo_url_option():
    """Common --tempo-url option."""
    return click.option(
        "--tempo-url",
        envvar="TEMPO_URL",
        default="http://localhost:3200",
        help="Tempo URL"
    )


def output_format_option(choices=("yaml", "json"), default="yaml"):
    """Common --output format option."""
    return click.option(
        "--output", "-o",
        type=click.Choice(choices),
        default=default,
        help="Output format"
    )
```

### 3. `cli/_generators.py` - Observability Generators (~180 lines)

Contains the helper functions currently embedded in cli.py:
- `generate_service_monitor()`
- `generate_prometheus_rule()`
- `generate_dashboard()`

These are pure functions that generate Kubernetes manifest dictionaries.

### 4. Command Modules Pattern

Each command module follows this pattern:

```python
"""ContextCore CLI - <Group Name> commands."""

import click
from ._common import project_option, output_data, echo_error


@click.group()
def <group_name>():
    """<Group description>."""
    pass


@<group_name>.command("subcommand")
@project_option()
@click.option("--specific-option", help="...")
def subcommand(project: str, specific_option: str):
    """Subcommand description."""
    # Lazy import to avoid circular deps and improve startup time
    from contextcore.some_module import SomeClass

    # Implementation
    ...
```

---

## Migration Steps

### Phase 1: Setup Structure (No Behavioral Changes)

1. **Create directory structure**
   ```bash
   mkdir -p src/contextcore/cli
   touch src/contextcore/cli/__init__.py
   touch src/contextcore/cli/_common.py
   touch src/contextcore/cli/_generators.py
   ```

2. **Extract helper functions to `_generators.py`**
   - `_generate_service_monitor()` (lines 269-309)
   - `_generate_prometheus_rule()` (lines 310-375)
   - `_generate_dashboard()` (lines 376-438)

3. **Create `_common.py`** with shared utilities

4. **Update `pyproject.toml`** entry point:
   ```toml
   [project.scripts]
   contextcore = "contextcore.cli:main"
   ```

### Phase 2: Extract Command Modules (One at a Time)

Extract in order of isolation (least dependencies first):

1. **`sync.py`** - 38 lines, minimal dependencies
2. **`sprint.py`** - 79 lines, uses tracker
3. **`metrics.py`** - 189 lines, uses tracker
4. **`install.py`** - 229 lines, standalone
5. **`ops.py`** - 287 lines, standalone
6. **`rbac.py`** - 239 lines, uses rbac module
7. **`dashboards.py`** - 238 lines, uses grafana module
8. **`task.py`** - 229 lines, uses tracker
9. **`git.py`** - 218 lines, uses tracker + parse helpers
10. **`demo.py`** - 276 lines, uses multiple modules
11. **`value.py`** - 297 lines, uses agent module
12. **`skill.py`** - 305 lines, uses agent module
13. **`insight.py`** - 247 lines, uses agent module
14. **`knowledge.py`** - 402 lines, uses agent module
15. **`core.py`** - 175 lines, uses generators + kubectl

### Phase 3: Create Backwards Compatibility Wrapper

Replace original `cli.py` with thin wrapper:

```python
"""Backwards compatibility wrapper - use contextcore.cli instead."""

import warnings
warnings.warn(
    "Importing from contextcore.cli is deprecated. "
    "Use 'from contextcore.cli import main' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from contextcore.cli import main

if __name__ == "__main__":
    main()
```

### Phase 4: Verification

1. Run existing tests
2. Manual smoke tests:
   ```bash
   contextcore --help
   contextcore task --help
   contextcore ops doctor
   contextcore install verify
   ```
3. Update any documentation referencing file paths

---

## Benefits

### For Human Developers
- **Focused editing**: Each file has single responsibility (~100-400 lines)
- **Easier navigation**: Find commands by filename
- **Reduced merge conflicts**: Parallel work on different command groups
- **Clear ownership**: Command groups can be owned by different teams

### For AI Agents
- **Context window efficiency**: Read only relevant module (~300 lines vs 3,837)
- **Targeted modifications**: Change one command without loading others
- **Clearer dependencies**: Explicit imports show relationships
- **Better pattern matching**: Consistent module structure aids understanding

### For CI/CD
- **Parallel testing**: Test modules independently
- **Incremental rebuilds**: Changed module = faster builds
- **Code coverage**: Per-module coverage metrics

---

## Dependency Graph

```
cli/__init__.py
    ├── _common.py (utilities)
    ├── _generators.py (pure functions)
    │
    ├── core.py ─────────────> _generators.py
    ├── sync.py
    ├── task.py ─────────────> _common.py (tracker utils)
    ├── sprint.py ───────────> _common.py (tracker utils)
    ├── metrics.py ──────────> _common.py (tracker utils)
    ├── git.py ──────────────> _common.py (parse_task_refs)
    ├── demo.py
    ├── skill.py ────────────> _common.py (agent utils)
    ├── insight.py ──────────> _common.py (agent utils)
    ├── knowledge.py ────────> _common.py (agent utils)
    ├── rbac.py
    ├── value.py ────────────> _common.py (agent utils)
    ├── dashboards.py
    ├── ops.py
    └── install.py
```

---

## Estimated Effort

| Phase | Effort | Risk |
|-------|--------|------|
| Phase 1: Setup | 30 min | Low |
| Phase 2: Extract modules | 2-3 hours | Medium |
| Phase 3: Compatibility | 15 min | Low |
| Phase 4: Verification | 30 min | Low |

**Total: ~4 hours**

---

## Testing Strategy

### Unit Tests
- Test each module independently
- Mock external dependencies (kubectl, API calls)
- Use Click's testing utilities (`CliRunner`)

### Integration Tests
- Test command registration in `__init__.py`
- Verify all subcommands accessible via main group
- Test cross-module interactions (e.g., task + git)

### Example Test Structure
```
tests/
├── cli/
│   ├── test_core.py
│   ├── test_task.py
│   ├── test_git.py
│   └── ...
```

---

## Rollback Plan

If issues arise:
1. Revert to original `cli.py` by restoring from git
2. Entry point in `pyproject.toml` still works (points to same `main()`)
3. No external API changes - only internal restructuring

---

## Success Criteria

1. **All CLI commands work identically** to before modularization
2. **Startup time unchanged** (lazy imports preserved)
3. **No new dependencies** added
4. **Each module < 400 lines**
5. **Tests pass** (once tests exist)
6. **AI agents can modify single module** without loading full CLI

---

## Future Enhancements (Out of Scope)

- Auto-generated documentation from docstrings
- Shell completion scripts per module
- Plugin architecture for third-party commands
- Interactive mode using prompt_toolkit
