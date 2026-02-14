# ContextCore Harbor Tour

**Welcome aboard.** You've docked at ContextCore—a project management observability framework that finally treats your work the way observability tools treat your services.

This is your self-guided tour for exploring what's here and understanding why it matters to *you*, right now, on your own machine.

---

## Quick Orientation

```
You Are Here: ~/Documents/dev/ContextCore
├── Your new observability stack awaits
├── A TUI wizard to get you running
└── Zero status reports, forever
```

**Time to value:** Run `contextcore tui launch` and you'll have dashboards in minutes.

---

## The Value to You

### What Problem Does This Solve?

You've felt it: the disconnect between the work you're doing and the "status" you're supposed to report. You commit code, merge PRs, ship features—but then someone asks "what's the status?" and you have to *reconstruct* information that already exists.

**The core insight:** Project tasks have the same structure as distributed trace spans:
- Start time, end time
- Status transitions
- Parent-child hierarchy
- Events along the way

ContextCore stores your tasks in the same infrastructure you'd use for tracing microservices. This isn't a new tool—it's a new use of tools you probably already run.

---

## Your Personal ROI

### Time Reclaimed

| Activity | Before ContextCore | With ContextCore |
|----------|-------------------|------------------|
| Writing status reports | 30-60 min/week | 0 min (derived from artifacts) |
| Answering "what's the status?" | 5-10 interruptions/week | Link to dashboard |
| Finding what was decided last month | 15 min of searching | TraceQL query in seconds |
| Setting up project observability | Hours of config | `make full-setup` |

**Conservative estimate:** 2-4 hours/week reclaimed.

### Cognitive Load Reduced

Things you no longer need to remember:
- Which tasks are in progress (it's in the span)
- When something was started (timestamp in Tempo)
- What agents decided in past sessions (queryable insights)
- Who to update about status (they have dashboard access)

### Problems Eliminated

| Used to Fail | Now Works |
|--------------|-----------|
| "I forgot to update the ticket" | Status derived from commits |
| "What did we decide about X?" | Query `{ insight.type = "decision" }` |
| "Agent sessions start from zero" | Agent insights persist across sessions |
| "Where's that metric coming from?" | Unified in your observability stack |

---

## What's Unique Here

### Tasks as Spans

This is the key innovation. Every project task becomes an OpenTelemetry span:

```python
from contextcore import TaskTracker

tracker = TaskTracker(project="my-project")
tracker.start_task(task_id="PROJ-123", title="Implement feature", task_type="story")
tracker.update_status("PROJ-123", "in_progress")  # Adds span event
tracker.complete_task("PROJ-123")  # Ends span
```

**Why this matters:** Your tasks are now queryable with TraceQL, visualizable in Grafana, and correlated with your runtime telemetry. One infrastructure for everything.

### Dual Telemetry

ContextCore emits both:
- **Spans to Tempo** — hierarchy, timing, TraceQL queries
- **Logs to Loki** — events, status changes, metrics derivation

This means your dashboards can show:
- Task timelines (from spans)
- Event feeds (from logs)
- Derived metrics (from Loki recording rules to Mimir)

### Agent Memory That Persists

When you use AI agents (Claude, GPT, etc.), their insights typically die when the session ends. ContextCore changes that:

```python
from contextcore.agent import InsightEmitter, InsightQuerier

# Agent emits a decision
emitter = InsightEmitter(project_id="my-project", agent_id="claude")
emitter.emit_decision("Selected async pattern for better throughput", confidence=0.9)

# Next session (or different agent) queries it
querier = InsightQuerier()
prior = querier.query(project_id="my-project", insight_type="decision", time_range="30d")
```

**Why this matters:** AI agents can build on each other's work. Your architecture decisions persist. Lessons learned don't get lost.

---

## Your First 15 Minutes

### Option 1: TUI Wizard (Recommended)

```bash
# Launch the terminal interface
contextcore tui launch

# Or jump straight to installation
contextcore tui install
```

The TUI guides you through:
1. Prerequisites check
2. Deployment method selection (Docker Compose or Kind)
3. Configuration
4. Stack deployment
5. Verification

### Option 2: One Command

```bash
# Full stack: observability services + verification + seeded dashboards
make full-setup
```

### Option 3: Generate Custom Script

```bash
# Generate an installation script tailored to your environment
contextcore tui generate-script
```

---

## What You'll See

After installation, open Grafana at `http://localhost:3000`:

### Installation Dashboard
Path: `contextcore-installation`

Verifies everything is working:
- All services healthy
- Endpoints accessible
- Demo data flowing

### Portfolio Dashboard
Path: `contextcore-portfolio`

High-level view:
- Active projects
- Health status (on-track, at-risk, blocked)
- Sprint velocity trends
- Blocked task summary

### Project Progress Dashboard
Path: `contextcore-progress`

Drill-down view:
- Sprint burndown
- Kanban board
- Work breakdown structure
- Cycle time metrics

---

## The Stack You're Getting

| Service | Port | Purpose |
|---------|------|---------|
| **Grafana** | 3000 | Dashboards & visualization |
| **Tempo** | 3200 | Traces (tasks as spans, agent insights) |
| **Mimir** | 9009 | Metrics (derived from Loki) |
| **Loki** | 3100 | Logs (events, status changes) |
| **Alloy** | 12345 | Telemetry collection |
| **OTLP** | 4317 | gRPC endpoint for spans |

All vendor-agnostic. All configurable. All running locally.

---

## Key Files to Know

| File | What It Does |
|------|--------------|
| `.contextcore.yaml` | Project metadata, risks, SLOs |
| `CLAUDE.md` | Instructions for AI agents working on this project |
| `docker-compose.yaml` | Local observability stack |
| `Makefile` | Common operations (up, down, seed-metrics, etc.) |
| `src/contextcore/` | The Python SDK |
| `grafana/provisioning/dashboards/` | Dashboard JSON files |

---

## CLI Commands That Matter

```bash
# Task tracking
contextcore task start --id TASK-1 --title "My feature" --type story
contextcore task update --id TASK-1 --status in_progress
contextcore task complete --id TASK-1

# Installation verification
contextcore install verify          # Full check with telemetry
contextcore install status          # Quick status (no telemetry)

# Dashboard management
contextcore dashboards provision    # Push dashboards to Grafana
contextcore dashboards list         # See what's provisioned

# TUI
contextcore tui launch              # Main interface
contextcore tui status              # Service health check
contextcore tui generate-script     # Create install script
```

---

## The Mental Model

```
Traditional Approach              ContextCore Approach
─────────────────────             ───────────────────────
Jira ────┐
         │                        Commits ──┐
GitHub ──┼── Manual sync          PRs ──────┼── Auto-derived ──▶ Tempo
         │                        CI ───────┘                     (spans)
Slack ───┘                                                          │
    │                                                               │
    ▼                                                               ▼
Status reports                    Grafana dashboards
(you write)                       (always current)
```

**You stop being the integration layer.** The system derives status from what you're already doing.

---

## For AI Agent Integration

If you're exploring ContextCore for AI agent use:

```python
# Check human-set constraints before acting
from contextcore.agent import GuidanceReader
reader = GuidanceReader(project_id="my-project")
constraints = reader.get_constraints_for_path("src/auth/")

# Query what other agents discovered
from contextcore.agent import InsightQuerier
querier = InsightQuerier()
prior = querier.query(project_id="my-project", insight_type="decision")

# Emit your findings for future sessions
from contextcore.agent import InsightEmitter
emitter = InsightEmitter(project_id="my-project", agent_id="my-agent")
emitter.emit_decision("Chose X over Y because Z", confidence=0.9)
```

---

## What Makes This Worth Your Time

1. **No new tools to learn** — Uses Grafana, Tempo, Loki you may already know
2. **Vendor agnostic** — OTLP exports to any compatible backend
3. **Self-monitoring** — ContextCore tracks its own installation status
4. **Human-agent parity** — Same data accessible to humans and AI agents
5. **Zero ongoing maintenance** — Status is derived, not manually entered

---

## Quick Verification

After setup, run:

```bash
# Check service health
contextcore tui status --json

# Full verification
contextcore install verify

# Expected output: 100% completeness
```

Open `http://localhost:3000/d/contextcore-installation` to see it visualized.

---

## Next Steps

1. **Explore the TUI:** `contextcore tui launch`
2. **Read CLAUDE.md:** Understand the project's architecture
3. **Try task tracking:** Create your first task span
4. **Check dashboards:** See your data in Grafana
5. **Emit an insight:** Test agent memory persistence

---

## The Bottom Line

ContextCore gives you:
- **Hours back every week** from eliminated status reporting
- **Queryable project history** instead of lost context
- **AI agent memory** that survives sessions
- **Unified observability** for code and projects

All running on your machine. All vendor-agnostic. All derived from work you're already doing.

---

*This is ContextCore. One system. Every audience. Always current.*
