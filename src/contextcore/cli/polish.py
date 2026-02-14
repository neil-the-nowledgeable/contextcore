import click
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

class PolishResult:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.suggestions: List[str] = []
        self.warnings: List[str] = []

    def add_suggestion(self, message: str):
        self.suggestions.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)

    @property
    def has_issues(self) -> bool:
        return bool(self.suggestions or self.warnings)

def check_plan_overview(content: str, result: PolishResult):
    """
    Check 1: Overview Section Existence
    Check 2: Overview Content (Objectives & Goals)
    """
    # Check 1: Overview Section Existence
    # Look for # Overview or ## Overview (case-insensitive)
    overview_match = re.search(r'^#{1,3}\s+Overview', content, re.IGNORECASE | re.MULTILINE)
    
    if not overview_match:
        result.add_suggestion("Missing 'Overview' section. Add a section describing the high-level purpose.")
        return

    # Check 2: Overview Content
    # Extract text under Overview until the next header
    start_pos = overview_match.end()
    remaining_content = content[start_pos:]
    
    # Find next header to limit scope
    next_header_match = re.search(r'^#{1,3}\s+', remaining_content, re.MULTILINE)
    if next_header_match:
        overview_text = remaining_content[:next_header_match.start()]
    else:
        overview_text = remaining_content

    # Check for Objectives
    if not re.search(r'\bObjectives?\b', overview_text, re.IGNORECASE):
        result.add_suggestion("The 'Overview' section is missing 'Objectives'. Explicitly mention the objectives of this plan.")

    # Check for Goals
    if not re.search(r'\bGoals?\b', overview_text, re.IGNORECASE):
        result.add_suggestion("The 'Overview' section is missing 'Goals'. Explicitly mention the goals for completion.")

def polish_file(file_path: Path) -> Optional[PolishResult]:
    """Applies polish rules to a single file."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        # If we can't read it (e.g. binary), just skip for now or return error
        return None

    result = PolishResult(str(file_path))
    
    # Simple heuristic: if it looks like a plan (markdown file), check overview
    if file_path.suffix.lower() in ['.md', '.markdown']:
        check_plan_overview(content, result)
        
    return result if result.has_issues else None

@click.command()
@click.argument('target', type=click.Path(exists=True, file_okay=True, dir_okay=True))
@click.option('--strict', is_flag=True, help="Exit with non-zero code if suggestions exist.")
@click.option('--format', 'output_format', type=click.Choice(['text', 'json']), default='text', help="Output format.")
def polish(target, strict, output_format):
    """[EXPERIMENTAL] Advisory step to polish artifacts for better output quality."""
    
    if output_format == 'text':
        click.echo(click.style("⚠️  EXPERIMENTAL: This command is not yet officially part of the pipeline.\n", fg="yellow"))

    target_path = Path(target)
    results = []

    if target_path.is_file():
        res = polish_file(target_path)
        if res:
            results.append(res)
    else:
        for root, _, files in os.walk(target_path):
            for file in files:
                file_path = Path(root) / file
                # Only check markdown files for now
                if file_path.suffix.lower() in ['.md', '.markdown']:
                    res = polish_file(file_path)
                    if res:
                        results.append(res)

    if output_format == 'json':
        import json
        output = [
            {
                "file": r.file_path,
                "suggestions": r.suggestions,
                "warnings": r.warnings
            }
            for r in results
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        if not results:
            click.echo(click.style("✨ All polished! No issues found.", fg="green"))
        else:
            for r in results:
                click.echo(click.style(f"\n[SUGGESTION] {r.file_path}", fg="yellow", bold=True))
                for s in r.suggestions:
                    click.echo(f"  - {s}")
                for w in r.warnings:
                    click.echo(click.style(f"  ! {w}", fg="red"))
            click.echo("") # trailing newline

    if strict and results:
        ctx = click.get_current_context()
        ctx.exit(1)
