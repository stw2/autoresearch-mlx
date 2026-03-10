#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
repo_root="$PWD"

agent="${1:-claude}"
iterations="${2:-0}"

case "$agent" in
  claude|codex) ;;
  *)
    echo "usage: ./loop.sh [claude|codex] [iterations]" >&2
    exit 1
    ;;
esac

if ! command -v "$agent" >/dev/null 2>&1; then
  echo "error: '$agent' is not installed or not on PATH" >&2
  exit 1
fi

if ! [[ "$iterations" =~ ^[0-9]+$ ]]; then
  echo "error: iterations must be a non-negative integer" >&2
  exit 1
fi

if [[ ! -d .git ]]; then
  echo "error: loop.sh must be run from the repo root" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: source checkout has local changes; commit or stash them before running loop.sh" >&2
  exit 1
fi

if [[ ! -e memory ]]; then
  echo "error: memory/ is missing; run 'uv run memory.py init' first" >&2
  exit 1
fi

git_dir="$(cd "$(git rev-parse --git-dir)" && pwd)"
session_logs_dir="$git_dir/autoresearch/session-logs"
memory_branch="${AUTORESEARCH_MEMORY_BRANCH:-autoresearch-memory}"
current_worktree=""

cleanup_current_worktree() {
  if [[ -n "$current_worktree" && -d "$current_worktree" ]]; then
    git -C "$repo_root" worktree remove --force "$current_worktree" >/dev/null 2>&1 || rm -rf "$current_worktree"
    current_worktree=""
  fi
}

trap cleanup_current_worktree EXIT INT TERM

if git check-ignore -q --no-index memory/; then
  echo "error: memory/ is gitignored; fix .gitignore before running the loop" >&2
  exit 1
fi

default_branch="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@')"
if [[ -z "$default_branch" ]]; then
  default_branch="$(git branch --show-current)"
fi

if [[ -z "$default_branch" ]]; then
  echo "error: could not determine the default branch" >&2
  exit 1
fi

if ! git show-ref --verify --quiet "refs/heads/$default_branch"; then
  echo "error: default branch '$default_branch' does not exist locally" >&2
  exit 1
fi

prompt="$(
  awk '
    /^## Running the agent$/ { in_section=1; next }
    in_section && /^```$/ && !in_block { in_block=1; next }
    in_block && /^```$/ { exit }
    in_block { print }
  ' README.md
)"

if [[ -z "$prompt" ]]; then
  echo "error: could not extract default prompt from README.md" >&2
  exit 1
fi

i=1
while :; do
  mkdir -p "$session_logs_dir"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  session_log="$session_logs_dir/${timestamp}-${agent}-iter$(printf '%03d' "$i").log"
  current_worktree="$(mktemp -d "${TMPDIR:-/tmp}/autoresearch-${timestamp}-${agent}-iter$(printf '%03d' "$i").XXXXXX")"
  git -C "$repo_root" worktree add --detach "$current_worktree" "refs/heads/$default_branch" >/dev/null
  if git show-ref --verify --quiet "refs/heads/$memory_branch"; then
    git -C "$current_worktree" checkout "refs/heads/$memory_branch" -- memory >/dev/null 2>&1 || true
  fi

  prompt_with_context="$(cat <<EOF
Autoresearch launcher context:
- source repo: $repo_root
- default branch: $default_branch
- memory branch: $memory_branch
- isolated session worktree: $current_worktree
- session log path: $session_log
- the source checkout must stay clean; do all experiment work inside the isolated worktree
- publish memory with: uv run memory.py publish "publish <nanopub-id>: <short title>"

$prompt
EOF
)"

  echo "=== Iteration $i ($agent) ==="
  echo "default branch: $default_branch"
  echo "memory branch: $memory_branch"
  echo "session worktree: $current_worktree"
  echo "session log: $session_log"

  if [[ "$agent" == "claude" ]]; then
    (
      cd "$current_worktree"
      AUTORESEARCH_SESSION_LOG="$session_log" \
      AUTORESEARCH_DEFAULT_BRANCH="$default_branch" \
      AUTORESEARCH_MEMORY_BRANCH="$memory_branch" \
      AUTORESEARCH_SOURCE_REPO="$repo_root" \
      claude \
        --print \
        --no-session-persistence \
        --dangerously-skip-permissions \
        --permission-mode bypassPermissions \
        "$prompt_with_context"
    ) 2>&1 | tee "$session_log"
  else
    (
      cd "$current_worktree"
      AUTORESEARCH_SESSION_LOG="$session_log" \
      AUTORESEARCH_DEFAULT_BRANCH="$default_branch" \
      AUTORESEARCH_MEMORY_BRANCH="$memory_branch" \
      AUTORESEARCH_SOURCE_REPO="$repo_root" \
      codex exec --yolo -C "$current_worktree" "$prompt_with_context"
    ) 2>&1 | tee "$session_log"
  fi

  cleanup_current_worktree

  if [[ "$iterations" -gt 0 && "$i" -ge "$iterations" ]]; then
    break
  fi

  i=$((i + 1))
done
