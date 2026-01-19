# Project Portfolio Overview Dashboard

**Purpose**: Provide executives and program managers a single-pane view of all projects tracked by ContextCore, enabling quick identification of projects needing attention and resource allocation decisions.

**Primary Users**: Program Managers, Engineering Managers, Executives, PMO

**Data Sources**: Tempo (task spans), Loki (event logs), Mimir (derived metrics)

---

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PROJECT PORTFOLIO OVERVIEW                          │
│  [Time Range Picker: 7d ▼]  [Refresh: 30s]                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Active    │  │   On Track  │  │  At Risk    │  │  Blocked    │        │
│  │  Projects   │  │  Projects   │  │  Projects   │  │   Tasks     │        │
│  │     12      │  │      8      │  │      3      │  │      5      │        │
│  │   ▲ 2       │  │   ▼ 1       │  │   ▲ 2       │  │   ▲ 1       │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 1: Portfolio Health Matrix                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  PROJECT HEALTH OVERVIEW (Table with conditional formatting)           ││
│  │  ─────────────────────────────────────────────────────────────────────  ││
│  │  Project       │ Status │ Progress │ Blocked │ Sprint │ Owner    │ ▶    ││
│  │  ─────────────────────────────────────────────────────────────────────  ││
│  │  checkout-svc  │  🟢    │  ████░ 78%│    0    │ S-3   │ commerce │ →    ││
│  │  auth-service  │  🟡    │  ███░░ 45%│    2    │ S-3   │ platform │ →    ││
│  │  payment-api   │  🔴    │  ██░░░ 32%│    3    │ S-2   │ fintech  │ →    ││
│  │  user-profile  │  🟢    │  █████ 92%│    0    │ S-3   │ growth   │ →    ││
│  │  inventory     │  🟡    │  ███░░ 55%│    1    │ S-3   │ supply   │ →    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 2: Progress & Velocity                                                 │
│  ┌───────────────────────────────────┐  ┌───────────────────────────────────┐│
│  │  PORTFOLIO PROGRESS (Gauge Grid) │  │  VELOCITY TREND (Time Series)    ││
│  │                                   │  │                                   ││
│  │  checkout    auth      payment   │  │      ╭─────╮                      ││
│  │    ◐          ◔          ◔       │  │     ╱      ╲    ╭──╮             ││
│  │   78%        45%        32%      │  │    ╱        ╲__╱    ╲            ││
│  │                                   │  │   ╱                   ╲           ││
│  │  user-prof  inventory  search    │  │  ╱─────────────────────╲          ││
│  │    ◕          ◐          ◔       │  │  S-1    S-2    S-3    S-4        ││
│  │   92%        55%        28%      │  │  ─── Target  ─── Actual          ││
│  └───────────────────────────────────┘  └───────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 3: Risk & Blockers                                                     │
│  ┌───────────────────────────────────┐  ┌───────────────────────────────────┐│
│  │  BLOCKED TASKS (Table)           │  │  TASKS BY STATUS (Stacked Bar)   ││
│  │                                   │  │                                   ││
│  │  Task      │Project │Days│Reason │  │  checkout  ████████░░ 8/10       ││
│  │  AUTH-45   │auth-svc│ 3  │API dep│  │  auth-svc  ██████░░░░ 6/10       ││
│  │  PAY-12    │payment │ 5  │vendor │  │  payment   ███░░░░░░░ 3/10       ││
│  │  PAY-15    │payment │ 2  │PAY-12 │  │  user-prof █████████░ 9/10       ││
│  │  INV-88    │inventory│1  │data   │  │                                   ││
│  │  PAY-18    │payment │ 1  │review │  │  ■ Done ■ In Progress ■ Blocked  ││
│  └───────────────────────────────────┘  └───────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 4: Trends & Patterns                                                   │
│  ┌───────────────────────────────────┐  ┌───────────────────────────────────┐│
│  │  LEAD TIME DISTRIBUTION (Hist)   │  │  ACTIVITY HEATMAP (Calendar)     ││
│  │                                   │  │                                   ││
│  │      ▂▄█▇▅▃▂▁                    │  │  Mon ░▒▓▓▒░▒▓▒░▒▓░░▒▓▒░          ││
│  │      ─────────────               │  │  Tue ▒▓▓▓▒▒▓▓▒░▒▓▒▒▓▓▒           ││
│  │      1d  3d  7d  14d  30d        │  │  Wed ▒▓▓▒▒░▓▓▒░░▓▓▓▓▓▒           ││
│  │                                   │  │  Thu ░▒▓▓▒▒▒▓▒░▒▓▓▒▓▓▒           ││
│  │  Median: 4.2d  P90: 8.1d         │  │  Fri ░░▒▓░░▒▓▒░░▒▓▒░▒░           ││
│  └───────────────────────────────────┘  └───────────────────────────────────┘│
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ROW 5: Recent Activity Log                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  RECENT EVENTS (Log Panel - Last 50 events)                            ││
│  │  ─────────────────────────────────────────────────────────────────────  ││
│  │  14:32  ✅ checkout-svc  TASK-789 completed (story, 5pts)              ││
│  │  14:28  🚫 payment-api   PAY-18 blocked: "Waiting on security review"  ││
│  │  14:15  🔄 auth-service  AUTH-45 status: in_progress → in_review       ││
│  │  14:02  ➕ user-profile  USER-92 created (bug, P2)                     ││
│  │  13:55  ✅ inventory     INV-87 completed (task, 3pts)                 ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Panel Specifications

### Header Row: KPI Stats

#### Panel 1: Active Projects Count
- **Type**: Stat
- **Description**: Count of projects with active (non-completed) tasks
- **Query** (Loki):
  ```logql
  count(
    count by (project_id) (
      {service="contextcore"}
      | json
      | task_type =~ "epic|story|task"
      | __error__=""
    )
  )
  ```
- **Thresholds**:
  - Green: Any value (informational)
- **Sparkline**: Show trend over time range

#### Panel 2: On Track Projects
- **Type**: Stat
- **Description**: Projects with average task progress > 60% and no blocked tasks
- **Query** (PromQL):
  ```promql
  count(
    avg by (project_id) (task_percent_complete{task_type=~"story|epic"}) > 60
    unless
    count by (project_id) (task_status{status="blocked"}) > 0
  )
  ```
- **Color**: Green
- **Sparkline**: Show trend

#### Panel 3: At Risk Projects
- **Type**: Stat
- **Description**: Projects with progress < 40% or blocked tasks
- **Query** (PromQL):
  ```promql
  count(
    avg by (project_id) (task_percent_complete{task_type=~"story|epic"}) < 40
    or
    count by (project_id) (task_status{status="blocked"}) > 0
  )
  ```
- **Color**: Yellow/Orange
- **Sparkline**: Show trend

#### Panel 4: Blocked Tasks (Total)
- **Type**: Stat
- **Description**: Total blocked tasks across all projects
- **Query** (Loki instant):
  ```logql
  count_over_time(
    {service="contextcore"}
    | json
    | event="task.blocked"
    [$__range]
  )
  -
  count_over_time(
    {service="contextcore"}
    | json
    | event="task.unblocked"
    [$__range]
  )
  ```
- **Thresholds**:
  - Green: 0
  - Yellow: 1-3
  - Red: > 3

---

### Row 1: Project Health Overview

#### Panel: Project Health Table
- **Type**: Table
- **Description**: Sortable table of all projects with health indicators
- **Columns**:
  | Column | Source | Description |
  |--------|--------|-------------|
  | Project | `project_id` | Project identifier (link to detail dashboard) |
  | Status | Calculated | Health status emoji based on rules below |
  | Progress | `task_percent_complete` | Average progress bar |
  | Blocked | Count | Number of blocked tasks |
  | Sprint | `sprint_id` | Current sprint identifier |
  | Owner | `business.owner` | Team/individual owner |
  | Action | Link | Drill-down to Project Details |

- **Health Status Rules**:
  - 🟢 Green: Progress ≥ 70% AND Blocked = 0
  - 🟡 Yellow: Progress 40-69% OR Blocked 1-2
  - 🔴 Red: Progress < 40% OR Blocked > 2

- **Query** (Loki + Transform):
  ```logql
  # Get latest status per project
  {service="contextcore"}
  | json
  | event="task.progress_updated" or event="task.status_changed"
  | line_format "{{.project_id}} {{.task_id}} {{.percent_complete}} {{.to_status}}"
  ```

- **Transformations**:
  1. Group by `project_id`
  2. Calculate average progress
  3. Count blocked status
  4. Add data links to Project Details dashboard with `project_id` variable

---

### Row 2: Progress & Velocity

#### Panel: Portfolio Progress Gauges
- **Type**: Gauge (repeated)
- **Description**: Visual progress gauges for each project
- **Query** (PromQL):
  ```promql
  avg by (project_id) (
    task_percent_complete{task_type=~"story|epic"}
  )
  ```
- **Display**:
  - Show as grid of gauges
  - Max value: 100
  - Thresholds: 0-40 Red, 40-70 Yellow, 70-100 Green
  - Show project name as title

#### Panel: Velocity Trend
- **Type**: Time Series
- **Description**: Story points completed per sprint over time
- **Queries**:
  ```promql
  # Actual velocity
  sum by (sprint_id) (
    increase(task_story_points_completed_total[$__interval])
  )

  # Planned velocity (from sprint.planned_points)
  sum by (sprint_id) (sprint_planned_points)
  ```
- **Visualization**:
  - Line chart with points
  - Two series: Planned (dashed) vs Actual (solid)
  - Show sprint IDs on X-axis

---

### Row 3: Risk & Blockers

#### Panel: Blocked Tasks Table
- **Type**: Table
- **Description**: All currently blocked tasks with context
- **Columns**:
  | Column | Source | Description |
  |--------|--------|-------------|
  | Task | `task_id` | Task identifier (link to external system) |
  | Project | `project_id` | Parent project |
  | Days Blocked | Calculated | Duration since `task.blocked` event |
  | Reason | `reason` | Block reason from event |
  | Blocked By | `blocked_by` | Blocking task ID if applicable |

- **Query** (Loki):
  ```logql
  {service="contextcore"}
  | json
  | event="task.blocked"
  | line_format "{{.timestamp}} {{.project_id}} {{.task_id}} {{.reason}} {{.blocked_by}}"
  ```

  Exclude tasks that have been unblocked:
  ```logql
  # Use Grafana transformation to anti-join blocked with unblocked
  ```

- **Sorting**: By days blocked (descending)
- **Actions**: Link to task URL if available

#### Panel: Tasks by Status (Stacked Bar)
- **Type**: Bar Chart (horizontal, stacked)
- **Description**: Task count breakdown by status per project
- **Query** (PromQL):
  ```promql
  sum by (project_id, status) (
    task_count_by_status
  )
  ```
- **Stacking**: By status
- **Colors**:
  - Done: Green (#73BF69)
  - In Progress: Blue (#5794F2)
  - In Review: Purple (#B877D9)
  - Todo: Gray (#9FA7B3)
  - Blocked: Red (#F2495C)
  - Backlog: Light Gray (#CCCCDC)

---

### Row 4: Trends & Patterns

#### Panel: Lead Time Distribution
- **Type**: Histogram
- **Description**: Distribution of task completion times
- **Query** (PromQL):
  ```promql
  histogram_quantile(0.5,
    sum(rate(task_lead_time_bucket[$__rate_interval])) by (le)
  )
  ```
- **Visualization**:
  - Histogram bars showing distribution
  - Vertical lines for median and P90
  - X-axis: Duration buckets (1d, 3d, 7d, 14d, 30d)

#### Panel: Activity Heatmap
- **Type**: Heatmap
- **Description**: Task activity by day of week and time
- **Query** (Loki):
  ```logql
  sum by (day_of_week, hour) (
    count_over_time(
      {service="contextcore"}
      | json
      | event=~"task.created|task.completed|task.status_changed"
      [$__interval]
    )
  )
  ```
- **Visualization**:
  - Calendar heatmap showing activity intensity
  - Color scale: Low (light) to High (dark)

---

### Row 5: Recent Activity

#### Panel: Recent Events Log
- **Type**: Logs
- **Description**: Live stream of recent task events
- **Query** (Loki):
  ```logql
  {service="contextcore"}
  | json
  | event=~"task.created|task.completed|task.blocked|task.unblocked|task.status_changed"
  | line_format "{{.event | trunc 15}} {{.project_id}} {{.task_id}} {{if .to_status}}{{.from_status}}→{{.to_status}}{{end}} {{if .reason}}\"{{.reason}}\"{{end}}"
  ```
- **Display**:
  - Show timestamp, event icon, project, task, details
  - Color-code by event type
  - Limit to 50 most recent

---

## Variables (Template Variables)

| Variable | Type | Query | Description |
|----------|------|-------|-------------|
| `time_range` | Interval | Built-in | Dashboard time range |
| `project` | Query | `label_values(task_percent_complete, project_id)` | Filter by project |
| `owner` | Query | `label_values(project_owner)` | Filter by team owner |
| `criticality` | Custom | `critical,high,medium,low` | Filter by criticality |
| `sprint` | Query | `label_values(sprint_id)` | Filter by sprint |

---

## Drill-Down Links

Each project row links to the **Project Details Dashboard** with:
```
/d/contextcore-project-details?var-project=${project_id}
```

Task IDs link to external system URL if `task.url` attribute is set:
```
${__data.fields.task_url}
```

---

## Alerts (Optional)

| Alert | Condition | Severity |
|-------|-----------|----------|
| New Blocked Task | `task.blocked` event | Warning |
| Task Blocked > 3 days | Blocked duration > 72h | Critical |
| Project Progress Stalled | No progress events in 48h | Warning |
| Sprint Velocity < 70% Target | `completed_points / planned_points < 0.7` | Info |

---

## Refresh & Caching

- **Auto-refresh**: 30 seconds
- **Time range default**: Last 7 days
- **Cache TTL**: 30 seconds (for stats), 5 minutes (for historical queries)

---

## Color Scheme

| Element | Color | Hex |
|---------|-------|-----|
| On Track / Done | Green | #73BF69 |
| In Progress | Blue | #5794F2 |
| At Risk / Warning | Yellow | #FF9830 |
| Blocked / Critical | Red | #F2495C |
| Backlog / Inactive | Gray | #9FA7B3 |
| Background | Dark | #181B1F |

---

## Mobile Considerations

- Stack panels vertically on narrow screens
- Prioritize: KPI stats → Health table → Blocked tasks
- Hide: Heatmap, lead time histogram on mobile
- Swipe navigation between projects
