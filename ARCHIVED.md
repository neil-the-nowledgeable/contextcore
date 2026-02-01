# ARCHIVED

**This repository has been archived.** It is preserved for historical reference only.

## What Happened

The ContextCore monorepo has been separated into two focused repositories:

| Repository | Purpose | Location |
|------------|---------|----------|
| **contextcore-spec** | The ContextCore metadata standard (schemas, semantic conventions, protocols, terminology) | `~/Documents/dev/contextcore-spec/` |
| **wayfinder** | The reference implementation (Python SDK, CLI, dashboards, expansion packs) | `~/Documents/dev/wayfinder/` |

## Where to Go

- **To work on the implementation**: `cd ~/Documents/dev/wayfinder/`
- **To work on the spec**: `cd ~/Documents/dev/contextcore-spec/`

## Reference Points

| Tag/Branch | Purpose |
|------------|---------|
| `pre-separation-snapshot` | State of the monorepo before separation began |
| `archive/pre-separation` | Branch preserving the pre-separation state |
| `archived-post-separation` | Final state after separation and archival |

## Decision Record

See [ADR-003: Monorepo Separation](https://github.com/forcemultiplier-labs/wayfinder/blob/main/docs/adr/003-monorepo-separation.md) in the wayfinder repo for the full rationale.

## Do Not

- Do not make new commits to this repository
- Do not start new feature work here
- Do not deploy from this repository

All development continues in the **wayfinder** and **contextcore-spec** repos.
