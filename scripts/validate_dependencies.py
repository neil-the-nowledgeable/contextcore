#!/usr/bin/env python3
"""Validate that all dashboard datasource dependencies are declared in the manifest.

Scans Grafana dashboard JSON files for datasource type references and compares
them against the declared dependencies in grafana/provisioning/dashboards/dependencies.yaml.

Exit codes:
    0 - All dependencies are declared
    1 - Undeclared dependencies found or validation error

Usage:
    python3 scripts/validate_dependencies.py
    python3 scripts/validate_dependencies.py --verbose
    python3 scripts/validate_dependencies.py --manifest path/to/dependencies.yaml

See docs/DEPENDENCY_MANIFEST_PATTERN.md for the full pattern specification.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML is required. Install with: pip3 install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)


# Datasource types built into Grafana that never need plugin declarations.
# These are always available in any Grafana installation.
BUILTIN_DATASOURCE_TYPES = frozenset(
    {
        "grafana",
        "prometheus",
        "loki",
        "tempo",
        "elasticsearch",
        "influxdb",
        "mysql",
        "postgres",
        "graphite",
        "cloudwatch",
        "stackdriver",
        "testdata",
        "alertmanager",
        "datasource",  # Variable-based datasource reference
        "-- Dashboard --",
    }
)

# Root directory of the project (two levels up from this script)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default manifest path relative to project root
DEFAULT_MANIFEST = "grafana/provisioning/dashboards/dependencies.yaml"

# Directories to scan for dashboard JSON files, relative to project root
DASHBOARD_DIRS = [
    "grafana/provisioning/dashboards",
]


def load_manifest(manifest_path: Path) -> dict:
    """Load and parse the dependency manifest YAML file."""
    if not manifest_path.exists():
        print(
            f"ERROR: Dependency manifest not found: {manifest_path}",
            file=sys.stderr,
        )
        print(
            "  Create it with declared dependencies or run: contextcore deps generate",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    if not manifest:
        print(f"ERROR: Empty manifest: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    return manifest


def get_declared_datasource_types(manifest: dict) -> set[str]:
    """Extract all declared datasource types from the manifest.

    Returns the set of datasource types that are explicitly declared,
    combining both plugin IDs and datasource type entries.
    """
    declared = set()

    spec = manifest.get("spec", {})

    # Collect plugin IDs (these are also valid datasource types)
    for plugin in spec.get("plugins", []):
        plugin_id = plugin.get("id")
        if plugin_id:
            declared.add(plugin_id)

    # Collect datasource types
    for ds in spec.get("datasources", []):
        ds_type = ds.get("type")
        if ds_type:
            declared.add(ds_type)

    return declared


def get_manifest_builtin_types(manifest: dict) -> set[str]:
    """Extract the builtin_datasource_types allow-list from the manifest validation section."""
    validation = manifest.get("validation", {})
    builtin = validation.get("builtin_datasource_types", [])
    return set(builtin)


def get_ignore_patterns(manifest: dict) -> list[str]:
    """Extract file ignore patterns from the manifest validation section."""
    validation = manifest.get("validation", {})
    return validation.get("ignore_patterns", [])


def extract_datasource_types(obj, types: set[str] | None = None) -> set[str]:
    """Recursively extract all datasource type references from a JSON object.

    Looks for objects matching the pattern:
        {"datasource": {"type": "<type>", ...}}

    at any nesting depth within the JSON structure.
    """
    if types is None:
        types = set()

    if isinstance(obj, dict):
        # Check if this dict has a "datasource" key with a nested "type"
        ds = obj.get("datasource")
        if isinstance(ds, dict):
            ds_type = ds.get("type")
            if isinstance(ds_type, str) and ds_type:
                types.add(ds_type)

        # Recurse into all values
        for value in obj.values():
            extract_datasource_types(value, types)

    elif isinstance(obj, list):
        for item in obj:
            extract_datasource_types(item, types)

    return types


def should_ignore(filepath: Path, ignore_patterns: list[str]) -> bool:
    """Check whether a file matches any of the ignore patterns."""
    name = filepath.name
    for pattern in ignore_patterns:
        # Simple glob matching: strip directory prefix patterns
        clean_pattern = pattern.lstrip("**/")
        if clean_pattern.startswith("*"):
            # Suffix match, e.g., "**/test-*.json" -> starts with "test-"
            suffix = clean_pattern[1:]
            prefix = ""
            if "-" in suffix:
                prefix = suffix.split("-")[0] + "-"
                # Check if name starts with the prefix pattern
                if name.startswith(prefix):
                    return True
            # Also try fnmatch-style
            import fnmatch

            if fnmatch.fnmatch(name, clean_pattern):
                return True
        else:
            if name == clean_pattern:
                return True

    return False


def find_dashboard_files(
    dashboard_dirs: list[str], ignore_patterns: list[str]
) -> list[Path]:
    """Find all dashboard JSON files in the given directories."""
    files = []
    for dir_rel in dashboard_dirs:
        dir_path = PROJECT_ROOT / dir_rel
        if not dir_path.exists():
            continue
        for json_file in sorted(dir_path.rglob("*.json")):
            if should_ignore(json_file, ignore_patterns):
                continue
            files.append(json_file)
    return files


def validate(
    manifest_path: Path,
    dashboard_dirs: list[str],
    verbose: bool = False,
) -> bool:
    """Run dependency validation. Returns True if all dependencies are declared."""
    manifest = load_manifest(manifest_path)
    declared_types = get_declared_datasource_types(manifest)
    manifest_builtins = get_manifest_builtin_types(manifest)
    ignore_patterns = get_ignore_patterns(manifest)

    # Combine built-in allow-lists: the hardcoded set plus manifest-declared builtins
    allowed_types = BUILTIN_DATASOURCE_TYPES | manifest_builtins | declared_types

    if verbose:
        print(f"Manifest: {manifest_path}")
        print(f"Declared datasource types: {sorted(declared_types)}")
        print(f"Manifest builtin types: {sorted(manifest_builtins)}")
        print(f"Ignore patterns: {ignore_patterns}")
        print()

    dashboard_files = find_dashboard_files(dashboard_dirs, ignore_patterns)

    if not dashboard_files:
        print("WARNING: No dashboard JSON files found to validate.", file=sys.stderr)
        return True

    if verbose:
        print(f"Scanning {len(dashboard_files)} dashboard files...")
        print()

    errors: list[str] = []
    all_types_found: dict[str, set[str]] = {}  # type -> set of files using it

    for filepath in dashboard_files:
        try:
            with open(filepath) as f:
                dashboard = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"  {filepath.name}: Invalid JSON - {e}")
            continue

        types_in_file = extract_datasource_types(dashboard)
        rel_path = filepath.relative_to(PROJECT_ROOT)

        if verbose:
            if types_in_file:
                print(f"  {rel_path}: {sorted(types_in_file)}")

        for ds_type in types_in_file:
            if ds_type not in all_types_found:
                all_types_found[ds_type] = set()
            all_types_found[ds_type].add(str(rel_path))

            if ds_type not in allowed_types:
                errors.append(
                    f"  {rel_path}: uses undeclared datasource type '{ds_type}'"
                )

    if verbose:
        print()
        print("All datasource types found across dashboards:")
        for ds_type in sorted(all_types_found.keys()):
            status = "DECLARED" if ds_type in allowed_types else "UNDECLARED"
            file_count = len(all_types_found[ds_type])
            print(f"  {ds_type}: {status} (used in {file_count} file(s))")
        print()

    if errors:
        print("FAILED: Undeclared datasource dependencies found:", file=sys.stderr)
        print(file=sys.stderr)
        for error in sorted(errors):
            print(error, file=sys.stderr)
        print(file=sys.stderr)
        print(
            "Fix: Add the missing datasource type to the 'spec.datasources' or",
            file=sys.stderr,
        )
        print(
            "     'spec.plugins' section in:",
            file=sys.stderr,
        )
        print(f"     {manifest_path}", file=sys.stderr)
        print(file=sys.stderr)
        print(
            "See docs/DEPENDENCY_MANIFEST_PATTERN.md for details.",
            file=sys.stderr,
        )
        return False

    file_count = len(dashboard_files)
    type_count = len(all_types_found)
    print(
        f"OK: All dependencies declared. "
        f"Scanned {file_count} dashboard(s), "
        f"found {type_count} datasource type(s)."
    )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Validate Grafana dashboard dependency declarations.",
        epilog="See docs/DEPENDENCY_MANIFEST_PATTERN.md for details.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / DEFAULT_MANIFEST,
        help=f"Path to dependency manifest (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output including per-file datasource types",
    )
    args = parser.parse_args()

    success = validate(
        manifest_path=args.manifest,
        dashboard_dirs=DASHBOARD_DIRS,
        verbose=args.verbose,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
