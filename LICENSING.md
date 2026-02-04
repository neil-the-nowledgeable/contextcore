# Licensing

ContextCore uses a dual-license structure that separates the open specification from the commercial implementation.

## Specification (Apache License 2.0)

The following files define the ContextCore specification and are licensed under the [Apache License 2.0](LICENSE-APACHE). You are free to build your own implementations against these specs.

- `docs/semantic-conventions.md` — Attribute and metric reference
- `docs/agent-semantic-conventions.md` — Agent attribute conventions
- `docs/agent-communication-protocol.md` — Agent integration protocol
- `docs/OTEL_GENAI_MIGRATION_GUIDE.md` — OTel GenAI migration guide
- `docs/DEPENDENCY_MANIFEST_PATTERN.md` — Dependency manifest pattern
- `docs/NAMING_CONVENTION.md` — Animal naming convention
- `docs/adr/` — Architecture decision records
- `crds/` — Kubernetes CRD definitions
- `terminology/` — Wayfinder terminology definitions

## Implementation (FSL-1.1-ALv2)

Everything else — including source code, tests, examples, Helm charts, dashboards, extensions, Kubernetes manifests, scripts, and expansion packs — is licensed under the [Functional Source License, Version 1.1, ALv2 Future License](LICENSE).

This includes:

- `src/` — Python source code
- `tests/` — Test suite
- `examples/` — Usage examples
- `helm/` — Helm charts
- `grafana/` — Dashboard provisioning and JSON models
- `extensions/` — VSCode extension
- `k8s/` — Kubernetes manifests
- `scripts/` — Build and integration scripts
- `contextcore-rabbit/` — Rabbit expansion pack
- `contextcore-owl/` — Owl expansion pack

## What FSL-1.1-ALv2 Means

The Functional Source License is not an open-source license. It allows use, modification, and redistribution for any purpose **except** offering the Licensed Work as a competing commercial product or service. After the Change Date (two years from each release), the code automatically converts to the **Apache License 2.0**, becoming fully open source.

Licensor: **Force Multiplier Labs**

For questions about licensing, contact Force Multiplier Labs.
