#!/bin/bash
# Capability Delivery Pipeline — end-to-end orchestration (REQ-CDP-008/009)
#
# Runs all pipeline stages for a plan + requirements pair:
#   Preflight → CREATE → POLISH → FIX → ANALYZE → INIT → VALIDATE → EXPORT → Summary
#
# Usage:
#   run-cap-delivery.sh --plan PATH --requirements PATH [--requirements PATH ...] \
#     --output-dir DIR --project ID --name NAME \
#     [--skip-polish] [--skip-fix] [--skip-validate] [--no-strict-quality]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_stage() { echo -e "\n${CYAN}${BOLD}── $1 ──${NC}"; }

# ── Defaults ──────────────────────────────────────────────────────────────────

PLAN=""
REQUIREMENTS=()
OUTPUT_DIR=""
PROJECT=""
NAME=""
SKIP_POLISH=false
SKIP_FIX=false
SKIP_VALIDATE=false
NO_STRICT_QUALITY=false

# ── Argument parsing ─────────────────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: run-cap-delivery.sh --plan PATH --requirements PATH [--requirements PATH ...]
         --output-dir DIR --project ID --name NAME
         [--skip-polish] [--skip-fix] [--skip-validate] [--no-strict-quality]

Pipeline stages:
  Preflight     Verify contextcore installed, files exist, output dir writable
  Stage 0       CREATE        — project context (project-context.yaml)
  Stage 1       POLISH        — plan quality checks (polish-report.json)
  Stage 1.5     FIX           — auto-remediate fixable polish failures
  Stage 2a      ANALYZE-PLAN  — structured plan analysis (plan-analysis.json)
  Stage 2b      INIT-FROM-PLAN — manifest bootstrap (.contextcore.yaml)
  Stage 3       VALIDATE      — schema check (gating)
  Stage 4       EXPORT        — artifact contract + provenance

Flags:
  --skip-polish         Bypass polish strict gating (still runs in advisory mode)
  --skip-fix            Skip auto-remediation entirely
  --skip-validate       Bypass manifest validation gating
  --no-strict-quality   Pass through to export (avoids task-mapping requirement)
USAGE
    exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --plan)
            PLAN="$2"; shift 2 ;;
        --requirements)
            REQUIREMENTS+=("$2"); shift 2 ;;
        --output-dir)
            OUTPUT_DIR="$2"; shift 2 ;;
        --project)
            PROJECT="$2"; shift 2 ;;
        --name)
            NAME="$2"; shift 2 ;;
        --skip-polish)
            SKIP_POLISH=true; shift ;;
        --skip-fix)
            SKIP_FIX=true; shift ;;
        --skip-validate)
            SKIP_VALIDATE=true; shift ;;
        --no-strict-quality)
            NO_STRICT_QUALITY=true; shift ;;
        --help|-h)
            usage 0 ;;
        *)
            log_error "Unknown argument: $1"
            usage 1 ;;
    esac
done

# ── Validate required args ───────────────────────────────────────────────────

missing=()
[[ -z "$PLAN" ]]       && missing+=("--plan")
[[ ${#REQUIREMENTS[@]} -eq 0 ]] && missing+=("--requirements")
[[ -z "$OUTPUT_DIR" ]] && missing+=("--output-dir")
[[ -z "$PROJECT" ]]    && missing+=("--project")
[[ -z "$NAME" ]]       && missing+=("--name")

if [[ ${#missing[@]} -ne 0 ]]; then
    log_error "Missing required arguments: ${missing[*]}"
    usage 1
fi

# ── Gate tracking (bash 3.x compatible — no associative arrays) ──────────────

PIPELINE_FAILED=false
GATE_create="N/A"
GATE_polish="N/A"
GATE_fix="N/A"
GATE_analyze_plan="N/A"
GATE_init_from_plan="N/A"
GATE_validate="N/A"
GATE_export="N/A"

record_gate() {
    local gate="$1" outcome="$2"
    # Store in individual variables (bash 3.x compatible)
    eval "GATE_${gate//-/_}=\"$outcome\""
    if [[ "$outcome" == "FAIL" ]]; then
        PIPELINE_FAILED=true
    fi
}

get_gate() {
    eval "echo \"\$GATE_${1//-/_}\""
}

# ══════════════════════════════════════════════════════════════════════════════
# PREFLIGHT
# ══════════════════════════════════════════════════════════════════════════════

log_stage "PREFLIGHT"

# contextcore installed?
if ! command -v contextcore &> /dev/null; then
    log_error "contextcore CLI not found. Install with: pip3 install -e '.[dev]'"
    exit 1
fi
log_info "contextcore CLI found: $(command -v contextcore)"

# Plan file exists?
if [[ ! -f "$PLAN" ]]; then
    log_error "Plan file not found: $PLAN"
    exit 1
fi
log_info "Plan: $PLAN"

# Requirements files exist?
for req in "${REQUIREMENTS[@]}"; do
    if [[ ! -f "$req" ]]; then
        log_error "Requirements file not found: $req"
        exit 1
    fi
    log_info "Requirements: $req"
done

# Output dir writable?
mkdir -p "$OUTPUT_DIR"
if [[ ! -w "$OUTPUT_DIR" ]]; then
    log_error "Output directory not writable: $OUTPUT_DIR"
    exit 1
fi
log_info "Output dir: $OUTPUT_DIR"

log_info "Preflight passed"

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 0: CREATE
# ══════════════════════════════════════════════════════════════════════════════

log_stage "Stage 0: CREATE"

contextcore create \
    --name "$NAME" \
    --project "$PROJECT" \
    --output-dir "$OUTPUT_DIR"

record_gate "create" "PASS"
log_info "Stage 0 complete — project-context.yaml written"

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1: POLISH
# ══════════════════════════════════════════════════════════════════════════════

log_stage "Stage 1: POLISH"

# When fix is enabled (default), polish runs in advisory mode to produce the
# report that fix consumes.  Strict gating only applies when fix is skipped.
if [[ "$SKIP_POLISH" == true ]]; then
    log_warn "Polish gating SKIPPED (--skip-polish)"
    # Still run advisory for the report
    if contextcore polish "$PLAN" --output-dir "$OUTPUT_DIR"; then
        record_gate "polish" "SKIPPED(advisory:pass)"
    else
        record_gate "polish" "SKIPPED(advisory:fail)"
    fi
elif [[ "$SKIP_FIX" == true ]]; then
    # No fix stage to remediate — enforce strict gating
    if contextcore polish "$PLAN" --strict --output-dir "$OUTPUT_DIR"; then
        record_gate "polish" "PASS"
        log_info "Stage 1 complete — polish strict checks passed"
    else
        record_gate "polish" "FAIL"
        log_error "Stage 1 FAILED — polish strict checks did not pass"
        log_error "Re-run with --skip-polish to bypass, or fix the plan document"
        exit 1
    fi
else
    # Fix stage will handle failures — run advisory mode for the report
    if contextcore polish "$PLAN" --output-dir "$OUTPUT_DIR"; then
        record_gate "polish" "PASS"
        log_info "Stage 1 complete — all polish checks passed"
    else
        record_gate "polish" "ADVISORY_FAIL"
        log_warn "Polish found issues — fix stage will attempt remediation"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1.5: FIX
# ══════════════════════════════════════════════════════════════════════════════

log_stage "Stage 1.5: FIX"

# Determine which plan file downstream stages should use
EFFECTIVE_PLAN="$PLAN"

if [[ "$SKIP_FIX" == true ]]; then
    log_warn "Fix stage SKIPPED (--skip-fix)"
    record_gate "fix" "SKIPPED"
else
    POLISH_REPORT="$OUTPUT_DIR/polish-report.json"
    FIX_ARGS=("$PLAN" --output-dir "$OUTPUT_DIR")
    if [[ -f "$POLISH_REPORT" ]]; then
        FIX_ARGS+=(--polish-report "$POLISH_REPORT")
    fi

    if contextcore fix "${FIX_ARGS[@]}"; then
        record_gate "fix" "PASS"
        # Use the remediated plan for downstream stages if it was produced
        PLAN_STEM="$(basename "$PLAN" .md)"
        FIXED_PLAN="$OUTPUT_DIR/${PLAN_STEM}.fixed.md"
        if [[ -f "$FIXED_PLAN" ]]; then
            EFFECTIVE_PLAN="$FIXED_PLAN"
            log_info "Using remediated plan: $EFFECTIVE_PLAN"
        else
            log_info "No remediated plan produced (no fixable issues); using original"
        fi
        log_info "Stage 1.5 complete"
    else
        record_gate "fix" "FAIL"
        log_warn "Fix stage returned non-zero; continuing with original plan"
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2a: ANALYZE-PLAN
# ══════════════════════════════════════════════════════════════════════════════

log_stage "Stage 2a: ANALYZE-PLAN"

ANALYZE_ARGS=(--plan "$EFFECTIVE_PLAN" --output "$OUTPUT_DIR/plan-analysis.json")
for req in "${REQUIREMENTS[@]}"; do
    ANALYZE_ARGS+=(--requirements "$req")
done

contextcore manifest analyze-plan "${ANALYZE_ARGS[@]}"

record_gate "analyze-plan" "PASS"
log_info "Stage 2a complete — plan-analysis.json written"

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2b: INIT-FROM-PLAN
# ══════════════════════════════════════════════════════════════════════════════

log_stage "Stage 2b: INIT-FROM-PLAN"

INIT_ARGS=(
    --plan "$EFFECTIVE_PLAN"
    --output "$OUTPUT_DIR/.contextcore.yaml"
    --plan-analysis "$OUTPUT_DIR/plan-analysis.json"
    --force
    --no-validate
)
for req in "${REQUIREMENTS[@]}"; do
    INIT_ARGS+=(--requirements "$req")
done

contextcore manifest init-from-plan "${INIT_ARGS[@]}"

record_gate "init-from-plan" "PASS"
log_info "Stage 2b complete — .contextcore.yaml written"

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3: VALIDATE
# ══════════════════════════════════════════════════════════════════════════════

log_stage "Stage 3: VALIDATE"

if [[ "$SKIP_VALIDATE" == true ]]; then
    log_warn "Validation gating SKIPPED (--skip-validate)"
    record_gate "validate" "SKIPPED"
else
    if contextcore manifest validate --path "$OUTPUT_DIR/.contextcore.yaml"; then
        record_gate "validate" "PASS"
        log_info "Stage 3 complete — manifest validation passed"
    else
        record_gate "validate" "FAIL"
        log_error "Stage 3 FAILED — manifest validation did not pass"
        log_error "Re-run with --skip-validate to bypass, or fix the manifest"
        exit 1
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4: EXPORT
# ══════════════════════════════════════════════════════════════════════════════

log_stage "Stage 4: EXPORT"

EXPORT_ARGS=(
    -p "$OUTPUT_DIR/.contextcore.yaml"
    -o "$OUTPUT_DIR"
    --emit-provenance
    --emit-run-provenance
)
if [[ "$NO_STRICT_QUALITY" == true ]]; then
    EXPORT_ARGS+=(--no-strict-quality)
fi

contextcore manifest export "${EXPORT_ARGS[@]}"

record_gate "export" "PASS"
log_info "Stage 4 complete — export artifacts written"

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY (REQ-CDP-009)
# ══════════════════════════════════════════════════════════════════════════════

log_stage "PIPELINE SUMMARY"

echo ""
echo -e "${BOLD}Gate outcomes:${NC}"
for gate in create polish fix analyze-plan init-from-plan validate export; do
    outcome="$(get_gate "$gate")"
    case "$outcome" in
        PASS)               color="$GREEN" ;;
        FAIL)               color="$RED" ;;
        SKIPPED*)           color="$YELLOW" ;;
        *)                  color="$NC" ;;
    esac
    printf "  %-18s %b%s%b\n" "$gate" "$color" "$outcome" "$NC"
done

echo ""
echo -e "${BOLD}Output directory:${NC} $OUTPUT_DIR"
echo -e "${BOLD}Files:${NC}"
ls -1 "$OUTPUT_DIR" | while read -r f; do
    echo "  $f"
done

# Provenance summary
PROV_FILE="$OUTPUT_DIR/run-provenance.json"
if [[ -f "$PROV_FILE" ]]; then
    echo ""
    echo -e "${BOLD}Artifact inventory (from run-provenance.json):${NC}"
    python3 - "$PROV_FILE" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    inventory = d.get('artifact_inventory', [])
    by_stage = {}
    for e in inventory:
        stage = e.get('stage', 'unknown')
        by_stage.setdefault(stage, []).append(e.get('artifact_id', '?'))
    for stage in sorted(by_stage):
        ids = by_stage[stage]
        print(f'  {stage}: {len(ids)} entries -- {", ".join(ids)}')
    print(f'  TOTAL: {len(inventory)} inventory entries')
except Exception as exc:
    print(f'  (could not parse: {exc})', file=sys.stderr)
PYEOF
fi

echo ""
if [[ "$PIPELINE_FAILED" == true ]]; then
    log_error "Pipeline completed with failures"
    exit 1
else
    log_info "Pipeline completed successfully"
    exit 0
fi
