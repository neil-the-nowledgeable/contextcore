# ROI Estimation Engine: Value Reflection

## Why I Built This

The pain points manifest (v1.0) had 28 pain points with `cost_model` fields -- frequency, unit cost, affected percentage. Structured. Ready for math. But no math had been done.

That meant every time someone asked "how much does this cost?" or "is this gap worth building?", the answer required pulling out the cost model, choosing an estimation method, plugging in org-specific numbers, and doing arithmetic. Every time. From scratch.

v2.0 did the math once: 28 pain points x 3 org sizes x 3 estimation methods = a complete ROI picture baked into the manifest. The estimates are order-of-magnitude (not forecasts), but they're auditable -- every formula is visible, every assumption is documented, and you can swap in your own org profile and recompute.

The real trigger: I couldn't answer "what should we build next?" without doing a 20-minute spreadsheet exercise. Now it's a lookup.

---

## What Was Built

### Three Estimation Methods

Not all pain is the same shape. Redundant effort is easy to measure (count the hours). Downtime risk depends on probability and impact. Agent capability gaps are speculative. Forcing all three into one formula would be dishonest. So three methods:

#### 1. Time-Based (High Confidence, +-30%)

```
annual_cost = headcount x frequency x unit_cost_hours x weeks/yr x affected_pct x hourly_rate
```

Used for pains where someone is doing repetitive, measurable work:
- Triple status update tax (dev: 5x/week, 6 min each, 90% affected)
- Monday morning status compilation (PM: 2 hours/week, 90% affected)
- 5-tool portfolio assembly (eng leader: 20 min/day, 90% affected)

These are the highest-confidence estimates. The inputs are observable. A time study would confirm or refine them within +-30%.

**Example: `dev.redundant_status_updates`**
```yaml
formula: "devs x 5/wk x 0.1hr x 50wk x 90% x $100/hr"
per_person_annual:
  hours: 22.5
  cost_usd: 2_250
annual_cost_usd:
  startup: 11_250       # 5 devs x $2,250
  mid_market: 56_250    # 25 devs x $2,250
  enterprise: 225_000   # 100 devs x $2,250
confidence: high
```

#### 2. Risk-Based (Medium Confidence, +-50%)

```
annual_cost = frequency x P(realization) x impact_if_realized
```

Used for pains where the cost depends on whether something goes wrong and how bad it is:
- 2am triage without context (incident frequency x MTTR extension x downtime cost)
- Deploy-time dependency surprise (sprint frequency x failure rate x rollback cost)
- Cycle time too late to act (sprint frequency x waste rate x sprint value)

These estimates include a probability multiplier. The biggest variable is downtime cost, which scales dramatically with org size ($500/hr startup to $10,000/hr enterprise). That's why SRE pain jumps from $20K (startup) to $471K (enterprise) -- it's the same number of incidents, but each minute costs 20x more.

**Example: `sre.triage_without_context`**
```yaml
method: risk_based
formula: "incidents/yr x MTTR_extension_hr x (downtime_cost + labor)"
components:
  mttr_extension:
    hours: 0.5         # 30 min longer without context
  incidents_per_year: 24
annual_cost_usd:
  startup: 7_440       # $500/hr downtime
  mid_market: 33_360   # $2,000/hr downtime
  enterprise: 240_000  # $10,000/hr downtime
confidence: medium
```

#### 3. Opportunity-Based (Low Confidence, +-3-5x)

```
annual_cost = capability_delta x adoption_drag x value_per_unit
```

Used for pains where the cost is what you _can't_ do, not what you're doing wrong:
- Agent decisions opaque (no dashboard for AI reasoning)
- Best-AI-for-job inaccessible (agents can't delegate to specialists)
- No institutional memory (every session starts from zero)

These are the least certain estimates. The "cost" is lost productivity or missed capability, not measurable hours. A 3-5x range is appropriate -- meaning a $100K estimate could be $30K or $500K depending on how much the org relies on AI agents.

**Example: `agent.no_institutional_memory`**
```yaml
method: opportunity_based
rationale: |
  Agent effectiveness loss from no cross-session memory.
  Each session rediscovers 5-10 min of context. But the real cost
  is compounding: decisions aren't reused, patterns aren't learned.
annual_cost_usd:
  startup: 5_000
  mid_market: 25_000
  enterprise: 100_000
confidence: low
note: "Highly dependent on AI usage intensity. Zero if agents aren't used."
```

---

### Org-Size Profiles

Three reference profiles define all the input variables. Every formula traces back to these:

| Parameter | Startup | Mid-Market | Enterprise |
|---|---|---|---|
| Developers | 5 | 25 | 100 |
| Project Managers | 1 | 3 | 10 |
| Engineering Leaders | 1 | 3 | 10 |
| SREs | 1 | 3 | 10 |
| Compliance Officers | 1 | 1 | 3 |
| AI Agent Users | 5 | 25 | 100 |
| Dev hourly rate | $100 | $100 | $100 |
| PM hourly rate | $90 | $90 | $90 |
| Leader hourly rate | $130 | $130 | $130 |
| SRE hourly rate | $110 | $110 | $110 |
| Downtime cost/hr | $500 | $2,000 | $10,000 |
| Incidents/month | 2 | 4 | 8 |
| Audits/year | 4 | 4 | 4 |
| Working weeks/year | 50 | 50 | 50 |

To adjust for your org: replace these values, then recompute using the formula documented on each pain point. The formulas are visible -- no black boxes.

---

### Rollup Calculations

Individual pain point estimates aggregate into five rollup views:

#### A. By Persona

| Persona | # Pains | Startup | Mid-Market | Enterprise |
|---|---|---|---|---|
| Developer | 9 | $66K | $307K | $1,136K |
| Operator / SRE | 4 | $20K | $109K | $471K |
| AI Agent | 3 | $20K | $55K | $275K |
| Engineering Leader | 4 | $29K | $100K | $373K |
| Project Manager | 5 | $20K | $62K | $222K |
| Compliance Officer | 3 | $15K | $15K | $46K |
| **TOTAL** | **28** | **~$163K** | **~$633K** | **~$2,546K** |

Developer dominates at all org sizes. SRE scales fastest (downtime cost is the multiplier).

#### B. By Friction Category

| Category | Cost Type | Enterprise | % of Total |
|---|---|---|---|
| Redundant Effort | Time | $584K | 23% |
| Blind Spots | Opportunity | $550K | 22% |
| Crisis Friction | Risk | $452K | 18% |
| Interoperability Tax | Time | $251K | 10% |
| Delayed Feedback | Risk | $218K | 9% |
| Context Fragmentation | Time | $211K | 8% |
| Trust Deficit | Quality | $200K | 8% |

The top two (redundant effort + blind spots) account for 45% of total enterprise pain.

#### C. Delivered vs Gap Split

| Status | Enterprise Cost | % of Total |
|---|---|---|
| Delivered | $1,431K | 56% |
| Partial | $280K | 11% |
| Gap | $835K | 33% |

Cross-referenced with `contextcore.benefits.yaml` delivery_status. As benefits ship, costs move from gap to delivered.

#### D. Gap ROI Ranking

| Rank | Benefit Gap | Effort | Enterprise $/yr | Signal |
|---|---|---|---|---|
| 1 | Status compilation eliminated | Medium | $81K | HIGH |
| 2 | Agent decision visibility | Small | $275K | HIGHEST -- quick win |
| 3 | Deliverable verification | Medium | $200K | HIGH |
| 4 | Dependency validation | Small | $87K | HIGH |
| 5 | AOS compliance | Medium | $74K | MEDIUM |
| 6 | Codegen health | Medium | $125K | MEDIUM |

Gap #2 (agent visibility) is the top quick win: $275K enterprise value at small effort.

#### E. Top Cost Drivers Per Persona

Each persona section includes a `persona_roi_summary` identifying which pains dominate their burden. Examples:
- **Developer**: Context re-explanation (19%), redundant status (17%), cross-framework isolation (15%)
- **PM**: Monday status compilation (40%), status chasing (18%), cycle time too late (10%)
- **SRE**: 2am triage without context (51%), recent changes unknown (41%)
- **Compliance**: Audit evidence assembly (~65% of persona cost)

---

### Key Assumptions and Limitations

Documented in the `roi_methodology` section of the YAML:

**Assumptions:**
- Hourly rates include salary + benefits + overhead
- 50 working weeks/year
- Downtime costs scale with org size ($500 -> $10K/hr)
- AI agent frequency scales with active AI users
- Integration frequency scales sub-linearly with org size

**Limitations:**
- Opportunity-based estimates have 3-5x uncertainty
- Risk-based estimates assume industry-average incident rates
- No accounting for morale/retention impact (real but unquantifiable)
- Partial overlap between some persona pains (audit appears under both compliance and leader)
- Assumes current tool landscape

**Confidence scale:**
- **High**: Time-based with documented baselines. +-30% range.
- **Medium**: Time-based with estimated frequencies, or risk-based with known parameters. +-50% range.
- **Low**: Opportunity-based or risk-based with estimated probabilities. +-3-5x range.

---

## What It Gives Me

### Decisions It Answers

| Question | Where to Look | Example Answer |
|---|---|---|
| What should we build next? | `gap_roi_ranking` | Agent visibility: $275K, small effort |
| Which persona hurts most? | `roi_rollup.by_persona` | Developer: $1.1M enterprise |
| What type of friction dominates? | `roi_rollup.by_friction_category` | Redundant effort: 23% |
| How much value have we delivered? | `by_delivery_status.delivered` | $1.4M (56%) |
| How much opportunity remains? | `by_delivery_status.gap` | $835K (33%) |
| What does inaction cost this persona? | `personas.{name}.persona_roi_summary` | PM: $222K/yr enterprise |
| Can I use these numbers for my org? | `org_profiles` + per-pain `formula` | Replace inputs, recompute |

### Time Saved

Before: derive the answer from cost_model fields, choose a method, do arithmetic, sanity-check. 20-30 minutes per question.

After: lookup. The math is done and the formulas are visible for audit.

### Cognitive Load Removed

- Don't need to remember which estimation method applies to which friction type
- Don't need to decide whether to use headcount or incident frequency as the multiplier
- Don't need to re-derive downtime scaling across org sizes
- Don't need to manually cross-reference delivery status with cost allocation

---

## How to Use It

### For roadmap prioritization
Read `roi_rollup.gap_roi_ranking`. The gaps are pre-ranked by cost/effort ratio. #2 (agent visibility) is labeled "HIGHEST -- quick win" because $275K at small effort beats $81K at medium effort.

### For a sales conversation
Pick the prospect's persona. Read their `persona_roi_summary` for the total burden, then their top pain points for specific quotes in their voice. "Your PMs spend 2 hours every Monday compiling status" is more compelling than "we save time."

### For your own org
Replace `org_profiles` with your headcounts, rates, and downtime costs. Then recompute using the formula on each pain point. The formulas are explicit -- `devs x 5/wk x 0.1hr x 50wk x 90% x $100/hr` -- so you can plug in your own values.

### For tracking progress
When a benefit ships, update `by_delivery_status` -- move its cost from `gap` to `delivered`. The pain point itself stays (it documents what WAS painful). Only the rollup changes.

---

## File Location

All ROI calculations live inside the pain points manifest:

```
docs/capability-index/contextcore.pain_points.yaml

  Lines 37-103:    org_profiles (3 reference orgs)
  Lines 203-1700:  28 pain points, each with roi_estimate block
  Lines 1706-1964: roi_rollup (5 aggregation views)
  Lines 1966-2012: roi_methodology (methods, assumptions, limitations)
```

Supporting files:
- `PAIN_POINTS_GUIDE.md` -- usage guide with estimation methodology section
- `pain-points-harbor-tour.html` -- visual ROI tables, persona cards, gap ranking
- `contextcore.user.yaml` -- `contextcore.value.roi_estimation` capability entry
- `contextcore.agent.yaml` -- `contextcore.value.query_pain_points` and `query_gap_ranking`

---

*Session: 2026-01-30 | Capability: ROI Estimation Engine | 28 estimates, 3 methods, 3 org sizes, 5 rollup views*
