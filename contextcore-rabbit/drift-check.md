# Drift Check: What It Does and Why

## The Problem It Solves

The observability stack (Grafana, Loki, Mimir, Tempo, Pyroscope) stores data on PersistentVolumeClaims. If a deployment's volume is changed from a PVC to `emptyDir`, the pod keeps running, health checks keep passing, and Grafana keeps serving pages -- but all stored data is gone the next time the pod restarts. Nothing alerts. Nothing looks broken. The data just silently disappears.

This happened repeatedly over 19 days before anyone noticed. The live cluster state had drifted from what the on-disk manifests specified, and no system was comparing the two.

Drift check closes that gap. It answers one question: **does what's running in the cluster match what's declared in the protection descriptor?**

## What It Does

The script performs three steps:

### 1. Reads the protection descriptor

It parses `observability/pvc-protection.yaml`, which declares the five protected volume bindings:

| Deployment | Volume Name | Expected PVC | Mount Path |
|------------|-------------|-------------|------------|
| grafana | grafana-storage | grafana-pvc | /var/lib/grafana |
| loki | storage | loki-pvc | /loki |
| mimir | storage | mimir-pvc | /data |
| tempo | storage | tempo-pvc | /tmp/tempo |
| pyroscope | storage | pyroscope-pvc | /data |

This file is the single source of truth. The drift check script, the webhook, the emergency restore script, and the hook all read from it. Adding a new protected volume means editing one file.

### 2. Queries the live cluster

For each protected deployment, it runs `kubectl get deployment <name> -n observability -o json` and extracts the actual volume spec. It checks:

- Is the named volume present in the deployment?
- Is it a `persistentVolumeClaim` type?
- Does the `claimName` match the expected PVC?

### 3. Reports the comparison

It outputs a table showing expected vs. actual state for each deployment:

```
=== Observability PVC Drift Check ===

DEPLOYMENT   EXPECTED             ACTUAL                         STATUS
----------   --------             ------                         ------
grafana      pvc:grafana-pvc      pvc:grafana-pvc                OK
loki         pvc:loki-pvc         pvc:loki-pvc                   OK
mimir        pvc:mimir-pvc        emptyDir (DATA LOSS RISK)      DRIFTED
tempo        pvc:tempo-pvc        pvc:tempo-pvc                  OK
pyroscope    pvc:pyroscope-pvc    pvc:pyroscope-pvc              OK

DRIFT DETECTED: 1 deployment(s) have incorrect volume bindings.

To fix: make fix-drift
   or:  ./scripts/emergency-restore.sh
```

Statuses are color-coded: green for OK, red for DRIFTED, yellow for MISSING or UNKNOWN.

## Why Each Check Matters

| Status | What It Means | Why It's Dangerous |
|--------|---------------|-------------------|
| **OK** | PVC name matches expected. Data is persistent. | Not dangerous -- this is the correct state. |
| **DRIFTED** (emptyDir) | Volume was replaced with ephemeral storage. | Data survives only as long as the current pod. A restart, rollout, or node drain destroys everything. |
| **DRIFTED** (hostPath) | Volume was replaced with a node-local path. | Data is tied to one specific node. Pod rescheduling to another node loses it. Not portable, not backed up. |
| **WRONG_PVC** | Volume is a PVC but with the wrong claim name. | Data is persistent but pointing at the wrong storage. Could be reading stale data or writing to an unmonitored volume. |
| **MISSING** | The deployment doesn't exist in the cluster. | The component isn't running at all. No data is being collected. |
| **volume-not-found** | The deployment exists but the expected volume name isn't in its spec. | The deployment was reconstructed from scratch and the volume was omitted entirely. |

## Why This Exists

Prevention (the hook, the webhook) can block known-bad commands. But prevention has gaps:

- The hook only runs inside Claude Code sessions
- The webhook can be bypassed if its pod is down
- Neither catches novel attack vectors not yet anticipated

Drift check is the **detection** layer. It doesn't care *how* the state changed -- it only cares *whether* the state matches what's expected. A direct `kubectl` from the terminal, a CI pipeline, a Helm upgrade, a future tool that doesn't exist yet -- if any of them change a protected volume, drift check will catch it.

Prevention answers "should I allow this action?" Detection answers "is the system in the correct state?" Both are needed because neither is complete on its own.

## How to Use It

```bash
# Interactive check with colored table output
make drift-check

# JSON output for automation
./scripts/drift-check.sh --json

# Exit code only (0=clean, 1=drifted, 2=error)
./scripts/drift-check.sh --quiet

# Fix detected drift by re-applying canonical manifests
make fix-drift

# Watch continuously (checks every 60 seconds)
make watch-drift
```

## What It Doesn't Do

- It does not **prevent** drift. That's the hook and webhook's job.
- It does not **fix** drift. That's `make fix-drift` or `./scripts/emergency-restore.sh`.
- It does not run **continuously**. It checks at the moment you invoke it. For continuous monitoring, a Kubernetes CronJob would need to run this script on a schedule and push results to an alerting system.
- It does not check **ConfigMap values**. A misconfigured `ingestion_rate: 0` in a Mimir ConfigMap (which silently blocks all metrics) is invisible to drift check. It only validates volume bindings.
