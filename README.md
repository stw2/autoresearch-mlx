# autoresearch-mlx

Apple Silicon [MLX](https://github.com/ml-explore/mlx) port of [Karpathy's autoresearch](https://github.com/karpathy/autoresearch), adapted to a looped single-session workflow.

Instead of one endlessly running agent session, this fork treats each run as exactly one hypothesis-driven investigation:

- the agent starts with fresh context
- reads the shared `memory/` state
- investigates one falsifiable hypothesis
- publishes a nanopublication to `memory/layer1/`
- records the session in `memory/sessions/`
- exits so an outer launcher can start the next fresh session

The training target is still the same: minimize `val_bpb` under a fixed 5-minute training budget on Apple Silicon.

## Repository layout

- `prepare.py` downloads data, trains the tokenizer, builds the dataloader, and defines evaluation. Do not modify it during experiments.
- `train.py` contains the model, optimizer, and training loop. This is the main experiment surface.
- `program.md` is the per-session protocol the agent follows.
- `memory.py` bootstraps and summarizes the shared `memory/` substrate.
- `loop.sh` is the outer launcher that repeatedly starts fresh agent sessions.
- `results.tsv` is the append-only run log for experiment outcomes.

## Quick start

Requirements: Apple Silicon Mac, Python 3.10+, and `uv`.

```bash
# install dependencies
uv sync

# one-time data preparation
uv run prepare.py

# initialize shared memory state
uv run memory.py init

# optional: inspect current memory status
uv run memory.py status

# run one training job manually
uv run train.py
```

## Running the loop

Use `loop.sh` to launch repeated fresh agent sessions from the repo root:

```bash
./loop.sh claude
./loop.sh codex 5
```

- Supported agents are `claude` and `codex`.
- The second argument is the iteration count. Omit it or pass `0` to run indefinitely.
- `loop.sh` refuses to start if the source checkout is dirty.
- Each iteration runs in a fresh temporary git worktree rooted at the default branch.
- If `autoresearch-memory` exists locally, the launcher syncs `memory/` from that branch into the fresh worktree before starting the agent.
- Each iteration writes a full transcript to a launcher-managed session log outside the source checkout so the source tree stays clean.
- `loop.sh` reads the default prompt from the `## Running the agent` section below.

## Running the agent

```
Your task is to run one complete autoresearch session right now. Do not wait for further instructions.

Start immediately:
1. Read `README.md`, `program.md`, `prepare.py`, and `train.py` to understand the codebase and protocol.
2. Read the memory state with `uv run memory.py status` and any existing nanopubs in `memory/layer1/`.
3. Follow `program.md` end-to-end for exactly one hypothesis: orient, hypothesize, design, execute experiments, synthesize, and publish.
4. Publish results with `uv run memory.py publish "publish <nanopub-id>: <short title>"`.
5. Exit — do not start a second hypothesis.

If `memory/` is missing, initialize it first with `uv run memory.py init`.
```

## Memory substrate

The shared `memory/` directory is the durable cross-session state:

- `memory/layer1/` stores nanopublications with YAML frontmatter plus supporting analysis.
- `memory/sessions/` stores active and completed session records.
- `memory/sessions/runs/` stores per-run provenance artifacts such as `run.json`, `train.patch`, and preserved `run.log` files.

Canonical published memory lives on the local branch `autoresearch-memory`. Session worktrees read from that branch when available, and `uv run memory.py publish ...` commits updated `memory/` state back to it without stashing or checking out `main`.

Use the helper commands below:

```bash
uv run memory.py init
uv run memory.py status
uv run memory.py record-run --help
uv run memory.py publish "publish np-YYYYMMDD-NNN: short title"
```

`init` is idempotent and safe to rerun.

## Current training setup

This repository currently implements:

- MLX-based training on Apple Silicon
- AdamW optimization
- a fixed 300-second training budget from `prepare.py`
- `val_bpb` as the primary metric
- peak unified-memory reporting via `peak_vram_mb`

This repository does not currently implement Muon in `train.py`, so older Muon-related notes from other forks do not apply here.

## Notes on the workflow

- The experiment loop is now split into two layers: `program.md` defines one agent session, and `loop.sh` provides the outer repetition.
- The memory substrate is intended to preserve findings across restarts instead of relying on one long context window.
- `results.tsv` remains useful for per-run tracking alongside higher-level nanopublications in `memory/`.

## Acknowledgments

- [Andrej Karpathy](https://github.com/karpathy) for autoresearch
- [scasella/nanochat-mlx](https://github.com/scasella/nanochat-mlx) for MLX GPT and optimizer references
- [awni/picochat](https://github.com/awni/picochat) for MLX training patterns
- [Apple MLX team](https://github.com/ml-explore/mlx)

## License

MIT. Original copyright preserved. See `LICENSE`.
