# Prime Contractor Git Safety: Pre-flight Repository Checks

## Problem Statement

The Prime Contractor workflow modifies files during integration but does not verify the repository state before starting. This can result in:

1. **Uncommitted work being overwritten** - Generated code replaces files with pending changes
2. **Unclear baseline** - Hard to know what the codebase looked like before integration
3. **Difficult rollback** - No clean git history to revert to if integration fails catastrophically
4. **Merge confusion** - Mixed changes (manual + generated) in the same uncommitted state

### Evidence

During contextcore-mole integration:
- `parser.py` was overwritten, losing original functions
- `cli.py` was completely replaced with generated code
- Backup files (`.backup`) were created but git state was not checked

---

## Phased Approach

### Phase 1: Simple (Pre-flight Warning)

**Goal**: Alert the user when the repo has uncommitted changes, but don't block.

**Implementation**:
```python
def check_git_status(self) -> tuple[bool, list[str]]:
    """Check if git repo is clean. Returns (is_clean, dirty_files)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=self.project_root
    )
    dirty_files = [line.strip() for line in result.stdout.strip().split('\n') if line]
    return len(dirty_files) == 0, dirty_files
```

**Behavior**:
- Run at start of `workflow.run()`
- Print warning if dirty: `"⚠️  Repository has uncommitted changes"`
- List affected files
- Continue anyway (no blocking)

**Effort**: ~20 lines of code

**Value**: Immediate awareness without workflow disruption

---

### Phase 2: Basic (Blocking with Override)

**Goal**: Require clean repo by default, allow `--force` to proceed anyway.

**Implementation**:
- Add `--force` / `--allow-dirty` CLI flag
- Block workflow if repo is dirty (unless forced)
- Suggest `git stash` or `git commit` before proceeding

**Behavior**:
```
❌ BLOCKED: Repository has uncommitted changes

  Modified files:
    M  src/contextcore_mole/parser.py
    M  src/contextcore_mole/cli.py

  Options:
    1. Commit your changes:  git add . && git commit -m "WIP"
    2. Stash your changes:   git stash
    3. Force proceed:        --allow-dirty (not recommended)

Aborting to protect your uncommitted work.
```

**CLI Addition**:
```bash
python3 scripts/prime_contractor/cli.py run --allow-dirty  # Override safety
```

**Effort**: ~50 lines of code + CLI flag

**Value**: Protects uncommitted work by default

---

### Phase 3: Thoughtful Holistic Approach

**Goal**: Full repository safety with intelligent handling and recovery options.

#### 3.1 Pre-flight Checks

| Check | Behavior | Recovery |
|-------|----------|----------|
| Uncommitted changes | Block (unless `--allow-dirty`) | Suggest stash/commit |
| Untracked files in target paths | Warn | Show files, suggest add/ignore |
| Detached HEAD | Warn | Suggest creating branch |
| Merge/rebase in progress | Block | Suggest complete/abort |
| Branch behind remote | Warn | Suggest pull |

#### 3.2 Automatic Snapshot

Before modifying any files, automatically create a safety commit or stash:

```python
def create_safety_snapshot(self) -> str:
    """Create a safety snapshot before integration."""
    if self.auto_snapshot:
        # Stash all changes with descriptive message
        timestamp = datetime.now().isoformat()
        result = subprocess.run(
            ["git", "stash", "push", "-m",
             f"prime-contractor-snapshot-{timestamp}"],
            capture_output=True, text=True
        )
        return result.stdout.strip()
    return ""
```

**CLI Options**:
```bash
--auto-stash       # Automatically stash before starting (can recover with git stash pop)
--auto-commit      # Commit each feature (existing)
--snapshot-branch  # Create a snapshot branch before starting
```

#### 3.3 Target File Protection

Before overwriting any file, check if it's been modified since last commit:

```python
def is_file_dirty(self, path: Path) -> bool:
    """Check if a specific file has uncommitted changes."""
    result = subprocess.run(
        ["git", "diff", "--name-only", str(path)],
        capture_output=True, text=True
    )
    return bool(result.stdout.strip())

def protect_dirty_target(self, path: Path) -> bool:
    """Refuse to overwrite a file with uncommitted changes."""
    if self.is_file_dirty(path):
        print(f"  ⛔ Cannot overwrite {path.name}: has uncommitted changes")
        print(f"     Commit or stash changes first, then retry")
        return False
    return True
```

#### 3.4 Recovery Mechanism

If workflow fails mid-integration:

```bash
# Show what happened
python3 scripts/prime_contractor/cli.py recovery-status

# Restore to pre-integration state
python3 scripts/prime_contractor/cli.py recover --to-snapshot

# Recover specific file from backup
python3 scripts/prime_contractor/cli.py recover --file src/parser.py
```

#### 3.5 Updated Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PRIME CONTRACTOR WORKFLOW                        │
│                      (with Git Safety)                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐                                                    │
│  │  PRE-FLIGHT  │                                                    │
│  │    CHECKS    │                                                    │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────┐    NO     ┌──────────────┐                        │
│  │  Repo Clean? │─────────▶ │    BLOCK     │                        │
│  └──────┬───────┘           │ (or --force) │                        │
│         │ YES               └──────────────┘                        │
│         ▼                                                            │
│  ┌──────────────┐                                                    │
│  │   SNAPSHOT   │  (optional: --auto-stash)                         │
│  └──────┬───────┘                                                    │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐       │
│  │ Feature  │───▶│ Generate │───▶│Integrate │───▶│Checkpoint│       │
│  │    N     │    │  (Lead)  │    │  (Prime) │    │  Validate│       │
│  └──────────┘    └──────────┘    └────┬─────┘    └────┬─────┘       │
│                                       │               │              │
│                           ┌───────────┘               │              │
│                           ▼                           │              │
│                  ┌──────────────┐                     │              │
│                  │ Target File  │  FAIL ──────────────┼──▶ RECOVER  │
│                  │   Dirty?     │                     │              │
│                  └──────┬───────┘                     │              │
│                         │ NO                          │              │
│                         ▼                             ▼ PASS         │
│                  ┌──────────────┐             ┌──────────────┐       │
│                  │    WRITE     │             │   COMPLETE   │       │
│                  │    FILE      │             └──────────────┘       │
│                  └──────────────┘                                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan (Using Prime Contractor)

We will use the Prime Contractor workflow itself to implement these features incrementally.

### Feature Queue

```bash
# Add features in dependency order
cd ~/Documents/dev/ContextCore

python3 scripts/prime_contractor/cli.py add "Git Status Check" \
  --description "Add check_git_status() method to PrimeContractorWorkflow. Returns (is_clean, dirty_files). Call at start of run() and print warning if dirty." \
  --target-files scripts/prime_contractor/workflow.py

python3 scripts/prime_contractor/cli.py add "Allow Dirty Flag" \
  --description "Add --allow-dirty CLI flag. Block run() if repo dirty unless flag set. Print helpful message with options (commit, stash, force)." \
  --depends-on git_status_check \
  --target-files scripts/prime_contractor/workflow.py scripts/prime_contractor/cli.py

python3 scripts/prime_contractor/cli.py add "Auto Stash Option" \
  --description "Add --auto-stash flag. If set and repo dirty, automatically stash changes before starting. Store stash ref for recovery. Print stash name." \
  --depends-on allow_dirty_flag \
  --target-files scripts/prime_contractor/workflow.py scripts/prime_contractor/cli.py

python3 scripts/prime_contractor/cli.py add "Target File Protection" \
  --description "Before overwriting any target file, check if it has uncommitted changes. Refuse to overwrite dirty targets. Suggest commit/stash first." \
  --depends-on git_status_check \
  --target-files scripts/prime_contractor/workflow.py

python3 scripts/prime_contractor/cli.py add "Recovery Command" \
  --description "Add 'recover' CLI command. Options: --to-snapshot (pop stash), --file PATH (restore from .backup). Show recovery-status." \
  --depends-on auto_stash_option \
  --target-files scripts/prime_contractor/cli.py
```

### Execution

```bash
# Step 1: Commit current state (practice what we preach!)
git add -A && git commit -m "WIP: Before git safety implementation"

# Step 2: Check queue
python3 scripts/prime_contractor/cli.py status

# Step 3: Run one feature at a time
python3 scripts/prime_contractor/cli.py run --max-features 1 --auto-commit

# Step 4: Test the new feature manually
git status  # Should be clean
# ... make a change ...
python3 scripts/prime_contractor/cli.py run  # Should warn about dirty repo

# Step 5: Continue with next feature
python3 scripts/prime_contractor/cli.py run --max-features 1 --auto-commit
```

---

## Success Criteria

### Phase 1 (Simple)
- [ ] Warning printed when repo has uncommitted changes
- [ ] Workflow continues after warning
- [ ] No behavior change for clean repos

### Phase 2 (Basic)
- [ ] Workflow blocks by default when repo is dirty
- [ ] `--allow-dirty` flag overrides block
- [ ] Clear error message with recovery options

### Phase 3 (Holistic)
- [ ] `--auto-stash` creates recoverable snapshot
- [ ] Target files with uncommitted changes are protected
- [ ] `recover` command can restore from stash/backup
- [ ] Documentation updated with new safety features

---

## Documentation Updates Required

1. **PRIME_CONTRACTOR_WORKFLOW.md** - Add "Git Safety" section
2. **CLI Reference** - Add new flags and commands
3. **Troubleshooting** - Add recovery scenarios
4. **Best Practices** - Recommend clean repo before running

---

## Related Files

| File | Changes |
|------|---------|
| `scripts/prime_contractor/workflow.py` | Add git safety methods |
| `scripts/prime_contractor/cli.py` | Add flags and recover command |
| `docs/PRIME_CONTRACTOR_WORKFLOW.md` | Document new features |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Git commands fail on non-git repos | Check for `.git` directory first |
| Stash conflicts on pop | Keep stash ref, allow manual recovery |
| Performance impact | Git status is fast (~10ms) |
| Breaking existing workflows | All new behavior is opt-in or warning-only initially |

---

## Timeline

| Phase | Effort | Features |
|-------|--------|----------|
| Phase 1 | 1 feature | Warning only |
| Phase 2 | 2 features | Block + override |
| Phase 3 | 3 features | Full safety suite |

**Total: 5 features via Prime Contractor**
