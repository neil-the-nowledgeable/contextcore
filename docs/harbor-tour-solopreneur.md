# ContextCore Harbor Tour: Solo-Preneur Edition

**Welcome aboard.** You're the developer who has five projects in flight, three half-baked ideas in `~/projects/`, and a growing collection of markdown files trying to keep it all straight.

This tour is for you—the solo builder who doesn't need to report status to anyone, but desperately needs to remember *where you left off* when you context-switch back to something you touched three weeks ago.

---

## The Problem You Know Too Well

```
~/projects/
├── saas-app/
│   ├── README.md           # "TODO: finish auth"
│   ├── NOTES.md            # Last updated: ???
│   └── decisions.md        # 47 lines, half outdated
├── cli-tool/
│   ├── TODO.md             # "Fix the thing"
│   └── CHANGELOG.md        # Stopped updating in March
├── side-project/
│   └── ideas.md            # "This could be big"
└── client-work/
    └── status.md           # "Where was I?"
```

**The markdown files don't scale.** You write them with good intentions, then:
- Forget to update them
- Can't remember which file has what
- Search through 12 files to find "that decision about the database"
- Start fresh every time you return to a project

---

## What If Your Work Tracked Itself?

ContextCore stores your project activity as queryable data—not static markdown that gets stale.

| Markdown Reality | ContextCore Reality |
|------------------|---------------------|
| `TODO.md` you forgot to update | Tasks derived from your commits |
| `decisions.md` you can't find | Query: "What did I decide about auth?" |
| "Where was I?" on Monday morning | Dashboard shows last activity per project |
| Searching 12 files for context | One TraceQL query across everything |
| Starting from scratch with AI assistants | Agents remember your prior sessions |

---

## Your Personal ROI

### Context Recovery Time

| Scenario | Before | After |
|----------|--------|-------|
| Returning to project after 2 weeks | 30-45 min re-reading | 2 min dashboard scan |
| "What was I doing on X?" | Grep through markdown | TraceQL: recent tasks |
| "Why did I choose Y?" | Hope you wrote it down | Query past decisions |
| Finding where you left off | Mental archaeology | Last span timestamp |

**For someone juggling 3-5 projects, this is 2-4 hours/week recovered.**

### Cognitive Load Eliminated

Things you no longer need to hold in your head:
- Which project needs attention (dashboard shows staleness)
- What you decided and why (queryable insights)
- What's blocked and on what (span events)
- Where AI assistants left off (persistent agent memory)

### The Real Win: Continuity

The hardest part of solo work isn't the work—it's the **context switching**. Every time you jump between projects, you pay a tax. ContextCore minimizes that tax by making your history queryable, not narrative.

---

## How It Works for Solo Devs

### Your Work Becomes Data

Every task you track becomes an OpenTelemetry span:

```python
from contextcore import TaskTracker

# Working on the SaaS app today
tracker = TaskTracker(project="saas-app")
tracker.start_task(task_id="auth-flow", title="Implement OAuth", task_type="feature")

# Two hours later
tracker.update_status("auth-flow", "in_progress")
tracker.add_event("auth-flow", "Got Google OAuth working, need Apple next")

# Done for the day
tracker.pause_task("auth-flow")  # Span stays open with last event
```

**Three weeks later**, you return:

```python
# Where was I?
from contextcore.agent import InsightQuerier
querier = InsightQuerier()
recent = querier.query(project_id="saas-app", time_range="30d")
# Returns: "Got Google OAuth working, need Apple next"
```

### AI Assistants That Remember

When you use Claude, GPT, or any AI assistant with ContextCore:

```python
from contextcore.agent import InsightEmitter, InsightQuerier

# Claude helps you make a decision
emitter = InsightEmitter(project_id="saas-app", agent_id="claude")
emitter.emit_decision(
    "Use Supabase Auth instead of rolling our own",
    confidence=0.9,
    context={"reason": "Faster to ship, good enough for MVP"}
)

# A month later, different session, maybe different AI
querier = InsightQuerier()
prior = querier.query(project_id="saas-app", insight_type="decision")
# Returns the Supabase decision with full context
```

**No more re-explaining your project to AI every session.**

### Multi-Project Dashboard

Instead of checking 5 different `TODO.md` files:

```
┌─────────────────────────────────────────────────────────────┐
│  Your Projects                                      [Grafana] │
├─────────────────────────────────────────────────────────────┤
│  saas-app      │ ●  3 tasks in progress │ Last: 2 days ago  │
│  cli-tool      │ ○  1 task blocked      │ Last: 2 weeks ago │
│  side-project  │ ●  Active              │ Last: today       │
│  client-work   │ ⚠  Stale (14 days)     │ Last: 14 days ago │
└─────────────────────────────────────────────────────────────┘
```

One glance. All projects. No file hunting.

---

## Quick Start for Solo Devs

### Option 1: TUI Wizard

```bash
# Interactive setup
contextcore tui launch
```

### Option 2: One Command

```bash
# Full stack in one shot
make full-setup

# Then open your dashboard
open http://localhost:3000
```

### Option 3: Minimal Start

Don't need the full observability stack? Start with just task tracking:

```bash
# Install just the SDK
pip install contextcore

# Start tracking (exports to file if no backend)
contextcore task start --id my-task --title "The thing I'm working on"
```

---

## Daily Workflow

### Morning: What Needs Attention?

```bash
# Quick status across all projects
contextcore tui status

# Or check the dashboard
open http://localhost:3000/d/contextcore-portfolio
```

### During Work: Capture Context

```bash
# Starting something
contextcore task start --id feature-x --title "Add export feature" --project saas-app

# Made progress
contextcore task update --id feature-x --status in_progress

# Hit a blocker
contextcore task block --id feature-x --reason "Need to upgrade pandas first"

# Done for now
contextcore task complete --id feature-x
```

### End of Day: Let It Be

That's it. No status file to update. No decisions.md to maintain. Your work is already recorded.

---

## Replacing Your Markdown Files

| Old File | ContextCore Replacement |
|----------|------------------------|
| `TODO.md` | Active tasks in Tempo (TraceQL query) |
| `decisions.md` | Agent insights with `insight.type = "decision"` |
| `CHANGELOG.md` | Task completion spans with timestamps |
| `notes.md` | Task events and agent insights |
| `ideas.md` | Tasks with `task.type = "idea"` and status `backlog` |

### Migration: Don't Migrate

You don't need to import your old markdown. Just start tracking new work. Old context can stay where it is—you'll naturally query ContextCore for recent work and only dig into old markdown for historical archaeology.

---

## For Your AI Assistants

Add this to your project's `CLAUDE.md` (or equivalent):

```markdown
## Project Memory

This project uses ContextCore for persistent context. Before starting work:

1. Query prior decisions:
   ```python
   from contextcore.agent import InsightQuerier
   querier = InsightQuerier()
   prior = querier.query(project_id="PROJECT_ID", time_range="30d")
   ```

2. Check active tasks:
   ```python
   tasks = querier.query(project_id="PROJECT_ID", insight_type="task")
   ```

3. After making decisions, emit them:
   ```python
   from contextcore.agent import InsightEmitter
   emitter = InsightEmitter(project_id="PROJECT_ID", agent_id="claude")
   emitter.emit_decision("What was decided", confidence=0.9)
   ```
```

Now every AI session has access to prior context.

---

## The Stack (Lightweight Option)

Full stack for complete observability:

| Service | Port | Why You Want It |
|---------|------|-----------------|
| Grafana | 3000 | Visual dashboards |
| Tempo | 3200 | Task spans, decisions |
| Loki | 3100 | Event logs |
| Mimir | 9009 | Metrics (optional for solo) |

**But you can start smaller:**

```bash
# Just Tempo + Grafana for task visualization
docker-compose up grafana tempo -d
```

Or even simpler—ContextCore can export to files if you don't want to run services:

```bash
export CONTEXTCORE_EXPORT_MODE=file
export CONTEXTCORE_EXPORT_PATH=~/.contextcore/data
```

---

## Key Commands for Solo Work

```bash
# Project switching
contextcore task list --project saas-app      # What's active?
contextcore task list --status blocked        # What's stuck across all projects?

# Quick task management
contextcore task start --id X --title "Thing" --project Y
contextcore task update --id X --status in_progress
contextcore task complete --id X

# Context queries
contextcore metrics wip                       # Work in progress across all
contextcore metrics stale --days 14           # Projects needing attention

# AI context
contextcore insight query --project Y --type decision --days 30
contextcore insight emit --summary "Decided X because Y" --confidence 0.9
```

---

## The Solo-Preneur Mental Model

```
Traditional Solo Dev                 ContextCore Solo Dev
────────────────────                 ───────────────────────

5 projects ──┐                       5 projects ──┐
             │                                    │
             ▼                                    ▼
5 TODO.md files                      1 Tempo database
5 decisions.md                       TraceQL queries
5 notes.md                           1 Grafana dashboard
             │                                    │
             ▼                                    ▼
Context lives in your head           Context lives in queryable data
(hope you remember)                  (always recoverable)
```

---

## What You'll Actually Use

Be honest—you won't use everything. Here's the 80/20 for solo devs:

### Daily (2 minutes)
- `contextcore task start/complete` when switching focus
- Glance at dashboard when starting work

### Weekly (5 minutes)
- Check stale projects: `contextcore metrics stale --days 7`
- Review blocked tasks: `contextcore task list --status blocked`

### When AI Helps (automatic)
- Agent insights are queried/emitted automatically if you've set up CLAUDE.md
- Prior decisions surface without you asking

### Monthly (15 minutes)
- Review decision history: "What major choices did I make?"
- Clean up completed tasks
- Archive projects you're not returning to

---

## Getting Started

```bash
# 1. Clone and install
cd ~/projects
git clone https://github.com/contextcore/contextcore
cd contextcore
pip install -e ".[dev]"

# 2. Start the stack
make full-setup

# 3. Open dashboard
open http://localhost:3000

# 4. Track your first task
contextcore task start --id my-first-task --title "Try ContextCore" --project test

# 5. Complete it
contextcore task complete --id my-first-task

# 6. See it in Grafana
# Navigate to the Project Progress dashboard
```

---

## The Bottom Line

You don't need status reports. You need **context recovery**.

ContextCore gives you:
- **Queryable history** instead of scattered markdown
- **AI assistants that remember** across sessions
- **One dashboard** for all your projects
- **Automatic tracking** from your existing workflow

Stop maintaining TODO.md files that go stale. Let your work speak for itself.

---

*ContextCore for Solo-Preneurs: Because your memory shouldn't be a single point of failure.*
