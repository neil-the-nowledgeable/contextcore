"""
Dashboard & Persistence Architecture Tasks.

Phases 1-3: Dashboard organization, Grafana config, discovery module
Phases 4-6: Provisioner update, CLI enhancements, persistence detector
Phases 7-9: Pre-destroy warnings, telemetry export, audit trail
"""

from ..runner import Feature


# =============================================================================
# Phase 1: Dashboard Folder Structure
# =============================================================================

PHASE1_FOLDER_STRUCTURE_TASK = """
Reorganize ContextCore dashboards from flat json/ folder into extension-specific folders.

## Goal
Create organized folder structure for dashboards by extension package.

## Context
- Current location: grafana/provisioning/dashboards/json/ (flat, 9 dashboards)
- Target: Organized by extension (core/, squirrel/, rabbit/, beaver/, fox/, coyote/, external/)

## Requirements

1. Create the following folder structure:
   ```
   grafana/provisioning/dashboards/
   ├── core/                        # Core ContextCore dashboards
   ├── squirrel/                    # Skills library (contextcore-squirrel)
   ├── rabbit/                      # Alert automation (contextcore-rabbit)
   ├── beaver/                      # LLM provider (contextcore-beaver)
   ├── fox/                         # Context enrichment (contextcore-fox)
   ├── coyote/                      # Incident resolution (contextcore-coyote)
   └── external/                    # Third-party/experimental
   ```

2. Move dashboards to correct folders:
   - core/: portfolio.json, installation.json, project-progress.json, project-operations.json, sprint-metrics.json
   - squirrel/: skills-browser.json, value-capabilities.json
   - rabbit/: workflow.json
   - external/: agent-trigger.json

3. Update dashboard UIDs in JSON files to follow new convention:
   - Format: contextcore-{extension}-{name}
   - Examples: contextcore-core-portfolio, contextcore-squirrel-skills-browser

## Output Format
Bash script that:
1. Creates the folder structure
2. Moves files with git mv
3. Uses sed to update UIDs in JSON files
4. Verifies the result
"""

PHASE1_FEATURES = [
    Feature(
        task=PHASE1_FOLDER_STRUCTURE_TASK,
        name="DashPersist_FolderStructure",
        output_subdir="dashboard_persistence/phase1",
    ),
]


# =============================================================================
# Phase 2: Grafana Multi-Provider Config
# =============================================================================

PHASE2_GRAFANA_CONFIG_TASK = """
Update Grafana provisioning to auto-load dashboards from multiple extension folders.

## Goal
Configure Grafana to scan each extension folder and organize dashboards into subfolders.

## Context
- Current: Single provider scanning json/ folder
- Target: Multiple providers, one per extension, each with its own Grafana folder

## Requirements

1. Backup existing dashboards.yaml to dashboards.yaml.bak

2. Create new dashboards.yaml with multi-provider configuration:
   ```yaml
   apiVersion: 1
   providers:
     - name: 'ContextCore Core'
       orgId: 1
       folder: 'ContextCore'
       folderUid: 'contextcore'
       type: file
       disableDeletion: false
       updateIntervalSeconds: 30
       allowUiUpdates: true
       options:
         path: /etc/grafana/provisioning/dashboards/core

     - name: 'ContextCore Squirrel'
       orgId: 1
       folder: 'ContextCore / Squirrel'
       folderUid: 'contextcore-squirrel'
       # ... similar pattern for each extension
   ```

3. Configure all extensions: core, squirrel, rabbit, beaver, fox, coyote, external

4. Key settings:
   - updateIntervalSeconds: 30 for hot-reload during development
   - allowUiUpdates: true to allow manual edits
   - Empty folders should not cause errors

## Output Format
YAML configuration file content for grafana/provisioning/dashboards/dashboards.yaml
"""

PHASE2_FEATURES = [
    Feature(
        task=PHASE2_GRAFANA_CONFIG_TASK,
        name="DashPersist_GrafanaConfig",
        output_subdir="dashboard_persistence/phase2",
    ),
]


# =============================================================================
# Phase 3: Discovery Module
# =============================================================================

PHASE3_DISCOVERY_MODULE_TASK = """
Create Python module for auto-discovering dashboards from filesystem and entry points.

## Goal
Enable automatic discovery of dashboards from extension folders and Python packages.

## Context
- Location: src/contextcore/dashboards/discovery.py
- Must work with existing DashboardConfig dataclass in provisioner.py

## Requirements

1. Create EXTENSION_REGISTRY mapping:
   ```python
   EXTENSION_REGISTRY = {
       "core": {"name": "ContextCore Core", "folder": "ContextCore", "folder_uid": "contextcore"},
       "squirrel": {"name": "Squirrel (Skills)", "folder": "ContextCore / Squirrel", "folder_uid": "contextcore-squirrel"},
       # ... all extensions
   }
   ```

2. Extend DashboardConfig dataclass with new fields:
   - extension: str = "core"
   - file_path: Optional[Path] = None
   - Add effective_file_path property

3. Implement discover_from_filesystem(extension: Optional[str] = None):
   - Scan grafana/provisioning/dashboards/{extension}/ for *.json files
   - Parse JSON to extract uid, title, description, tags
   - Yield DashboardConfig objects

4. Implement discover_from_entry_points(extension: Optional[str] = None):
   - Use importlib.metadata.entry_points(group="contextcore.dashboards")
   - Call each entry point's get_dashboards() function
   - Yield DashboardConfig objects

5. Implement discover_all_dashboards():
   - Combine filesystem and entry point sources
   - Deduplicate by UID (entry points override filesystem)
   - Return list[DashboardConfig]

6. Implement list_extensions():
   - Return list of extension info with dashboard counts

## Output Format
Python module with:
- Full type hints
- Docstrings with examples
- All functions mentioned above
"""

PHASE3_FEATURES = [
    Feature(
        task=PHASE3_DISCOVERY_MODULE_TASK,
        name="DashPersist_DiscoveryModule",
        output_subdir="dashboard_persistence/phase3",
    ),
]


# =============================================================================
# Phase 4: Provisioner Update
# =============================================================================

PHASE4_PROVISIONER_UPDATE_TASK = """
Integrate the discovery module into the existing DashboardProvisioner.

## Goal
Replace hardcoded DEFAULT_DASHBOARDS with auto-discovery.

## Context
- File: src/contextcore/dashboards/provisioner.py
- Current: DEFAULT_DASHBOARDS list with 2 dashboards
- Target: Use discovery module to find all dashboards

## Requirements

1. Add imports from discovery module:
   ```python
   from contextcore.dashboards.discovery import (
       discover_all_dashboards,
       list_extensions,
       EXTENSION_REGISTRY,
   )
   ```

2. Remove DEFAULT_DASHBOARDS list (or keep as fallback)

3. Update provision_all() method:
   - Add extension: Optional[str] = None parameter
   - If dashboards not provided, use discover_all_dashboards(extension=extension)
   - Filter by extension if specified

4. Update delete_all() method:
   - Add extension parameter
   - Use discovery to find dashboards to delete

5. Update _load_dashboard_json():
   - Use config.effective_file_path instead of computing from file_name

6. Add extension filtering throughout

## Output Format
Updated Python code for provisioner.py with all changes integrated
"""

PHASE4_FEATURES = [
    Feature(
        task=PHASE4_PROVISIONER_UPDATE_TASK,
        name="DashPersist_ProvisionerUpdate",
        output_subdir="dashboard_persistence/phase4",
    ),
]


# =============================================================================
# Phase 5: CLI Enhancements
# =============================================================================

PHASE5_CLI_ENHANCEMENTS_TASK = """
Add extension filtering and new commands to the dashboard CLI.

## Goal
Enable users to filter dashboard operations by extension.

## Context
- File: src/contextcore/cli/dashboards.py
- Current: provision, list, delete commands without filtering

## Requirements

1. Add --extension / -e flag to all commands:
   ```python
   @click.option("--extension", "-e", help="Filter by extension (core, squirrel, rabbit, etc.)")
   ```

2. Add --source flag to list command:
   - Options: local, grafana, both (default)
   - local: Only show dashboards from filesystem
   - grafana: Only show dashboards in Grafana
   - both: Show both with comparison

3. Create new "extensions" command:
   ```bash
   contextcore dashboards extensions
   ```
   Shows all known extensions with:
   - ID, name, folder, dashboard count, source

4. Update output formatting:
   - Group dashboards by extension
   - Show extension info in listings
   - Add color coding for status

5. Add examples to help text:
   ```
   contextcore dashboards provision -e core      # Core only
   contextcore dashboards list --source local    # Local files
   contextcore dashboards extensions             # List extensions
   ```

## Output Format
Updated Python code for dashboards.py CLI module
"""

PHASE5_FEATURES = [
    Feature(
        task=PHASE5_CLI_ENHANCEMENTS_TASK,
        name="DashPersist_CLIEnhancements",
        output_subdir="dashboard_persistence/phase5",
    ),
]


# =============================================================================
# Phase 6: Persistence Detector
# =============================================================================

PHASE6_PERSISTENCE_DETECTOR_TASK = """
Create module to detect what data needs persistence and derive importance.

## Goal
Automatically detect persistent data sources in ContextCore deployment.

## Context
- New module: src/contextcore/persistence/
- Must scan docker-compose, tempo/loki/mimir configs, state directory

## Requirements

1. Create persistence module structure:
   ```
   src/contextcore/persistence/
   ├── __init__.py
   ├── detector.py      # Main detection logic
   └── models.py        # DataSource, PersistenceManifest dataclasses
   ```

2. Implement DataSource dataclass:
   ```python
   @dataclass
   class DataSource:
       name: str
       path: Path
       type: str  # traces, metrics, logs, configuration, task_state
       retention: str  # e.g., "48h", "7d", "unlimited"
       api_endpoint: Optional[str] = None
       size_bytes: int = 0
       importance: str = "medium"  # critical, high, medium, low
   ```

3. Implement PersistenceDetector class with methods:
   - detect() -> PersistenceManifest
   - _scan_docker_compose() - Parse volumes from docker-compose.yaml
   - _parse_tempo_retention() - Extract from tempo/tempo.yaml
   - _parse_loki_retention() - Extract from loki/loki.yaml
   - _scan_state_directory() - Find ~/.contextcore/state/
   - _derive_importance() - Use .contextcore.yaml business.criticality
   - _generate_warnings() - Create warnings for approaching retention

4. PersistenceManifest should include:
   - sources: Dict[str, DataSource]
   - warnings: List[RetentionWarning]
   - importance_derivation: dict

## Output Format
Python module with full implementation and type hints
"""

PHASE6_FEATURES = [
    Feature(
        task=PHASE6_PERSISTENCE_DETECTOR_TASK,
        name="DashPersist_PersistenceDetector",
        output_subdir="dashboard_persistence/phase6",
    ),
]


# =============================================================================
# Phase 7: Pre-Destroy Warning System
# =============================================================================

PHASE7_PRE_DESTROY_TASK = """
Enhance make destroy with data inventory and export options.

## Goal
Show users what data they're about to lose before destruction.

## Context
- Current: Makefile destroy target with basic warning
- Target: Show detailed inventory and offer export options

## Requirements

1. Create persistence CLI (src/contextcore/cli/persistence.py):
   ```python
   @click.group()
   def persistence():
       '''Persistence and data protection commands.'''

   @persistence.command("inventory")
   def inventory():
       '''Show inventory of persistent data.'''
       # Display: source, size, retention, importance
   ```

2. Add data-inventory Makefile target:
   ```makefile
   data-inventory: ## Show data inventory
       @python3 -m contextcore.cli persistence inventory
   ```

3. Update destroy target with interactive menu:
   ```makefile
   destroy:
       @$(MAKE) data-inventory
       @echo "OPTIONS:"
       @echo "  1. Export all telemetry data before destroy"
       @echo "  2. Export dashboards only (current behavior)"
       @echo "  3. Destroy without export"
       @read -p "Select option [1/2/3]: " option; ...
   ```

4. Add colored output for importance levels:
   - critical: red
   - high: yellow
   - medium: white
   - low: dim

5. Show retention warnings prominently

## Output Format
1. Python CLI code for persistence.py
2. Makefile target additions
"""

PHASE7_FEATURES = [
    Feature(
        task=PHASE7_PRE_DESTROY_TASK,
        name="DashPersist_PreDestroyWarning",
        output_subdir="dashboard_persistence/phase7",
    ),
]


# =============================================================================
# Phase 8: Telemetry Exporter
# =============================================================================

PHASE8_TELEMETRY_EXPORTER_TASK = """
Export actual trace, metric, and log data (not just dashboards).

## Goal
Enable backup of telemetry data before destruction.

## Context
- New file: src/contextcore/persistence/exporter.py
- Must query Tempo, Mimir, Loki APIs

## Requirements

1. Implement TelemetryExporter class:
   ```python
   class TelemetryExporter:
       def __init__(
           self,
           output_dir: str = "./backups",
           tempo_url: str = "http://localhost:3200",
           mimir_url: str = "http://localhost:9009",
           loki_url: str = "http://localhost:3100",
       ):
           ...

       def export_all(
           self,
           include_traces: bool = True,
           include_metrics: bool = True,
           include_logs: bool = True,
           time_range: str = "24h",
       ) -> ExportResult:
           ...
   ```

2. Implement _export_traces():
   - Use Tempo /api/search to find traces
   - Fetch full trace via /api/traces/{id}
   - Save to traces.json

3. Implement _export_metrics():
   - Use Mimir Prometheus API /api/v1/query_range
   - Query contextcore_* metrics
   - Save to metrics.json

4. Implement _export_logs():
   - Use Loki /api/v1/query_range with LogQL
   - Query {service="contextcore"}
   - Save to logs.json

5. Add CLI command:
   ```bash
   contextcore persistence export -t 24h -o ./backups/
   ```

6. Write manifest.json with export metadata

## Output Format
Python module with TelemetryExporter implementation
"""

PHASE8_FEATURES = [
    Feature(
        task=PHASE8_TELEMETRY_EXPORTER_TASK,
        name="DashPersist_TelemetryExporter",
        output_subdir="dashboard_persistence/phase8",
    ),
]


# =============================================================================
# Phase 9: Audit Trail
# =============================================================================

PHASE9_AUDIT_TRAIL_TASK = """
Record all destructive operations for accountability.

## Goal
Create an audit trail of data-affecting operations.

## Context
- New file: src/contextcore/persistence/audit.py
- Store in ~/.contextcore/audit.log and optionally push to Loki

## Requirements

1. Implement AuditEvent dataclass:
   ```python
   @dataclass
   class AuditEvent:
       timestamp: str
       operation: str  # destroy, delete, purge, restore
       user: str
       hostname: str
       data_affected: Dict[str, Any]  # sizes, counts
       backup_created: bool
       backup_path: Optional[str]
       confirmed: bool
       outcome: str  # success, failure, cancelled
   ```

2. Implement AuditTrail class:
   ```python
   class AuditTrail:
       def __init__(self, audit_dir: str = "~/.contextcore"):
           ...

       def record(self, event: AuditEvent) -> None:
           '''Append event to audit.log and optionally emit to Loki.'''

       def list_events(
           self,
           operation: Optional[str] = None,
           limit: int = 100,
       ) -> list[AuditEvent]:
           '''Query recent audit events.'''
   ```

3. Implement _emit_to_loki():
   - Push audit event to Loki for queryable history
   - Best effort (don't fail if Loki unavailable)

4. Add CLI command:
   ```bash
   contextcore persistence audit  # Show recent events
   ```

5. Integrate with destroy flow:
   - Record audit event before and after destruction
   - Include data inventory in the record

## Output Format
Python module with AuditTrail implementation
"""

PHASE9_FEATURES = [
    Feature(
        task=PHASE9_AUDIT_TRAIL_TASK,
        name="DashPersist_AuditTrail",
        output_subdir="dashboard_persistence/phase9",
    ),
]


# =============================================================================
# All Features Combined
# =============================================================================

DASHBOARD_PERSISTENCE_FEATURES = (
    PHASE1_FEATURES +
    PHASE2_FEATURES +
    PHASE3_FEATURES +
    PHASE4_FEATURES +
    PHASE5_FEATURES +
    PHASE6_FEATURES +
    PHASE7_FEATURES +
    PHASE8_FEATURES +
    PHASE9_FEATURES
)

# Phase groupings for selective execution
PHASES_1_3_FEATURES = PHASE1_FEATURES + PHASE2_FEATURES + PHASE3_FEATURES
PHASES_4_6_FEATURES = PHASE4_FEATURES + PHASE5_FEATURES + PHASE6_FEATURES
PHASES_7_9_FEATURES = PHASE7_FEATURES + PHASE8_FEATURES + PHASE9_FEATURES
