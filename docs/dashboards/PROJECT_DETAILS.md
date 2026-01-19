# Project Details Dashboard

**Purpose**: Deep-dive view into a single project, enabling project managers and team leads to understand current state, track individual tasks, identify blockers, and monitor team performance.

**Primary Users**: Project Managers, Tech Leads, Scrum Masters, Individual Contributors

**Data Sources**: Tempo (task spans), Loki (event logs), Mimir (derived metrics)

**Entry Point**: Drill-down from Project Portfolio Overview via `?var-project=${project_id}`

---

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PROJECT: ${project_id}                              [◀ Back to Portfolio]  │
│  Owner: ${owner}  │  Criticality: ${criticality}  │  Sprint: ${sprint_id}  │
│  [Time Range: 7d ▼]  [Refresh: 30s]                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Progress  │  │  Stories  │  │   Tasks   │  │  Blocked  │  │  Velocity │ │
│  │   67%     │  │  5 / 8    │  │  18 / 32  │  │     2     │  │  28 pts   │ │
│  │  ████░░   │  │ completed │  │ completed │  │  ▲ 1      │  │  / 34 plan│ │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘ │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 1: Sprint Burndown & Task Board                                        │
│  ┌───────────────────────────────────┐  ┌───────────────────────────────────┐
│  │  SPRINT BURNDOWN (Time Series)   │  │  KANBAN BOARD (Swimlane)          │
│  │                                   │  │                                   │
│  │  34 ─────╲                       │  │ BACKLOG│ TODO │IN PROG│ REVIEW│DONE│
│  │          ╲  Ideal               │  │ ───────┼──────┼───────┼───────┼────│
│  │           ╲                      │  │ EPIC-1 │      │       │       │    │
│  │  25 ───────╲────╮ Actual        │  │  ├ ST-1│      │ TSK-5 │       │TSK-1│
│  │              ╲   ╲               │  │  ├ ST-2│TSK-8 │ TSK-6 │ TSK-7 │TSK-2│
│  │               ╲   ╲              │  │  └ ST-3│      │       │       │TSK-3│
│  │  10 ───────────╲───╲             │  │ EPIC-2 │      │       │       │    │
│  │                 ╲   ╲            │  │  └ ST-4│TSK-12│ TSK-10│       │TSK-9│
│  │   0 ─────────────╲───▼          │  │        │      │       │       │    │
│  │     D1  D3  D5  D7  D10 D14     │  │ [🔴 Blocked tasks highlighted]     │
│  └───────────────────────────────────┘  └───────────────────────────────────┘
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 2: Task Hierarchy & Progress                                           │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  WORK BREAKDOWN (Tree Table with Progress Bars)                        ││
│  │  ─────────────────────────────────────────────────────────────────────  ││
│  │  ▼ EPIC-42: Platform Modernization                    ███████░░░ 72%   ││
│  │    ├─ ▼ STORY-101: Auth Service                       █████████░ 88%   ││
│  │    │    ├─ TASK-201: Implement OAuth [done]           ██████████ 100%  ││
│  │    │    ├─ TASK-202: Add MFA support [in_review]      █████████░ 90%   ││
│  │    │    └─ TASK-203: Write auth tests [in_progress]   ██████░░░░ 60%   ││
│  │    │                                                                    ││
│  │    ├─ ▼ STORY-102: Payment Gateway                    ████░░░░░░ 40%   ││
│  │    │    ├─ TASK-210: Design API [done]                ██████████ 100%  ││
│  │    │    ├─ TASK-211: Impl Stripe [blocked] 🔴         ███░░░░░░░ 30%   ││
│  │    │    └─ TASK-212: Impl PayPal [todo]               ░░░░░░░░░░ 0%    ││
│  │    │                                                                    ││
│  │    └─ ▼ STORY-103: Inventory Sync                     ██████████ 100%  ││
│  │         ├─ TASK-220: Batch import [done]              ██████████ 100%  ││
│  │         └─ TASK-221: Real-time sync [done]            ██████████ 100%  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 3: Blockers & Team Workload                                            │
│  ┌───────────────────────────────────┐  ┌───────────────────────────────────┐
│  │  BLOCKER DETAILS (Table)         │  │  TEAM WORKLOAD (Horizontal Bar)  │
│  │                                   │  │                                   │
│  │  Task   │ Since │ Reason │ Action│  │  alice    ████████░░ 8 pts        │
│  │  ──────────────────────────────  │  │  bob      ██████░░░░ 6 pts        │
│  │  TSK-211│ 3d    │ API key │ ⚠ ESC│  │  carol    ████░░░░░░ 4 pts        │
│  │  TSK-305│ 1d    │ Review  │ 👀   │  │  david    █████████░ 9 pts        │
│  │                                   │  │  [unassigned] ██░░░░░░░░ 2 pts   │
│  │  Impact: 2 stories, 8 pts blocked│  │                                   │
│  │                                   │  │  Team capacity: 29/34 pts (85%)  │
│  └───────────────────────────────────┘  └───────────────────────────────────┘
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 4: Metrics & Trends                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────────┐
│  │ CYCLE TIME (Avg)│  │ THROUGHPUT      │  │  STATUS FLOW (Sankey/Flow)      │
│  │                 │  │                 │  │                                 │
│  │    3.2 days     │  │   2.4 tasks/day │  │  backlog ══╗                   │
│  │    ▼ 0.5d       │  │    ▲ 0.3        │  │            ╠══> todo ══╗       │
│  │                 │  │                 │  │  todo ═════╝           ║       │
│  │  Target: 4 days │  │  Last sprint: 2.1│  │                       ╠══> done│
│  └─────────────────┘  └─────────────────┘  │  in_progress ═════════╝       │
│                                            │  blocked ══> in_progress      │
│                                            └─────────────────────────────────┘
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 5: Activity Timeline                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  PROJECT TIMELINE (Annotations + Events)                               ││
│  │                                                                         ││
│  │  Jan 8    Jan 10    Jan 12    Jan 14    Jan 16                         ││
│  │  ─────────────────────────────────────────────────────────────────────  ││
│  │     ○ Sprint start                                                      ││
│  │        ●─────────────○ STORY-101 (auth)                                 ││
│  │           ●──────────────────○ STORY-102 (payment)                      ││
│  │              ●───○ STORY-103 (inventory) ✓                              ││
│  │                    🔴 TSK-211 blocked                                   ││
│  │                          ○ Today                                        ││
│  │  ─────────────────────────────────────────────────────────────────────  ││
│  │  ■ Story span  ● Start  ○ End  🔴 Blocker  ✓ Complete                   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 6: Event Log (Collapsible)                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  ▼ RECENT ACTIVITY                                         [Filter ▼]  ││
│  │  ─────────────────────────────────────────────────────────────────────  ││
│  │  15:42  ✅ TSK-203 progress: 50% → 60%                                  ││
│  │  15:30  🔄 TSK-202 status: in_progress → in_review                      ││
│  │  14:15  💬 TSK-211 comment: "Waiting on vendor API key" (alice)        ││
│  │  12:00  🚫 TSK-211 blocked: "Vendor API unavailable"                   ││
│  │  11:30  ✅ TSK-221 completed (5 pts)                                    ││
│  │  10:45  👤 TSK-203 assigned: bob → alice                               ││
│  │  09:00  ➕ TSK-310 created: "Add retry logic" (task, 3 pts)            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Panel Specifications

### Header Row: Project KPIs

#### Panel 1: Overall Progress
- **Type**: Gauge
- **Description**: Weighted average progress across all epics/stories
- **Query** (PromQL):
  ```promql
  avg(
    task_percent_complete{
      project_id="${project}",
      task_type=~"epic|story"
    }
  )
  ```
- **Display**:
  - Large gauge with percentage
  - Progress bar below
  - Threshold colors: Red <40%, Yellow 40-70%, Green >70%

#### Panel 2: Stories Completed
- **Type**: Stat
- **Description**: Completed stories vs total in current sprint
- **Query** (Loki):
  ```logql
  # Completed
  count_over_time(
    {service="contextcore", project_id="${project}"}
    | json
    | event="task.completed"
    | task_type="story"
    | sprint_id="${sprint}"
    [$__range]
  )
  ```
- **Format**: `X / Y completed`

#### Panel 3: Tasks Completed
- **Type**: Stat
- **Description**: Completed tasks vs total
- **Query**: Similar to stories, filtered by `task_type="task"`

#### Panel 4: Blocked Count
- **Type**: Stat
- **Description**: Currently blocked tasks
- **Query** (Loki):
  ```logql
  # Count blocked events minus unblocked events
  count_over_time({service="contextcore", project_id="${project}"} | json | event="task.blocked" [$__range])
  -
  count_over_time({service="contextcore", project_id="${project}"} | json | event="task.unblocked" [$__range])
  ```
- **Thresholds**: 0=Green, 1-2=Yellow, >2=Red
- **Link**: Scroll to Blocker Details panel

#### Panel 5: Sprint Velocity
- **Type**: Stat
- **Description**: Story points completed vs planned
- **Query** (Loki/PromQL):
  ```promql
  sum(task_story_points_completed{project_id="${project}", sprint_id="${sprint}"})
  /
  scalar(sprint_planned_points{project_id="${project}", sprint_id="${sprint}"})
  * 100
  ```
- **Format**: `X pts / Y planned`

---

### Row 1: Sprint Progress

#### Panel: Sprint Burndown
- **Type**: Time Series
- **Description**: Story points remaining over sprint duration
- **Queries**:
  ```promql
  # Ideal burndown (linear from planned to 0)
  sprint_planned_points{sprint_id="${sprint}"}
  * (1 - (time() - sprint_start_time) / (sprint_end_time - sprint_start_time))

  # Actual remaining
  sprint_planned_points{sprint_id="${sprint}"}
  -
  sum(task_story_points_completed{sprint_id="${sprint}"})
  ```
- **Visualization**:
  - Two lines: Ideal (dashed gray), Actual (solid blue)
  - X-axis: Sprint days
  - Y-axis: Story points remaining
  - Shaded area between if behind

#### Panel: Kanban Board View
- **Type**: Table with Status Grouping (or Canvas/FlowChart plugin)
- **Description**: Visual task board grouped by status and hierarchy
- **Query** (Tempo TraceQL):
  ```traceql
  {
    project.id = "${project}"
    && task.status != "done"
    && task.status != "cancelled"
  }
  | select(task.id, task.title, task.status, task.type, task.assignee, task.parent_id)
  ```
- **Visualization**:
  - Columns: Backlog, Todo, In Progress, In Review, Done
  - Rows: Grouped by parent epic/story
  - Blocked tasks: Red border/highlight
  - Clickable cards linking to task details

---

### Row 2: Work Breakdown Structure

#### Panel: Task Hierarchy Tree
- **Type**: Table (with nesting/tree transformation)
- **Description**: Hierarchical view of epics → stories → tasks with progress
- **Query** (Tempo):
  ```traceql
  {
    project.id = "${project}"
    && task.type =~ "epic|story|task|subtask"
  }
  | select(
    task.id,
    task.title,
    task.type,
    task.status,
    task.percent_complete,
    task.parent_id,
    task.story_points,
    task.assignee
  )
  ```
- **Columns**:
  | Column | Width | Description |
  |--------|-------|-------------|
  | Task | 40% | Indented task ID + title (expandable) |
  | Status | 10% | Status badge with color |
  | Progress | 25% | Progress bar |
  | Assignee | 15% | Person assigned |
  | Points | 10% | Story points |

- **Transformations**:
  1. Build tree from `task.parent_id` relationships
  2. Sort by task type (epic → story → task → subtask)
  3. Add progress bars via value mappings
  4. Highlight blocked rows in red

- **Interactions**:
  - Click task to expand children
  - Click task ID to open external URL
  - Hover for full details tooltip

---

### Row 3: Blockers & Team

#### Panel: Blocker Details
- **Type**: Table
- **Description**: Deep dive into blocked tasks with context and actions
- **Columns**:
  | Column | Description |
  |--------|-------------|
  | Task | Task ID (linked) |
  | Title | Task title |
  | Blocked Since | Days since blocked |
  | Reason | Block reason text |
  | Blocked By | Blocking task/dependency |
  | Assignee | Who's responsible |
  | Impact | Downstream blocked items count |
  | Action | Suggested next action icon |

- **Query** (Loki):
  ```logql
  {service="contextcore", project_id="${project}"}
  | json
  | event="task.blocked"
  | line_format "{{.task_id}} {{.reason}} {{.blocked_by}} {{.timestamp}}"
  ```

- **Transformations**:
  - Calculate `days_blocked = now() - timestamp`
  - Lookup assignee from task attributes
  - Calculate impact by counting child tasks

- **Action Icons**:
  - ⚠️ Escalate (blocked > 2 days)
  - 👀 Needs review
  - 🔗 Dependency (has blocked_by)
  - ⏳ Waiting (external dependency)

#### Panel: Team Workload
- **Type**: Bar Gauge (horizontal)
- **Description**: Story points assigned per team member
- **Query** (PromQL):
  ```promql
  sum by (assignee) (
    task_story_points{
      project_id="${project}",
      task_status!~"done|cancelled"
    }
  )
  ```
- **Visualization**:
  - Horizontal bars per assignee
  - Color by capacity (over capacity = red)
  - Show "unassigned" as separate bar
  - Display team total vs capacity

---

### Row 4: Metrics

#### Panel: Average Cycle Time
- **Type**: Stat with Sparkline
- **Description**: Average time from in_progress to done
- **Query** (PromQL):
  ```promql
  histogram_quantile(0.5,
    sum(rate(task_cycle_time_bucket{project_id="${project}"}[$__rate_interval]))
    by (le)
  ) / 86400  # Convert to days
  ```
- **Comparison**: Show vs previous sprint
- **Target Line**: Configurable target (default: 4 days)

#### Panel: Throughput
- **Type**: Stat with Sparkline
- **Description**: Tasks completed per day (rolling average)
- **Query** (PromQL):
  ```promql
  sum(increase(task_completed_total{project_id="${project}"}[1d]))
  ```
- **Sparkline**: 7-day trend

#### Panel: Status Flow (Sankey)
- **Type**: Sankey Diagram (requires plugin) or Node Graph
- **Description**: Visualize task flow between statuses
- **Query** (Loki):
  ```logql
  {service="contextcore", project_id="${project}"}
  | json
  | event="task.status_changed"
  | line_format "{{.from_status}} {{.to_status}}"
  ```
- **Transformations**:
  - Count transitions between each status pair
  - Build flow diagram: backlog → todo → in_progress → in_review → done
  - Highlight blocked flows in red

---

### Row 5: Timeline

#### Panel: Project Timeline (Gantt-style)
- **Type**: Time Series with Annotations (or Canvas)
- **Description**: Visual timeline of task/story spans
- **Query** (Tempo):
  ```traceql
  {
    project.id = "${project}"
    && task.type =~ "story|epic"
  }
  ```
- **Visualization**:
  - Horizontal bars for each story/epic span
  - Start: span start_time
  - End: span end_time (or now if active)
  - Color by status
  - Annotations for blocker events

- **Annotations**:
  ```logql
  {service="contextcore", project_id="${project}"}
  | json
  | event=~"task.blocked|sprint.started|sprint.ended"
  ```

---

### Row 6: Activity Log

#### Panel: Recent Activity
- **Type**: Logs
- **Description**: Chronological event stream for the project
- **Query** (Loki):
  ```logql
  {service="contextcore", project_id="${project}"}
  | json
  | line_format "{{.event}} {{.task_id}} {{if .task_title}}{{.task_title | trunc 30}}{{end}} {{if .from_status}}{{.from_status}}→{{end}}{{.to_status}} {{if .reason}}\"{{.reason}}\"{{end}} {{if .actor}}({{.actor}}){{end}}"
  ```
- **Filters** (dropdown):
  - All events
  - Status changes only
  - Blockers only
  - Comments only
  - Completions only
- **Display**:
  - Event type icon
  - Timestamp
  - Task reference
  - Event details
  - Actor (if known)

---

## Variables (Template Variables)

| Variable | Type | Query/Options | Description |
|----------|------|---------------|-------------|
| `project` | Query | `label_values(task_percent_complete, project_id)` | Selected project (from drill-down) |
| `sprint` | Query | `label_values(task_percent_complete{project_id="$project"}, sprint_id)` | Sprint filter |
| `task_type` | Custom | `epic,story,task,subtask,bug` | Filter by task type |
| `status` | Custom | `backlog,todo,in_progress,in_review,blocked,done` | Filter by status |
| `assignee` | Query | `label_values(task_assignee{project_id="$project"})` | Filter by person |
| `show_completed` | Custom | `yes,no` | Toggle completed tasks |

---

## Drill-Down Links

### From Portfolio Overview
```
/d/contextcore-project-details?var-project=${project_id}
```

### To External Task System
Each task links to its external URL (Jira, GitHub, etc.):
```
${task.url}
```

### To Trace View (Tempo)
Link task span to Tempo explore:
```
/explore?left=["now-1h","now","Tempo",{"query":"{ task.id=\"${task_id}\" }"}]
```

---

## Alerts (Project-Specific)

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| Task Blocked | New `task.blocked` event | Warning | Notify assignee |
| Long-Running Blocker | Blocked > 48h | Critical | Notify PM + Tech Lead |
| Sprint at Risk | Progress < 50% at sprint midpoint | Warning | Notify PM |
| Story Overdue | Due date passed, not complete | Info | Add to standup |
| No Activity | No events in 24h | Info | Check-in with team |

---

## Interactions & UX

### Quick Actions
- **Refresh**: Manual refresh button
- **Time Range**: Quick select (Today, This Sprint, Last 7d, Last 30d)
- **Export**: Download task list as CSV
- **Share**: Copy dashboard URL with current filters

### Keyboard Shortcuts
- `r` - Refresh dashboard
- `p` - Toggle completed tasks
- `/` - Focus search
- `?` - Show help

### Responsive Behavior
- **Wide (>1600px)**: Full layout as shown
- **Medium (1200-1600px)**: 2-column layouts
- **Narrow (<1200px)**: Single column, prioritize:
  1. KPI stats
  2. Blocker details
  3. Task hierarchy
  4. Activity log

---

## Color Scheme (Consistent with Portfolio)

| Status | Color | Hex | Usage |
|--------|-------|-----|-------|
| Done | Green | #73BF69 | Completed tasks, success |
| In Progress | Blue | #5794F2 | Active work |
| In Review | Purple | #B877D9 | Awaiting review |
| Todo | Gray | #9FA7B3 | Not started |
| Blocked | Red | #F2495C | Blocked items |
| Backlog | Light Gray | #CCCCDC | Future work |
| Epic | Gold | #FADE2A | Epic-level items |
| Story | Teal | #6ED0E0 | Story-level items |

---

## Data Freshness

| Panel | Refresh Rate | Cache |
|-------|--------------|-------|
| KPI Stats | 30s | 30s |
| Burndown | 5m | 5m |
| Task Hierarchy | 1m | 1m |
| Blockers | 30s | 0 (real-time) |
| Activity Log | Live | 0 (streaming) |
| Metrics | 5m | 5m |
