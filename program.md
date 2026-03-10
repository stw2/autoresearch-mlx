# autoresearch — looped single-session protocol

This is a hypothesis-driven experiment protocol designed for an outer loop. Each agent session gets **fresh context**, investigates **exactly one hypothesis**, publishes the result as a **nanopublication** to the shared memory substrate (`memory/`), records the session plus log path in `memory/sessions/`, and then stops. The next session starts from scratch, reads memory, picks the next best hypothesis, and repeats.

## Setup

At the start of each session:

1. **Read the repo**: The repo is small. Read these files for full context:
   - `README.md` — repository context.
   - `prepare.py` — fixed constants, data prep, tokenizer, dataloader, evaluation. Do not modify.
   - `train.py` — the file you modify. Model architecture, optimizer, training loop.
   - This file (`program.md`) — your operating protocol.
2. **Create the session branch**: `git switch -c autoresearch/<tag>` using a tag based on today's date and agent (e.g. `mar8-claude`). The branch must not already exist.
3. **Verify data exists**: Check that `~/.cache/autoresearch/` contains data shards and a tokenizer. If not, abort and report the missing data.
4. **Initialize memory** (if needed): `uv run memory.py init` — idempotent, safe to re-run.
5. **Proceed immediately** into the loop contract below. Do not wait for human approval.

## Loop contract

Treat this file as the instructions for **one** unit of work in a larger orchestrator loop:

1. Start with fresh context.
2. Read repo + memory state.
3. Choose one falsifiable hypothesis.
4. Run enough experiments to support or refute it.
5. Publish the synthesized result to `memory/`.
6. Exit cleanly.

Do not try to preserve long in-session working memory across multiple hypotheses. The durable state lives in git, `memory/`, and any committed experiment artifacts.

## The memory substrate

The `memory/` directory is the shared cross-session memory:

- **Nanopubs** (`memory/layer1/`): Synthesized findings from experiment sessions. Each is a `.md` file with YAML frontmatter (structured metadata) and a markdown body (evidence and analysis).
- **Sessions** (`memory/sessions/`): Per-session coordination records. The full launcher transcript lives at the path recorded in each session YAML via `$AUTORESEARCH_SESSION_LOG`.

### Reading the memory

At the start of each session:

1. **Sync from the memory branch**: `loop.sh` normally checks out `memory/` from `AUTORESEARCH_MEMORY_BRANCH` (default: `autoresearch-memory`) into the fresh session worktree before the agent starts. If you need to re-sync manually and the branch exists locally, run `git checkout "$AUTORESEARCH_MEMORY_BRANCH" -- memory/`.
2. **Get orientation**: `uv run memory.py status` — shows recent nanopubs and active sessions
3. **Read relevant nanopubs**: Based on the status output, read specific files from `memory/layer1/` that relate to your planned investigation
4. **Check active sessions**: Look at `memory/sessions/*.yaml` to see what other agents are currently investigating and what prior logs/artifacts were saved — avoid duplicating work

### Writing to the memory

When you publish findings:

1. **Write the nanopub**: Copy `memory/template-nanopub.md`, fill it in, save to `memory/layer1/<id>.md`
2. **Update your session file**: Set status to `completed`, add the nanopub ID to `publications`, set final `experiment_count`, and record the full-session log path from `$AUTORESEARCH_SESSION_LOG`
3. **Publish memory via the helper**:
   ```bash
   uv run memory.py publish "publish <nanopub-id>: <short title>"
   ```
4. **Do not stash or check out the default branch from the session worktree**. Memory publication is isolated onto the dedicated `AUTORESEARCH_MEMORY_BRANCH` branch.

## The looped session

Each session investigates exactly **one** hypothesis. The outer loop provides iteration; the session itself does not. That one hypothesis follows six phases:

### Phase 1: Orient

- Sync and read the memory (see above)
- Identify gaps in the published evidence
- Look for contradictions or low-confidence findings that could be strengthened
- Consider what the existing body of knowledge suggests as next steps

### Phase 2: Hypothesize

- Formulate a **specific, falsifiable** claim. Good: "Increasing FFN width from 4x to 6x improves val_bpb when depth is held at 8 layers." Bad: "Changing the architecture might help."
- Check that the hypothesis is **novel** — not already thoroughly covered by an existing nanopub with `confidence: high`
- Create a session file at `memory/sessions/<session-id>.yaml`:
  ```yaml
  session_id: <tag>-01
  agent: claude  # or codex
  branch: autoresearch/<tag>
  started: <ISO timestamp>
  hypothesis: "<your hypothesis>"
  status: active
  publications: []
  experiment_count: 0
  log_path: <value of AUTORESEARCH_SESSION_LOG, typically .git/autoresearch/session-logs/...>
  ```
- Publish the new session file with `uv run memory.py publish "publish session <session-id>: start tracking"` so other fresh sessions can see it

### Phase 3: Design

Plan a sequence of experiments. Every plan must include:

- **At least 1 control**: Run baseline or minimal-change variant for comparison
- **At least 1 falsification test**: An experiment that would *disprove* the hypothesis if it fails. This is the most important experiment — design it first.
- **Supporting experiments**: Vary the parameter of interest to map the effect
- Target **4–10 experiments** total per hypothesis

### Phase 4: Execute

Run experiments one at a time. For each experiment:

1. Start from the current best commit on `autoresearch/<tag>`.
2. Create a unique run branch from that best commit, for example: `git switch -c autoresearch/<tag>/run-001`
3. Edit `train.py` with the experimental change.
4. `git commit` the change. Every run must have its own commit before launch.
5. Save the full commit SHA with `git rev-parse HEAD`. Never log short SHAs in `results.tsv`.
6. Run: `uv run train.py > run.log 2>&1`
7. Record durable provenance immediately after the run:
   ```bash
   uv run memory.py record-run \
     --session-id "<session-id>" \
     --run-id "run-001" \
     --base-commit "<full-best-commit-sha>" \
     --status keep \
     --description "short description of the change" \
     --run-log run.log
   ```
   `record-run` copies `run.log` into `memory/sessions/runs/<session-id>/<run-id>/`, writes `run.json`, saves a `train.py` patch plus snapshot, and appends a row to `results.tsv`.
8. If the run crashed before producing metrics, rerun `record-run` with `--status crash` after capturing the failure log.
9. If val_bpb improved: fast-forward the session branch so it points at this run commit.
10. If val_bpb is equal or worse: switch back to the session branch and leave the run branch plus recorded artifacts intact. Do **not** use `git reset`.

The key property is isolation: every run starts from the best commit in a fresh branch, and every run leaves behind a recoverable commit plus artifacts.

**Adapt as you go**: If early results clearly confirm or refute the hypothesis, you can adjust the remaining experiments. But don't abandon the falsification test.

**Timeout**: Kill runs exceeding 10 minutes and treat as failure.

### Phase 5: Synthesize

After running enough experiments (minimum 4), synthesize your findings:

1. Review all experiment results from this hypothesis
2. Classify each experiment as **supporting**, **contradicting**, or **ambiguous**
3. Write a nanopub using the template at `memory/template-nanopub.md`:

**Nanopub ID format**: `np-YYYYMMDD-NNN` (date + sequence number, check layer1/ for existing IDs)

**Frontmatter** (all fields required):
```yaml
---
id: np-YYYYMMDD-NNN
title: "Short descriptive title"
published: <ISO timestamp>
agent: claude  # or codex
session: <session-id>
confidence: low | moderate | high
status: active
supersedes: null  # ID of nanopub this replaces, if any
evidence:
  supporting: <count>
  contradicting: <count>
  ambiguous: <count>
  baseline_bpb: <value>
---
```

**Body** — use these suggested sections (adapt as needed):
- **Assertion**: The core claim in 1–3 sentences
- **Evidence**: Table of experiments with commit, val_bpb, delta from baseline, description, and verdict
- **Conditions**: What was held constant (time budget, platform, model size, optimizer settings)
- **Falsification**: What was tested that could have disproved the hypothesis, and what happened
- **Implications**: What follow-up work this suggests, what concepts it interacts with

**Confidence calibration** — be honest:
- `low`: Fewer than 4 supporting experiments, OR high variance across runs, OR no falsification attempted, OR effect size < ~0.001 bpb (within run-to-run noise)
- `moderate`: 4+ supporting experiments, falsification attempted, results mostly consistent
- `high`: 6+ supporting experiments, falsification attempted and survived, low variance, at least 1 reproduction run

### Phase 6: Publish

1. Save the nanopub to `memory/layer1/<id>.md`
2. Update your session file: set `status: completed`, add the nanopub ID to `publications`, set final `experiment_count`, and save `log_path: <AUTORESEARCH_SESSION_LOG>`
3. The launcher captures the full agent stdout/stderr to `$AUTORESEARCH_SESSION_LOG`; make sure that path is preserved in the session YAML after publishing so future sessions can inspect the full transcript
4. Publish memory with `uv run memory.py publish "publish <nanopub-id>: <short title>"`
5. Return to your session branch if needed, then end the session

### Then what?

After publishing, end the session. Do **not** start a second hypothesis in the same context window.

The next iteration should be a brand new agent session that:
- reads `memory/` again from scratch
- uses the latest nanopubs and active/completed sessions for orientation
- selects one next hypothesis based on current evidence gaps
- repeats the same process

## What you CAN do

- Modify `train.py` — this is the only file you edit for experiments. Everything is fair game: model architecture, optimizer, hyperparameters, training loop, batch size, model size, etc.
- Read and write files in `memory/` — this is how you communicate with other agents.
- Create and update your session file in `memory/sessions/`.

## What you CANNOT do

- Modify `prepare.py`. It is read-only.
- Install new packages or add dependencies.
- Modify the evaluation harness.
- Modify other agents' nanopubs (you can *supersede* them by publishing a new nanopub with `supersedes: <id>`).

## Methodological rules

**The goal is lowest val_bpb.** Since the time budget is fixed at 5 minutes, everything is fair game.

**VRAM** is a soft constraint. Some increase is acceptable for meaningful val_bpb gains.

**Simplicity criterion**: All else equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Removing code for equal results is a win.

**Anti-confirmation bias**:
- Before concluding "X helps," you must have run at least one experiment where X should hurt (the falsification test). If you skip this, your confidence must be `low`.
- Report contradicting evidence prominently in the nanopub, not buried or explained away.
- If the effect size is smaller than run-to-run variance (~0.001 bpb), confidence must be `low` regardless of how many experiments you ran.

**Stopping criteria for a hypothesis**:
- Stop if 3 consecutive experiments produce consistent results (all supporting or all contradicting)
- Stop if the falsification experiment clearly refutes the hypothesis — publish it as a negative result (these are valuable!)
- Abandon (skip publishing) only if experiments are fundamentally broken (crashes, confounds that invalidate all data)

**Negative results are first-class**: A nanopub that says "GeLU provides no benefit over ReGLU-square in this context, confidence: high" is just as valuable as a positive finding. Publish it.

**STOP AFTER PUBLISHING**: Once the session has begun, do NOT pause to ask the human whether to continue the same hypothesis unless you are blocked. Finish the investigation, synthesize, publish, and then end the session so the outer loop can relaunch with clean context.

## Output format

The training script prints a summary like this after each run:

```
---
val_bpb:          0.997900
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     45060.2
mfu_percent:      39.80
total_tokens_M:   499.6
num_steps:        953
num_params_M:     50.3
depth:            8
```

`uv run memory.py record-run ...` extracts `val_bpb` and `peak_vram_mb` from `run.log` automatically.

## Logging results

Log every experiment to `results.tsv` (tab-separated) immediately after the run completes. The TSV now has 9 columns:

```
session_id	run_id	commit_sha	base_commit	val_bpb	memory_gb	status	artifact_dir	description
```

1. session identifier, e.g. `mar10-codex-01`
2. run identifier within that session, e.g. `run-003`
3. full git commit SHA for the experiment commit
4. full git commit SHA for the best commit the run branched from
5. val_bpb achieved — use `0.000000` for crashes
6. peak memory in GB, rounded to `.1f` — use `0.0` for crashes
7. status: `keep`, `discard`, or `crash`
8. durable artifact directory under `memory/sessions/runs/`
9. short text description of what this experiment tried

`uv run memory.py record-run ...` appends this row for you and writes the matching artifact directory. Do not wait until the end of the hypothesis to backfill it.

