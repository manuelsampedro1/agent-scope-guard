# Agent Scope Guard

Fail a coding-agent run when the diff touches files outside the declared task scope.

Agents can pass tests while quietly editing unrelated files. `agent-scope-guard` checks changed paths against an explicit allowlist so the task contract stays enforceable.

## What It Does

- Reads changed files from a unified diff, stdin, or newline-delimited path list.
- Accepts exact paths and glob patterns.
- Reports allowed and unexpected paths.
- Exits non-zero when any changed path is outside the declared scope.
- Emits text or JSON for CI and automation.
- Optionally verifies `agent-proof-packet.v1` evidence against the same changed
  paths before showing packet checks beside scope results.

## Install

```sh
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Or run without installing:

```sh
PYTHONPATH=src python3 -m agent_scope_guard examples/sample.diff --allow "src/**" --allow "tests/**"
```

## Usage

Check a saved diff:

```sh
agent-scope-guard examples/sample.diff \
  --allow "src/**" \
  --allow "tests/**"
```

Check current changes:

```sh
git diff -- . | agent-scope-guard - --allow "src/**" --allow "tests/**"
```

Check staged paths:

```sh
git diff --cached --name-only | agent-scope-guard - --paths-only --allow "src/**"
```

Use an allowlist file:

```sh
agent-scope-guard examples/sample.diff --allow-file examples/scope.txt
```

Attach proof-packet evidence:

```sh
agent-scope-guard examples/sample.diff \
  --allow-file examples/scope.txt \
  --proof-packet examples/proof-packet.json \
  --format json
```

The proof packet must be complete, include passing checks, have changed-file
evidence, have no missing evidence, and match the same diff or path list.
Packet checks do not authorize unexpected paths; scope violations still return
a non-zero exit.

`examples/scope.txt`:

```text
src/**
tests/**
README.md
```

## Example Output

```text
Agent Scope Guard: fail
Allowed: 2
Unexpected: 1

Unexpected paths:
- docs/roadmap.md
```

## Development

```sh
make test
make lint
make build
make smoke
```

## Fit With The Agent Workflow Stack

- `agent-task-contract`: declare the task before work starts.
- `agent-scope-guard`: enforce the expected changed paths.
- `agent-proof-packet`: show validated evidence for the same changed paths.
- `agent-secret-sentinel`: check for secret leakage.
- `verify-by-change`: match verification to the diff.
- `agent-rollback-plan`: prepare the undo path.
- `agent-run-ledger`: keep the run auditable.
