"""
Collective memory substrate for cross-session agent knowledge sharing.
Helper commands bootstrap the memory/ tree, summarize orientation, record
per-run provenance artifacts, and publish memory/ to a dedicated branch.

Usage:
    uv run memory.py init
    uv run memory.py status
    uv run memory.py record-run --help
    uv run memory.py publish "publish np-YYYYMMDD-NNN: short title"
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.resolve()
MEMORY_DIR = ROOT / "memory"
LAYER1 = MEMORY_DIR / "layer1"
SESSIONS = MEMORY_DIR / "sessions"
SESSION_LOGS = SESSIONS / "logs"
RUNS = SESSIONS / "runs"
DEFAULT_MEMORY_BRANCH = "autoresearch-memory"
RESULTS_HEADER = [
    "session_id",
    "run_id",
    "commit_sha",
    "base_commit",
    "val_bpb",
    "memory_gb",
    "status",
    "artifact_dir",
    "description",
]

NANOPUB_TEMPLATE = """\
---
id: np-YYYYMMDD-NNN
title: "Short descriptive title"
published: {timestamp}
agent: claude  # or codex, etc.
session: SESSION_ID
confidence: moderate  # low | moderate | high
status: active  # active | superseded | retracted
supersedes: null
evidence:
  supporting: 0
  contradicting: 0
  ambiguous: 0
  baseline_bpb: 0.0
---

## Assertion

State the core claim in 1-3 sentences.

## Evidence

| # | commit  | val_bpb | delta   | description          | verdict    |
|---|---------|---------|---------|----------------------|------------|
| 1 | abc1234 | 0.0000  | -0.0000 | what was changed     | supporting |

## Conditions

- 5-minute training budget
- Platform: (macOS M-series / NVIDIA GPU)
- Baseline val_bpb: X.XXXXXX

## Falsification

Describe what experiment could have disproved the hypothesis, and what happened.

## Implications

What follow-up work does this suggest?
"""

def git_run(*args, cwd=ROOT, capture_output=False, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        check=check,
        capture_output=capture_output,
    )


def git_output(*args, cwd=ROOT):
    return git_run(*args, cwd=cwd, capture_output=True).stdout.strip()


def git_ref_exists(ref):
    return git_run("show-ref", "--verify", "--quiet", ref, check=False).returncode == 0


def sanitize_tsv_field(value):
    return str(value).replace("\t", " ").replace("\n", " ").strip()


def relpath(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def parse_metrics_from_log(path):
    text = path.read_text()
    val_match = re.search(r"^val_bpb:\s+([0-9.]+)", text, re.MULTILINE)
    mem_match = re.search(r"^peak_vram_mb:\s+([0-9.]+)", text, re.MULTILINE)
    val_bpb = float(val_match.group(1)) if val_match else 0.0
    peak_vram_mb = float(mem_match.group(1)) if mem_match else 0.0
    return val_bpb, peak_vram_mb


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init():
    """Create memory/ directory tree and seed the nanopub template."""
    created = []

    for subdir in [LAYER1, SESSIONS, SESSION_LOGS, RUNS]:
        subdir.mkdir(parents=True, exist_ok=True)

    # .gitkeep for empty dirs
    for d in [LAYER1, SESSION_LOGS, RUNS]:
        gk = d / ".gitkeep"
        if not gk.exists():
            gk.touch()

    # Nanopub template
    tmpl = MEMORY_DIR / "template-nanopub.md"
    if not tmpl.exists():
        tmpl.write_text(NANOPUB_TEMPLATE.format(timestamp=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")))
        created.append("template-nanopub.md")

    if created:
        print(f"Initialized memory/ with {len(created)} new files:")
        for f in created[:10]:
            print(f"  {f}")
        if len(created) > 10:
            print(f"  ... and {len(created) - 10} more")
    else:
        print("memory/ already initialized, nothing to do.")


def parse_frontmatter(path):
    """Parse YAML frontmatter from a markdown file."""
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}


def cmd_status():
    """Print compact orientation summary of the memory substrate."""
    if not MEMORY_DIR.exists():
        print("memory/ not found. Run: uv run memory.py init")
        return

    # Scan nanopubs
    nanopubs = []
    for f in sorted(LAYER1.glob("*.md")):
        fm = parse_frontmatter(f)
        if not fm.get("id"):
            continue
        nanopubs.append(fm)

    status_counts = {}
    for np in nanopubs:
        s = np.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    # Scan sessions
    sessions = []
    for f in sorted(SESSIONS.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text()) or {}
            sessions.append(data)
        except yaml.YAMLError:
            continue

    session_status = {}
    for s in sessions:
        st = s.get("status", "unknown")
        session_status[st] = session_status.get(st, 0) + 1

    # Print summary
    print("=== Memory Status ===")
    np_summary = ", ".join(f"{k}: {v}" for k, v in status_counts.items()) if status_counts else "none yet"
    print(f"Nanopubs: {len(nanopubs)} ({np_summary})")

    sess_summary = ", ".join(f"{k}: {v}" for k, v in session_status.items()) if session_status else "none yet"
    print(f"Sessions: {len(sessions)} ({sess_summary})")

    # Active sessions
    active = [s for s in sessions if s.get("status") == "active"]
    if active:
        print(f"\nActive sessions:")
        for s in active:
            sid = s.get("session_id", "?")
            hyp = s.get("hypothesis", "?")
            agent = s.get("agent", "?")
            started = s.get("started", "?")
            print(f'  {sid}: "{hyp}" ({agent}, since {started})')

    # Recent nanopubs
    if nanopubs:
        recent = sorted(nanopubs, key=lambda x: x.get("published", ""), reverse=True)[:5]
        print(f"\nRecent nanopubs:")
        for np in recent:
            nid = np.get("id", "?")
            conf = np.get("confidence", "?")
            title = np.get("title", "?")
            print(f"  {nid}  {conf:9s}  {title}")


def cmd_record_run(args):
    """Create durable provenance artifacts for one experiment run."""
    if not MEMORY_DIR.exists():
        raise SystemExit("memory/ not found. Run: uv run memory.py init")

    run_log = Path(args.run_log)
    if not run_log.is_absolute():
        run_log = (ROOT / run_log).resolve()
    if not run_log.exists():
        raise SystemExit(f"Run log not found: {run_log}")

    results_path = Path(args.results_file)
    if not results_path.is_absolute():
        results_path = (ROOT / results_path).resolve()

    artifact_dir = RUNS / args.session_id / args.run_id
    if artifact_dir.exists():
        raise SystemExit(f"Run artifact directory already exists: {artifact_dir}")
    artifact_dir.mkdir(parents=True, exist_ok=False)

    commit_sha = git_output("rev-parse", "HEAD")
    val_bpb, peak_vram_mb = parse_metrics_from_log(run_log)
    memory_gb = peak_vram_mb / 1024 if peak_vram_mb else 0.0

    run_log_copy = artifact_dir / "run.log"
    shutil.copy2(run_log, run_log_copy)

    train_patch = git_output("diff", f"{args.base_commit}..HEAD", "--", "train.py")
    (artifact_dir / "train.patch").write_text(train_patch)
    shutil.copy2(ROOT / "train.py", artifact_dir / "train.py")

    metadata = {
        "session_id": args.session_id,
        "run_id": args.run_id,
        "recorded_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": args.status,
        "description": args.description,
        "commit_sha": commit_sha,
        "base_commit": args.base_commit,
        "val_bpb": val_bpb,
        "peak_vram_mb": peak_vram_mb,
        "memory_gb": round(memory_gb, 3),
        "artifact_dir": relpath(artifact_dir),
        "run_log": relpath(run_log_copy),
        "train_patch": relpath(artifact_dir / "train.patch"),
        "train_snapshot": relpath(artifact_dir / "train.py"),
        "source_run_log": str(run_log),
    }
    (artifact_dir / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")

    header = "\t".join(RESULTS_HEADER)
    if results_path.exists():
        lines = results_path.read_text().splitlines()
        if lines and lines[0] != header:
            raise SystemExit(
                "results.tsv header does not match the expected schema for record-run:\n"
                f"  expected: {header}\n"
                f"  actual:   {lines[0]}"
            )
    else:
        results_path.write_text(header + "\n")

    row = [
        args.session_id,
        args.run_id,
        commit_sha,
        args.base_commit,
        f"{val_bpb:.6f}",
        f"{memory_gb:.1f}",
        args.status,
        relpath(artifact_dir),
        sanitize_tsv_field(args.description),
    ]
    with results_path.open("a") as handle:
        handle.write("\t".join(row) + "\n")

    print(f"Recorded run {args.run_id} for session {args.session_id}")
    print(f"  commit:   {commit_sha}")
    print(f"  metrics:  val_bpb={val_bpb:.6f}, memory_gb={memory_gb:.1f}")
    print(f"  artifacts:{relpath(artifact_dir)}")


def cmd_publish(args):
    """Publish the current memory/ tree to the dedicated memory branch."""
    if not MEMORY_DIR.exists():
        raise SystemExit("memory/ not found. Run: uv run memory.py init")

    default_branch = args.default_branch
    memory_branch = args.memory_branch
    if not git_ref_exists(f"refs/heads/{default_branch}"):
        raise SystemExit(f"Default branch does not exist locally: {default_branch}")

    if not git_ref_exists(f"refs/heads/{memory_branch}"):
        git_run("branch", memory_branch, f"refs/heads/{default_branch}")

    publish_worktree = Path(tempfile.mkdtemp(prefix="autoresearch-memory-")).resolve()
    try:
        git_run("worktree", "add", "--detach", str(publish_worktree), f"refs/heads/{memory_branch}")

        target_memory = publish_worktree / "memory"
        if target_memory.exists():
            shutil.rmtree(target_memory)
        shutil.copytree(MEMORY_DIR, target_memory)

        status = git_output("status", "--porcelain", "--", "memory", cwd=publish_worktree)
        if not status:
            print(f"No memory changes to publish to {memory_branch}.")
            return

        git_run("add", "memory", cwd=publish_worktree)
        git_run("commit", "-m", args.message, cwd=publish_worktree)
        commit_sha = git_output("rev-parse", "HEAD", cwd=publish_worktree)
        git_run("branch", "-f", memory_branch, commit_sha, cwd=publish_worktree)

        print(f"Published memory/ to {memory_branch}")
        print(f"  commit: {commit_sha}")
    finally:
        git_run("worktree", "remove", "--force", str(publish_worktree), check=False)
        shutil.rmtree(publish_worktree, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autoresearch memory helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create memory/ directory tree")
    subparsers.add_parser("status", help="Print orientation summary")

    record_parser = subparsers.add_parser("record-run", help="Write durable run artifacts and append results.tsv")
    record_parser.add_argument("--session-id", required=True, help="Session identifier, e.g. mar10-codex-01")
    record_parser.add_argument("--run-id", required=True, help="Run identifier within the session, e.g. run-003")
    record_parser.add_argument("--base-commit", required=True, help="Full SHA of the best commit this run branched from")
    record_parser.add_argument(
        "--status",
        required=True,
        choices=["keep", "discard", "crash"],
        help="Outcome for this run",
    )
    record_parser.add_argument("--description", required=True, help="Short description of the experimental change")
    record_parser.add_argument("--run-log", required=True, help="Path to the train.py log for this run")
    record_parser.add_argument("--results-file", default="results.tsv", help="Path to results TSV (default: results.tsv)")

    publish_parser = subparsers.add_parser("publish", help="Publish memory/ to the memory branch")
    publish_parser.add_argument("message", help="Commit message for the memory publication")
    publish_parser.add_argument(
        "--default-branch",
        default=None,
        help="Default branch to seed the memory branch from (defaults to AUTORESEARCH_DEFAULT_BRANCH or current branch)",
    )
    publish_parser.add_argument(
        "--memory-branch",
        default=None,
        help=f"Memory branch name (default: AUTORESEARCH_MEMORY_BRANCH or {DEFAULT_MEMORY_BRANCH})",
    )

    args = parser.parse_args()

    if args.command == "init":
        cmd_init()
    elif args.command == "status":
        cmd_status()
    elif args.command == "record-run":
        cmd_record_run(args)
    elif args.command == "publish":
        if args.default_branch is None:
            args.default_branch = os.environ.get("AUTORESEARCH_DEFAULT_BRANCH")
        if args.default_branch is None:
            args.default_branch = git_output("branch", "--show-current")
        if not args.default_branch:
            raise SystemExit("Could not determine default branch; pass --default-branch explicitly.")
        if args.memory_branch is None:
            args.memory_branch = os.environ.get("AUTORESEARCH_MEMORY_BRANCH", DEFAULT_MEMORY_BRANCH)
        cmd_publish(args)
