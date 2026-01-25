#!/usr/bin/env python3
"""
Import Dashboard & Persistence features into the Prime Contractor queue.

This script adds all 9 dashboard-persistence features to the Prime Contractor
queue, with proper dependencies and descriptions, ready for execution.

Usage:
    python3 scripts/prime_contractor/import_dashboard_persistence.py

    # Then run the workflow:
    python3 scripts/prime_contractor/cli.py run
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.prime_contractor.feature_queue import FeatureQueue


# Dashboard & Persistence Features
FEATURES = [
    # Phase 1-3 (Foundation)
    {
        "id": "dp_phase1_folder_structure",
        "name": "Dashboard Folder Structure",
        "description": """Reorganize dashboards from flat json/ folder into extension-specific folders.

Create: grafana/provisioning/dashboards/{core,squirrel,rabbit,beaver,fox,coyote,external}/
Move dashboards to correct folders and update UIDs to contextcore-{extension}-{name} format.""",
        "dependencies": [],
        "target_files": [
            "grafana/provisioning/dashboards/core/",
            "grafana/provisioning/dashboards/squirrel/",
            "grafana/provisioning/dashboards/rabbit/",
        ],
    },
    {
        "id": "dp_phase2_grafana_config",
        "name": "Grafana Multi-Provider Config",
        "description": """Update Grafana provisioning to auto-load from multiple extension folders.

Create dashboards.yaml with multiple providers, one per extension, each with its own Grafana folder.""",
        "dependencies": ["dp_phase1_folder_structure"],
        "target_files": [
            "grafana/provisioning/dashboards/dashboards.yaml",
        ],
    },
    {
        "id": "dp_phase3_discovery_module",
        "name": "Discovery Module",
        "description": """Create Python module for auto-discovering dashboards from filesystem and entry points.

Implement: EXTENSION_REGISTRY, discover_from_filesystem(), discover_from_entry_points(), discover_all_dashboards()""",
        "dependencies": ["dp_phase1_folder_structure"],
        "target_files": [
            "src/contextcore/dashboards/discovery.py",
        ],
    },
    # Phase 4-6 (Integration)
    {
        "id": "dp_phase4_provisioner_update",
        "name": "Provisioner Update",
        "description": """Integrate the discovery module into the existing DashboardProvisioner.

Remove DEFAULT_DASHBOARDS, use discovery module, add extension filtering.""",
        "dependencies": ["dp_phase3_discovery_module"],
        "target_files": [
            "src/contextcore/dashboards/provisioner.py",
        ],
    },
    {
        "id": "dp_phase5_cli_enhancements",
        "name": "CLI Enhancements",
        "description": """Add extension filtering and new commands to dashboard CLI.

Add --extension flag, --source flag, and new 'extensions' command.""",
        "dependencies": ["dp_phase4_provisioner_update"],
        "target_files": [
            "src/contextcore/cli/dashboards.py",
        ],
    },
    {
        "id": "dp_phase6_persistence_detector",
        "name": "Persistence Detector",
        "description": """Create module to detect what data needs persistence and derive importance.

Scan docker-compose, tempo/loki/mimir configs, state directory, and .contextcore.yaml.""",
        "dependencies": [],  # Independent of dashboard work
        "target_files": [
            "src/contextcore/persistence/__init__.py",
            "src/contextcore/persistence/detector.py",
            "src/contextcore/persistence/models.py",
        ],
    },
    # Phase 7-9 (Protection)
    {
        "id": "dp_phase7_pre_destroy_warning",
        "name": "Pre-Destroy Warning",
        "description": """Enhance make destroy with data inventory and export options.

Add persistence CLI commands and update Makefile with data-inventory target.""",
        "dependencies": ["dp_phase6_persistence_detector"],
        "target_files": [
            "src/contextcore/cli/persistence.py",
            "Makefile",
        ],
    },
    {
        "id": "dp_phase8_telemetry_exporter",
        "name": "Telemetry Exporter",
        "description": """Export actual trace, metric, and log data (not just dashboards).

Query Tempo, Mimir, Loki APIs and save to backup directory.""",
        "dependencies": ["dp_phase7_pre_destroy_warning"],
        "target_files": [
            "src/contextcore/persistence/exporter.py",
        ],
    },
    {
        "id": "dp_phase9_audit_trail",
        "name": "Audit Trail",
        "description": """Record all destructive operations for accountability.

Store audit events in ~/.contextcore/audit.log and optionally push to Loki.""",
        "dependencies": ["dp_phase7_pre_destroy_warning"],
        "target_files": [
            "src/contextcore/persistence/audit.py",
        ],
    },
]


def main():
    print("\n" + "=" * 70)
    print("Import Dashboard & Persistence Features")
    print("=" * 70)

    queue = FeatureQueue()

    # Check for existing features
    existing = set(queue.features.keys())
    dp_features = {f["id"] for f in FEATURES}

    overlap = existing & dp_features
    if overlap:
        print(f"\nFound {len(overlap)} existing features:")
        for fid in overlap:
            feature = queue.features[fid]
            print(f"  - {fid}: {feature.status.value}")

        response = input("\nOverwrite existing features? (yes/no): ")
        if response.lower() not in ("yes", "y"):
            print("Cancelled")
            return

    # Add features
    added = 0
    for spec in FEATURES:
        queue.add_feature(
            feature_id=spec["id"],
            name=spec["name"],
            description=spec["description"],
            dependencies=spec.get("dependencies", []),
            target_files=spec.get("target_files", []),
        )
        added += 1
        print(f"  + {spec['name']}")

    print(f"\n✓ Added {added} features to Prime Contractor queue")

    # Show execution order
    print("\nExecution Order (based on dependencies):")
    print("  Phase 1-3:")
    print("    1. dp_phase1_folder_structure")
    print("    2. dp_phase2_grafana_config (depends on 1)")
    print("    3. dp_phase3_discovery_module (depends on 1)")
    print("  Phase 4-6:")
    print("    4. dp_phase4_provisioner_update (depends on 3)")
    print("    5. dp_phase5_cli_enhancements (depends on 4)")
    print("    6. dp_phase6_persistence_detector (independent)")
    print("  Phase 7-9:")
    print("    7. dp_phase7_pre_destroy_warning (depends on 6)")
    print("    8. dp_phase8_telemetry_exporter (depends on 7)")
    print("    9. dp_phase9_audit_trail (depends on 7)")

    print("\nNext steps:")
    print("  1. Review queue: python3 scripts/prime_contractor/cli.py status")
    print("  2. Dry run:      python3 scripts/prime_contractor/cli.py run --dry-run")
    print("  3. Execute:      python3 scripts/prime_contractor/cli.py run")


if __name__ == "__main__":
    main()
