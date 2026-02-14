# Pain Points Manifest Guide

## What Was Built

`contextcore.pain_points.yaml` is a companion manifest to `contextcore.benefits.yaml`. While the benefits manifest captures **what ContextCore delivers**, the pain points manifest captures **who hurts, how, and how much** before those benefits exist.

### Files

| File | Purpose |
|------|---------|
| `contextcore.pain_points.yaml` | Pain points, frictions, costs, and ROI estimates by persona |
| `contextcore.benefits.yaml` | User benefits that drive capability creation |
| `PAIN_POINTS_GUIDE.md` | This file |

### Relationship

```
benefits.yaml                    pain_points.yaml
(what we deliver)    <------>    (who hurts and how much)

benefit_id ─────────────────── addressed_by.benefit_id
  personas[].pain_point ────── pain_points[].description
  delivery_status ──────────── roi_rollup.by_delivery_status
```

Benefits are product-centric (organized by deliverable). Pain points are customer-centric (organized by persona). Both views are needed for product decisions.

---

## Structure

### Top-Level Sections

| Section | Purpose |
|---------|---------|
| `org_profiles` | Three reference org sizes (startup, mid-market, enterprise) with headcounts and rates |
| `friction_categories` | Seven friction types that emerge from clustering pain points |
| `personas` | Pain points grouped by persona — the primary query axis |
| `summary` | Cross-cutting analysis: severity, frequency, worst workarounds |
| `roi_rollup` | Aggregated annual costs by persona, friction category, delivery status |
| `roi_methodology` | How estimates were computed, key assumptions, limitations |
| `changelog` | Version history |

### Per Pain Point

Each of the 28 pain point entries contains:

```yaml
- pain_id: dev.redundant_status_updates     # Unique identifier
  name: "Triple Status Update Tax"           # Human-readable name
  description: "I update Jira, then..."      # Pain in the persona's voice
  friction_category: redundant_effort        # One of 7 categories
  severity: high                             # critical | high | medium | low
  emotional_weight: frustration              # How it feels (not just what it costs)

  cost_model:                                # Raw inputs for ROI calculation
    frequency: 5
    frequency_unit: per_week
    unit_cost: 6
    unit_cost_basis: minutes
    affected_pct: 90
    baseline_statement: "30+ min/dev/week"
    compounding: false

  roi_estimate:                              # Computed annual cost
    method: time_based                       # time_based | risk_based | opportunity_based
    formula: "devs x 5/wk x 0.1hr x ..."    # Auditable formula
    per_person_annual:
      hours: 22.5
      cost_usd: 2_250
    annual_cost_usd:
      startup: 11_250
      mid_market: 56_250
      enterprise: 225_000
    confidence: high                         # high (+-30%) | medium (+-50%) | low (+-3-5x)

  addressed_by:                              # Links back to benefits manifest
    - benefit_id: time.status_updates_eliminated
      relief: full                           # full | partial | indirect
```

---

## How to Use It

### 1. Understand persona pain burden

Look at the `persona_roi_summary` at the top of each persona section:

```yaml
developer:
  persona_roi_summary:
    annual_cost_usd:
      startup: 66_000
      mid_market: 307_000
      enterprise: 1_136_000
    top_cost_drivers:
      - pain_id: dev.context_reexplanation    # 19% of total
      - pain_id: dev.redundant_status_updates # 17%
```

**Use case:** "Which persona should we prioritize?" Sort by annual cost.

### 2. Prioritize roadmap gaps by ROI

The `roi_rollup.gap_roi_ranking` section ranks unaddressed gaps by cost:

```yaml
gap_roi_ranking:
  ranked:
    - rank: 1
      benefit_id: visibility.agent_insights
      effort: small
      annual_cost_addressed:
        enterprise: 275_000
      roi_signal: "HIGHEST -- large savings, SMALL effort. Quick win."
```

**Use case:** "What should we build next?" Sort gaps by cost/effort ratio.

### 3. Communicate value to specific audiences

Each pain point is written in the persona's voice with emotional weight:

- **Developer:** "I update Jira, then GitHub, then Slack -- same info 3 places" (frustration)
- **PM:** "I spend 2 hours every Monday compiling status" (dread)
- **SRE:** "Alert fires at 2am, I don't know why this service matters" (panic)

**Use case:** Sales conversations, product pages, investor decks. Pick the persona, use their pain language.

### 4. Assess delivered value

The `roi_rollup.by_delivery_status` section shows what's already captured:

```yaml
delivered:
  annual_cost_addressed:
    enterprise: 1_431_000      # ~$1.4M addressed
  pct_of_total:
    enterprise: 56             # 56% of total pain addressed
gap:
  annual_cost_unaddressed:
    enterprise: 835_000        # ~$835K still hurting
  pct_of_total:
    enterprise: 33
```

**Use case:** "How much value has ContextCore already delivered?" "How much is left?"

### 5. Adjust estimates for your org

Replace the `org_profiles` values with your actual numbers:

```yaml
org_profiles:
  your_org:
    headcount:
      developers: 40           # Your count
    rates_usd_per_hour:
      developer: 120           # Your blended rate
    downtime_cost_usd_per_hour: 5000  # Your downtime cost
```

Then recompute estimates using the documented formulas in each `roi_estimate.formula`.

### 6. Track pain reduction over time

As benefits move from `gap` to `partial` to `delivered`, update the `by_delivery_status` split. This shows pain reduction over releases.

---

## Three Estimation Methods

| Method | Confidence | Formula | Used For |
|--------|-----------|---------|----------|
| **Time-based** | High (+-30%) | headcount x frequency x hours x rate | Redundant effort, context fragmentation, trust deficit |
| **Risk-based** | Medium (+-50%) | frequency x P(event) x impact | Delayed feedback, crisis friction, downtime |
| **Opportunity-based** | Low (+-3-5x) | capability_delta x adoption_drag | Blind spots, interoperability tax, agent pains |

All estimates are order of magnitude. Use them for prioritization and directional decisions, not budgeting.

---

## Friction Categories

| Category | Cost Type | % of Total (Enterprise) |
|----------|-----------|------------------------|
| Redundant Effort | Time | 23% |
| Blind Spots | Opportunity | 22% |
| Crisis Friction | Risk | 18% |
| Interoperability Tax | Time | 10% |
| Delayed Feedback | Risk | 9% |
| Context Fragmentation | Time | 8% |
| Trust Deficit | Quality | 8% |

---

## Key Numbers

| Metric | Startup | Mid-Market | Enterprise |
|--------|---------|------------|------------|
| Total annual pain cost | ~$160K | ~$630K | ~$2.5M |
| Already addressed (delivered) | ~$92K (56%) | ~$326K (52%) | ~$1.4M (56%) |
| Remaining gaps | ~$57K (35%) | ~$234K (37%) | ~$835K (33%) |
| #1 gap by ROI | Agent decision visibility (small effort, ~$275K enterprise) |
| Largest persona cost | Developer (~$1.1M enterprise) |
| Highest per-person cost | Compliance officer (160 hrs/yr on audit evidence) |

---

## Maintenance

### Adding a new pain point

1. Add to the appropriate persona section in `pain_points.yaml`
2. Include all fields: `pain_id`, `cost_model`, `roi_estimate`, `addressed_by`
3. Update `persona_roi_summary` totals
4. Update `roi_rollup` aggregates
5. Bump version, add changelog entry

### When a benefit is delivered

1. In `benefits.yaml`: change `delivery_status: gap` to `delivered`
2. In `pain_points.yaml`: update `roi_rollup.by_delivery_status` — move the cost from `gap` to `delivered`
3. The pain point itself stays (documents what WAS painful). Only the rollup changes.

### Adjusting estimates

Each `roi_estimate` has an auditable `formula` field. Change `org_profiles` inputs to adjust all downstream numbers. Confidence labels tell you which estimates to trust.
