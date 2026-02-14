# Action Plan: OTel Kubernetes Observability Blueprint (#247)

> **Issue**: https://github.com/open-telemetry/sig-end-user/issues/247
> **Assigned**: neil-the-nowledgable, alemferreira
> **Project Lead**: danielgblanco
> **Last Updated**: 2026-02-04

---

## Context

You are assigned to issue #247 — creating a Blueprint for Kubernetes Observability. This is a SIG End-User deliverable under the OTel Blueprints project. It is separate from your ContextCore project management observability work.

There are also two related issues where you've already commented:
- **#235** (Blueprint template): You linked your reference architecture doc here. Daniel's Rumelt-based template is the one being adopted.
- **#236** (Reference architecture template): You linked the same doc here. Daniel pointed out it's more related to #235. The reference architecture template is still waiting on input from the DevEx SIG.

---

## Blockers (Do Not Write the Blueprint Yet)

Daniel has been explicit: no writing until two things are agreed.

1. **Template (#235)**: The Rumelt-based template (Diagnosis / Guiding Policies / Coherent Actions) is drafted in a Google Doc but has no PR yet. Wait for this to land as markdown in the sig-end-user repo.

2. **Scope (#247)**: alemferreira posted a scope proposal on Feb 3. Daniel hasn't responded yet. Scope needs agreement before writing starts.

---

## Action 1: Comment on the Scope Proposal (#247)

**Why**: The scope is being actively discussed. alemferreira posted a draft, alolita asked for a golden set of signals, and daniel listed four challenges. Your input now shapes what gets written later.

**What to post**: A comment that reframes the scope around challenges and benefits. Key points:

- Structure around daniel's four challenges (daemonset sprawl, OTLP vs Prometheus interop, KSM-less monitoring, resource semconv consistency)
- Each challenge should have: Problem / Benefit / Blueprint coverage
- Add a golden signals baseline section to address alolita's request for a "golden set for metrics and other signals"
- Clarify the boundary with #246: this blueprint covers what-to-observe and why; #246 covers how-to-collect and route
- Suggest additional topics: OTel Operator, autoscaling observability (HPA/VPA/CA/KEDA), meta-monitoring
- Propose reframing "verticals" as "domains" or "layers" to match K8s community terminology

See the scope draft prepared during the Feb 4 session below in Appendix A.

---

## Action 2: Clean Up Your #235 and #236 Comments

**Why**: Your existing reference architecture doc (`docs/blueprint-reference-architecture.md`) is a project management observability blueprint — unrelated to K8s observability. It currently sits as comments on both #235 and #236, which creates confusion about scope.

### Anti-Pattern: What Went Wrong

You linked the same combined document to both #235 and #236 without framing what it was contributing to each discussion. This created three overlapping problems:

**1. Scope-ambiguous contribution.** The document was both a blueprint (strategic guidance following the Rumelt template) AND a reference architecture (concrete implementation with code examples). Posting a document that serves two purposes into two issue threads forces the maintainer to figure out which part is relevant — or whether you understand the issue's scope at all. Daniel's response ("this is more related to #235") was a polite signal that the contribution didn't map to #236's scope.

**2. "Here's my thing" without "here's how it helps yours."** Linking a document without explicitly framing its relevance reads as self-promotion rather than contribution. The document may have been genuinely useful as an example of the Rumelt template applied to a real domain, but that framing was absent. The implicit message was "look at what I built," not "here's evidence that this template structure works when applied to a non-trivial domain."

**3. Domain confusion.** The document is about project management observability, not Kubernetes observability. Posting it on K8s-related discussions without clearly separating "I'm showing the template format works" from "I'm contributing K8s content" risks the impression that you're conflating your project's domain with the issue's domain.

### Positive Pattern: How to Contribute to SIG Discussions

**Frame before you link.** Before posting a document, write 2-3 sentences explaining what the reader should take from it and why it's relevant to *this specific issue*. "Here's an example of the Rumelt template applied to project management observability. The Diagnosis/Guiding Policies/Coherent Actions structure worked well for organizing domain-specific challenges. Happy to discuss what we'd change about the template based on this experience." That framing makes the contribution legible.

**Map your contribution to the issue's scope.** Each issue has a specific purpose. Before commenting, ask: "What is this issue trying to produce, and does my contribution advance that?" If your work spans multiple issues, reference only the relevant portion in each. Don't link the same artifact to both — split it and point each thread to the piece that matters.

**Separate "template example" from "content contribution."** On #235 (template), your doc is evidence that the template format works. On #236 (reference architecture), your doc would need to follow the reference architecture structure (case study with results and lessons learned), which it originally didn't. These are different contributions requiring different framing.

**Acknowledge when a maintainer redirects you.** When Daniel said the doc is more related to #235, the right response is to acknowledge the distinction and clarify your intent — not to let the comment sit. A brief reply like "You're right, the document follows the blueprint structure, not a reference architecture structure. I'll keep it on #235 as a template example" closes the loop and shows you're tracking the scope.

**Don't link your project unless the discussion calls for it.** On #247 (K8s observability), ContextCore is irrelevant — it's a different domain. Your OTel expertise and K8s operational experience are relevant; the ContextCore product is not. Contributing domain expertise without product references builds credibility.

### What to Do Now

- **#235**: Your doc is a valid worked example of the Rumelt template applied to a domain. No change needed, but if you comment again, clarify that it's an example of the template format, not a K8s observability contribution. Now that the split is done, you can link directly to [blueprint-project-management-observability.md](../blueprint-project-management-observability.md) as a cleaner example.

- **#236**: Daniel asked if it's more related to #235. He's right — the original doc followed the blueprint structure (strategic), not a reference architecture structure (case study). Consider replying to acknowledge this. Now that the reference architecture exists separately, [reference-architecture-contextcore.md](../reference-architecture-contextcore.md) is a genuine reference architecture that follows the template structure and could be linked as an example if helpful — but frame it as "here's what the template looks like when applied" rather than "here's my project."

- **Long-term**: ~~Split `docs/blueprint-reference-architecture.md` into two documents~~ **DONE (2026-02-04)**:
  - [docs/blueprint-project-management-observability.md](../blueprint-project-management-observability.md) — Blueprint (Diagnosis / Guiding Policies / Coherent Actions), strategic, environment-agnostic
  - [docs/reference-architecture-contextcore.md](../reference-architecture-contextcore.md) — Reference architecture (implementation, code, results, lessons learned), concrete, ContextCore-specific
  - Original `docs/blueprint-reference-architecture.md` updated to redirect to the two new documents (preserves existing GitHub links from #235 and #236 comments)

---

## Action 3: Research the Technical Content

**Why**: When the scope and template are agreed, you'll need depth on the K8s-specific topics. Building this now means you can contribute substantively when writing starts.

**Topics to research**:

### k8sclusterreceiver vs KSM
- What metrics does `k8sclusterreceiver` provide?
- Which KSM metrics have no equivalent?
- What's the migration path for teams with existing KSM-based dashboards and alerts?
- Collector resource overhead comparison

### Prometheus Interop
- Which K8s components expose Prometheus-only metrics (CoreDNS, etcd, kubelet)?
- OTel Collector Prometheus receiver configuration patterns
- When remote-write is needed vs direct scraping
- OTLP-native alternatives where they exist

### k8sattributes Processor
- Configuration patterns for enriching app telemetry with K8s metadata
- Mapping K8s Well-Known Labels to OTel resource attributes
- Organization-specific label propagation
- Performance considerations at scale

### OTel Operator
- CRD-based collector deployment patterns
- Auto-instrumentation injection for K8s workloads
- How the Operator relates to the blueprint's recommendations

### Golden Signals per Domain
- Application workloads: resource utilization, K8s events, workload state, probe health
- Cluster infrastructure: component health, DNS resolution, storage availability, autoscaler decisions
- What community dashboards and alert rules already exist for these?

---

## Action 4: Attend SIG End-User Meetings

**Why**: Scope decisions are happening in calls, not just in issue comments. alemferreira mentioned registering for the SIG meetings. Being present when scope is discussed prevents misalignment.

**What to do**:
- Join the OTel End-User SIG meeting (check CNCF calendar)
- Join `#otel-user-sig` on CNCF Slack if not already there
- Listen for scope decisions on #247 and template progress on #235

---

## Action 5: Prepare Example Configurations (After Scope Agreement)

**Why**: The blueprint will need concrete, tested examples. Having these ready accelerates writing.

**What to prepare** (only after scope is agreed):
- OTel Collector config for K8s workload monitoring
- `k8sattributes` processor enrichment config
- Prometheus receiver config for KSM / node-exporter
- `k8sclusterreceiver` config as KSM alternative
- Dashboard queries for K8s golden signals (PromQL / LogQL)

---

## Action 6: Propose Introduction / Summary Split for the Template

**Why**: The Rumelt-based blueprint template (#235) starts with a Summary section. There may be value in separating the "who is this for and what do they achieve" framing (Introduction) from the "what capabilities does this blueprint deliver" description (Summary). This makes it easier for a reader to decide if the blueprint is relevant before reading what it contains.

**What to propose**: Suggest to daniel that the template benefit from an Introduction section before the Summary. The Introduction establishes audience, environment, achievable end state, and business benefits. The Summary then describes the capabilities that deliver those benefits. See Appendix B for drafted sections applied to the K8s blueprint.

**Where to raise it**: Comment on #235 or bring it up in a SIG meeting. Frame it as a suggestion based on applying the template to #247 — the K8s blueprint scope work surfaced the need to separate "is this for me?" from "what does it cover?"

---

## What NOT to Do

- **Don't write the blueprint yet.** Template and scope must be agreed first.
- **Don't reference ContextCore in #247 discussions.** It's a different domain (project management vs K8s infrastructure). Your OTel expertise is relevant; the ContextCore product is not.
- **Don't propose `project.*` or `task.*` semconv in this context.** Those belong to your separate blueprint proposal (file `01-community-issue-blueprint-category.md`), not to the K8s observability blueprint.

---

## Appendix A: Proposed Scope (Prepared Feb 4)

This is the challenge-oriented scope rewrite prepared during the Feb 4 session. Use this as the basis for your comment on #247.

### Scope: Blueprint for Kubernetes Observability

This blueprint provides a known good path to observing Kubernetes clusters and workloads using OpenTelemetry. It is organized around common challenges faced by platform engineers and SREs, the benefits OTel provides for each, and concrete guidance to achieve those benefits.

#### Observability Domains

The blueprint covers two domains:

**Application Workloads** — Applications developed and maintained by the organization, observed through the lens of their execution on Kubernetes: resource consumption (CPU, memory, network, disk), K8s events affecting them (OOMKilled, scheduling failures, probe status), and workload state (replica counts, rollout status, restart patterns).

**Cluster Infrastructure** — Kubernetes-native components critical to cluster operation: CoreDNS, CNI, CSI, cloud provider integrations, ingress controllers, and autoscalers (HPA, VPA, Cluster Autoscaler, KEDA).

#### Challenges Addressed

**1. Tool and Daemonset Sprawl**

*Problem*: Monitoring stacks accumulate standalone deployments — KSM, node-exporter, various exporters — each consuming cluster resources and requiring independent lifecycle management.

*Benefit*: OTel Collectors can consolidate collection via `k8sclusterreceiver`, `kubeletstatsreceiver`, and Prometheus receivers, reducing operational surface area.

*Blueprint coverage*: Decision framework for when OTel receivers can replace standalone tooling, when they cannot yet, and migration paths for existing setups.

**2. OTLP Support vs Prometheus Interop**

*Problem*: Many K8s-native components (CoreDNS, etcd, kubelet) expose only Prometheus-format metrics. Organizations adopting OTLP face a mixed-protocol environment.

*Benefit*: OTel Collectors bridge this via Prometheus receivers while emitting OTLP downstream, enabling a unified pipeline without requiring upstream changes.

*Blueprint coverage*: For each in-scope component, state whether OTLP-native collection exists or whether a Prometheus receiver is required. Provide configuration patterns for both paths.

**3. KSM-less Cluster Monitoring**

*Problem*: kube-state-metrics has been the default for cluster state visibility, but it overlaps with OTel Collector capabilities and adds another component to maintain.

*Benefit*: The `k8sclusterreceiver` provides cluster state metrics natively within the collector, eliminating a standalone deployment for many use cases.

*Blueprint coverage*: Capability comparison between KSM and `k8sclusterreceiver`, gap analysis for metrics not yet covered, and a decision framework for when to cut over.

**4. Resource Semantic Convention Consistency Across Layers**

*Problem*: Application-level telemetry and infrastructure-level telemetry use inconsistent resource attributes, making it difficult to correlate an application error to the node, pod, or deployment that experienced it.

*Benefit*: The `k8sattributes` processor and Kubernetes Well-Known Labels provide a unified attribute set from infrastructure through application, enabling cross-layer correlation.

*Blueprint coverage*: Best practices for metadata enrichment using `k8sattributes`, mapping of Well-Known Labels to OTel semantic conventions, and patterns for organization-specific label propagation.

#### Golden Signals Baseline

For each domain, the blueprint will define a minimum viable set of metrics and signals — the golden set that any K8s observability setup should capture. This provides end-users with an actionable starting point rather than an exhaustive catalog.

| Domain | Signal Categories |
|--------|------------------|
| **Application Workloads** | Resource utilization, K8s events, workload state, restart/probe health |
| **Cluster Infrastructure** | Component health, DNS resolution, network path, storage availability, autoscaler decisions |

Known assets (community dashboards, alert rules) for each signal category will be referenced where available.

#### Additional Topics

- **OTel Operator**: CRD-based collector management and auto-instrumentation injection as the recommended K8s-native deployment model.
- **Autoscaling observability**: Telemetry for HPA, VPA, Cluster Autoscaler, and KEDA — scaling decisions are operational blind spots without dedicated signals.
- **Meta-monitoring**: Observability of the observability components themselves (is KSM / node-exporter / the collector healthy?).

#### Out of Scope

- **Collector deployment architecture** (scaling, topology, gateway patterns) — covered by #246.
- **SDK configuration and application-level instrumentation** — covered by #246.
- **Service mesh and eBPF-based network observability** — potential future blueprint.

---

## Appendix B: Introduction / Summary Draft (Prepared Feb 4)

This is a draft of the proposed Introduction and Summary sections for the K8s observability blueprint. Use this to illustrate the template split when discussing with daniel on #235, and as starting content for the blueprint itself once scope is agreed.

### Introduction

Kubernetes adoption has outpaced the tooling needed to observe it consistently. Platform engineering teams face a fragmented landscape: kube-state-metrics for cluster state, node-exporter for node health, Prometheus scrapers for control plane components, and application-level instrumentation — each deployed, configured, and maintained independently. The result is daemonset sprawl, inconsistent metadata across telemetry layers, and no reliable way to correlate an application error to the infrastructure condition that caused it.

This blueprint is for **platform engineers and SREs** responsible for observability across Kubernetes clusters. It assumes an environment where:

- One or more Kubernetes clusters run production workloads
- An OTLP-compatible backend is available or planned (Grafana stack, Datadog, Elastic, etc.)
- Some combination of KSM, node-exporter, and Prometheus scraping is already in place
- The team is evaluating or adopting OpenTelemetry Collectors

The achievable end state is a **consolidated, OTel-native observability posture** for Kubernetes where:

- A single collection layer (OTel Collectors) replaces multiple standalone monitoring deployments
- Application telemetry and infrastructure telemetry share consistent resource attributes, enabling cross-layer correlation
- Every in-scope K8s component has a defined collection path — OTLP-native where available, Prometheus receiver where not
- A golden set of signals per domain provides a minimum viable baseline that any team can adopt without designing from scratch

The business benefits are direct: fewer components to operate and secure, faster mean-time-to-correlate during incidents, and a consistent observability baseline that scales across clusters without per-cluster custom configuration.

### Summary

This blueprint delivers four capabilities that address the challenges above:

**Consolidated collection architecture.** OTel Collector receivers (`k8sclusterreceiver`, `kubeletstatsreceiver`, Prometheus receiver) can replace standalone deployments like KSM and node-exporter in many scenarios. The blueprint provides a decision framework for when to consolidate, when standalone tooling is still required, and migration paths for teams with existing dashboards and alerts built against KSM metric names.

**Component-level collection guidance.** For each Kubernetes component in scope — application workloads, CoreDNS, CNI, CSI, ingress controllers, and autoscalers — the blueprint specifies the collection method (OTLP-native vs Prometheus receiver), the receiver configuration, and the relevant semantic conventions. This eliminates the per-component research each team currently does independently.

**Cross-layer metadata enrichment.** The `k8sattributes` processor and Kubernetes Well-Known Labels provide the mechanism to attach consistent resource attributes (namespace, deployment, node, pod) to all telemetry regardless of source. The blueprint defines enrichment patterns that bridge application-level and infrastructure-level telemetry into a correlated view.

**Golden signals baseline.** For each observability domain (application workloads, cluster infrastructure), the blueprint defines a minimum viable set of metrics and signals. This gives teams an actionable starting point — not an exhaustive catalog, but the signals that matter most — along with references to existing community dashboards and alert rules where available.

---

*The Introduction tells the reader whether this blueprint is for them and what they'll achieve. The Summary tells them what specific capabilities the blueprint provides to get there. The Diagnosis, Guiding Policies, and Coherent Actions sections that follow then deliver on the Summary's promises in detail.*
