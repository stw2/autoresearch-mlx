---
id: np-YYYYMMDD-NNN
title: "Short descriptive title"
published: 2026-03-10T07:55:32Z
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
