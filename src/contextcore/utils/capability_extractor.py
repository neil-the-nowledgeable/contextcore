"""
Capability Extractor - AST-based raw capability extraction from Python codebases.

Extracts capabilities by analyzing:
- CLI commands (Click/Typer/argparse)
- Class definitions with docstrings
- Public functions with docstrings
- Documentation headings
- Test names (as capability evidence)
- API endpoints (FastAPI/Flask routes)

Outputs:
- raw_capabilities.yaml: Structured extraction
- synthesis_prompt.md: Ready-to-use LLM prompt for Phase 2
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ExtractedCapability:
    """A single extracted capability from source code."""
    name: str
    source_type: str  # cli, class, function, doc, test, api
    file_path: str
    line_number: Optional[int] = None
    docstring: Optional[str] = None
    signature: Optional[str] = None
    decorators: list = field(default_factory=list)
    parent: Optional[str] = None  # For nested items


@dataclass
class ExtractionResult:
    """Complete extraction result from a project."""
    project_path: str
    project_name: str
    extracted_at: str
    cli_commands: list = field(default_factory=list)
    classes: list = field(default_factory=list)
    functions: list = field(default_factory=list)
    doc_sections: list = field(default_factory=list)
    tests: list = field(default_factory=list)
    api_endpoints: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'metadata': {
                'project_path': self.project_path,
                'project_name': self.project_name,
                'extracted_at': self.extracted_at,
                'total_capabilities': self.total_count(),
            },
            'cli_commands': [vars(c) for c in self.cli_commands],
            'classes': [vars(c) for c in self.classes],
            'functions': [vars(c) for c in self.functions],
            'doc_sections': [vars(c) for c in self.doc_sections],
            'tests': [vars(c) for c in self.tests],
            'api_endpoints': [vars(c) for c in self.api_endpoints],
        }

    def total_count(self) -> int:
        return (len(self.cli_commands) + len(self.classes) +
                len(self.functions) + len(self.doc_sections) +
                len(self.tests) + len(self.api_endpoints))


class CapabilityExtractor:
    """Extracts capabilities from a Python project."""

    def __init__(self, project_path: Path, project_name: Optional[str] = None):
        self.project_path = project_path
        self.project_name = project_name or project_path.name
        self.result = ExtractionResult(
            project_path=str(project_path),
            project_name=self.project_name,
            extracted_at=datetime.utcnow().isoformat() + "Z"
        )

    def extract_all(self) -> ExtractionResult:
        """Run all extraction methods."""
        print(f"Extracting capabilities from: {self.project_path}")

        # Find Python files
        py_files = list(self.project_path.rglob("*.py"))
        py_files = [f for f in py_files if not self._should_skip(f)]
        print(f"  Found {len(py_files)} Python files")

        for py_file in py_files:
            self._extract_from_python_file(py_file)

        # Find documentation files
        md_files = list(self.project_path.rglob("*.md"))
        md_files = [f for f in md_files if not self._should_skip(f)]
        print(f"  Found {len(md_files)} Markdown files")

        for md_file in md_files:
            self._extract_from_markdown(md_file)

        print(f"  Total capabilities extracted: {self.result.total_count()}")
        return self.result

    def _should_skip(self, path: Path) -> bool:
        """Skip vendor, test fixtures, and hidden directories."""
        skip_patterns = [
            'venv', 'env', '.venv', '__pycache__',
            'node_modules', '.git', 'dist', 'build',
            '.egg-info', 'site-packages'
        ]
        return any(p in path.parts for p in skip_patterns)

    def _extract_from_python_file(self, file_path: Path):
        """Extract capabilities from a single Python file."""
        try:
            source = file_path.read_text(encoding='utf-8')
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"    Skipping {file_path}: {e}")
            return

        relative_path = str(file_path.relative_to(self.project_path))

        for node in ast.walk(tree):
            # Extract CLI commands (Click decorators)
            if isinstance(node, ast.FunctionDef):
                self._check_cli_command(node, relative_path)
                self._check_api_endpoint(node, relative_path)
                self._check_public_function(node, relative_path)
                self._check_test_function(node, relative_path, file_path)

            # Extract classes
            elif isinstance(node, ast.ClassDef):
                self._extract_class(node, relative_path)

    def _check_cli_command(self, node: ast.FunctionDef, file_path: str):
        """Check if function is a CLI command (Click/Typer)."""
        cli_decorators = ['command', 'group', 'cli', 'app.command', 'main']

        for decorator in node.decorator_list:
            decorator_name = self._get_decorator_name(decorator)
            if any(cli in decorator_name.lower() for cli in cli_decorators):
                cap = ExtractedCapability(
                    name=node.name,
                    source_type='cli',
                    file_path=file_path,
                    line_number=node.lineno,
                    docstring=ast.get_docstring(node),
                    signature=self._get_function_signature(node),
                    decorators=[decorator_name]
                )
                self.result.cli_commands.append(cap)
                return

    def _check_api_endpoint(self, node: ast.FunctionDef, file_path: str):
        """Check if function is an API endpoint (FastAPI/Flask)."""
        api_decorators = ['get', 'post', 'put', 'delete', 'patch', 'route', 'api_route']

        for decorator in node.decorator_list:
            decorator_name = self._get_decorator_name(decorator)
            if any(api in decorator_name.lower() for api in api_decorators):
                # Extract route path if available
                route_path = self._extract_route_path(decorator)
                cap = ExtractedCapability(
                    name=node.name,
                    source_type='api',
                    file_path=file_path,
                    line_number=node.lineno,
                    docstring=ast.get_docstring(node),
                    signature=route_path or self._get_function_signature(node),
                    decorators=[decorator_name]
                )
                self.result.api_endpoints.append(cap)
                return

    def _check_public_function(self, node: ast.FunctionDef, file_path: str):
        """Extract public functions (not starting with _)."""
        # Skip private, dunder, and already-captured functions
        if node.name.startswith('_'):
            return

        # Skip if already captured as CLI or API
        existing_names = (
            [c.name for c in self.result.cli_commands] +
            [c.name for c in self.result.api_endpoints]
        )
        if node.name in existing_names:
            return

        # Only include if it has a docstring (indicates intentional public API)
        docstring = ast.get_docstring(node)
        if not docstring:
            return

        cap = ExtractedCapability(
            name=node.name,
            source_type='function',
            file_path=file_path,
            line_number=node.lineno,
            docstring=docstring,
            signature=self._get_function_signature(node)
        )
        self.result.functions.append(cap)

    def _check_test_function(self, node: ast.FunctionDef, file_path: str, full_path: Path):
        """Extract test functions as capability evidence."""
        if not (node.name.startswith('test_') or 'test' in full_path.name.lower()):
            return

        cap = ExtractedCapability(
            name=node.name,
            source_type='test',
            file_path=file_path,
            line_number=node.lineno,
            docstring=ast.get_docstring(node)
        )
        self.result.tests.append(cap)

    def _extract_class(self, node: ast.ClassDef, file_path: str):
        """Extract class definition."""
        # Skip private classes
        if node.name.startswith('_'):
            return

        docstring = ast.get_docstring(node)

        # Get base classes
        bases = [self._get_name(base) for base in node.bases]

        # Get public methods
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and not item.name.startswith('_'):
                methods.append(item.name)

        cap = ExtractedCapability(
            name=node.name,
            source_type='class',
            file_path=file_path,
            line_number=node.lineno,
            docstring=docstring,
            signature=f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}",
            decorators=methods[:10]  # Store first 10 public methods
        )
        self.result.classes.append(cap)

    def _extract_from_markdown(self, file_path: Path):
        """Extract documentation sections from markdown."""
        try:
            content = file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            return

        relative_path = str(file_path.relative_to(self.project_path))

        # Find all headings
        heading_pattern = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)

        for match in heading_pattern.finditer(content):
            level = len(match.group(1))
            title = match.group(2).strip()

            # Skip generic headings
            skip_titles = ['table of contents', 'toc', 'contents', 'index',
                          'license', 'contributing', 'changelog']
            if title.lower() in skip_titles:
                continue

            # Calculate line number
            line_num = content[:match.start()].count('\n') + 1

            cap = ExtractedCapability(
                name=title,
                source_type='doc',
                file_path=relative_path,
                line_number=line_num,
                signature=f"{'#' * level} {title}"
            )
            self.result.doc_sections.append(cap)

    def _get_decorator_name(self, decorator) -> str:
        """Get the name of a decorator."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return f"{self._get_name(decorator.value)}.{decorator.attr}"
        elif isinstance(decorator, ast.Call):
            return self._get_decorator_name(decorator.func)
        return "unknown"

    def _get_name(self, node) -> str:
        """Get name from various AST node types."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        return "unknown"

    def _get_function_signature(self, node: ast.FunctionDef) -> str:
        """Get function signature."""
        args = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)

        sig = f"def {node.name}({', '.join(args)})"
        if node.returns:
            sig += f" -> {ast.unparse(node.returns)}"
        return sig

    def _extract_route_path(self, decorator) -> Optional[str]:
        """Extract route path from API decorator."""
        if isinstance(decorator, ast.Call) and decorator.args:
            first_arg = decorator.args[0]
            if isinstance(first_arg, ast.Constant):
                return str(first_arg.value)
        return None


def generate_synthesis_prompt(result: ExtractionResult, output_path: Path) -> Path:
    """Generate the Phase 2 LLM synthesis prompt."""

    # Build capability summary
    cli_summary = "\n".join([
        f"  - `{c.name}`: {(c.docstring or 'No description')[:100]}"
        for c in result.cli_commands[:20]
    ]) or "  (none found)"

    class_summary = "\n".join([
        f"  - `{c.name}`: {(c.docstring or 'No description')[:100]}"
        for c in result.classes[:20]
    ]) or "  (none found)"

    function_summary = "\n".join([
        f"  - `{c.name}`: {(c.docstring or 'No description')[:100]}"
        for c in result.functions[:20]
    ]) or "  (none found)"

    api_summary = "\n".join([
        f"  - `{c.signature or c.name}`: {(c.docstring or 'No description')[:100]}"
        for c in result.api_endpoints[:20]
    ]) or "  (none found)"

    doc_summary = "\n".join([
        f"  - {c.signature} ({c.file_path})"
        for c in result.doc_sections[:30]
    ]) or "  (none found)"

    test_capabilities = set()
    for t in result.tests:
        # Extract capability name from test name (test_foo_bar -> foo_bar)
        name = t.name.replace('test_', '').replace('_', ' ')
        test_capabilities.add(name)
    test_summary = "\n".join([f"  - {c}" for c in sorted(test_capabilities)[:20]]) or "  (none found)"

    prompt = f'''# Phase 2: User-Facing Capability Synthesis

## Project Information

- **Project:** {result.project_name}
- **Path:** {result.project_path}
- **Extracted:** {result.extracted_at}
- **Total raw capabilities:** {result.total_count()}

---

## Extracted Capabilities

### CLI Commands ({len(result.cli_commands)})
{cli_summary}

### Classes ({len(result.classes)})
{class_summary}

### Public Functions ({len(result.functions)})
{function_summary}

### API Endpoints ({len(result.api_endpoints)})
{api_summary}

### Documentation Sections ({len(result.doc_sections)})
{doc_summary}

### Test Coverage (capabilities with tests) ({len(test_capabilities)})
{test_summary}

---

## Synthesis Task

Based on the extracted capabilities above, create **3-7 user-facing capability categories**.

### Requirements

1. **Group by user value, not code structure**
   - Bad: "TaskTracker Features", "CLI Commands"
   - Good: "Eliminate Manual Status Reporting", "Real-Time Project Visibility"

2. **Name categories in user language**
   - Users don't care about class names
   - Focus on problems solved and outcomes achieved

3. **For each category, provide:**
   - Category name (user-facing)
   - User pain it solves (1-2 sentences)
   - Capabilities included (from extraction above)
   - Primary persona(s) who benefit
   - Measurable outcome

4. **Identify gaps**
   - What user needs are NOT covered by current capabilities?
   - What's technically present but not user-ready?

### Output Format

```yaml
user_facing_categories:
  - name: "[User-Facing Category Name]"
    pain_point: "[What frustrates users today]"
    solution: "[How this category solves it]"
    measurable_outcome: "[How users know it's working]"
    personas: [developer, pm, leader, operator, compliance, agent]
    capabilities:
      - name: "[extracted capability name]"
        source: "[cli|class|function|api]"
        user_description: "[What this does for the user]"
    maturity: draft|beta|stable

gaps_identified:
  - description: "[Missing capability]"
    user_need: "[Why users need this]"
    recommendation: "[How to address]"

synthesis_notes:
  - "[Any observations about the codebase]"
  - "[Patterns noticed]"
  - "[Recommendations]"
```

---

## Personas Reference

| Persona | Primary Concern |
|---------|-----------------|
| **Developer** | No context switching, code-first workflow |
| **Project Manager** | Accurate real-time data, no manual reporting |
| **Engineering Leader** | Portfolio visibility, resource allocation |
| **Operator** | Incident context, quick triage |
| **Compliance** | Audit trail, evidence, history |
| **AI Agent** | Persistent memory, constraint awareness |

---

## Anti-Patterns to Avoid

- **Technical naming**: "TaskTracker Module" -> "Automatic Status Updates"
- **Feature listing**: Don't just list features, group by outcome
- **Internal focus**: "We have X" -> "Users can Y"
- **Maturity inflation**: If it's CLI-only with no docs, it's beta at best

---

Please synthesize the extracted capabilities into user-facing categories.
'''

    prompt_path = output_path / "synthesis_prompt.md"
    prompt_path.write_text(prompt)
    print(f"  Generated synthesis prompt: {prompt_path}")
    return prompt_path


def run_extraction(
    project_path: Path,
    output_dir: Path,
    project_name: Optional[str] = None,
) -> ExtractionResult:
    """Run a full extraction and write outputs.

    This is the main entry point for CLI integration.
    """
    extractor = CapabilityExtractor(project_path, project_name)
    result = extractor.extract_all()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write raw capabilities YAML
    yaml_path = output_dir / "raw_capabilities.yaml"
    with open(yaml_path, 'w') as f:
        yaml.dump(result.to_dict(), f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"  Wrote raw capabilities: {yaml_path}")

    # Generate synthesis prompt
    generate_synthesis_prompt(result, output_dir)

    return result
