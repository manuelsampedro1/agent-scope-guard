# AGENTS.md

## Goal

Keep `agent-scope-guard` a small, dependency-free CLI that fails coding-agent diffs when changed paths fall outside the declared task scope.

## Constraints

- Prefer Python standard library only.
- Treat scope as explicit path and glob allowlists; do not infer intent from filenames.
- Keep text and JSON output stable unless tests and README examples are updated together.
- Do not add real private paths, secrets, tokens, or customer repo names to fixtures.
- Keep generated build metadata out of the repository.

## Verification

Run before closing changes:

```sh
make test
make lint
make build
make smoke
git diff --check
```

## Commit Expectations

- Commit parser or scope-matching changes with tests.
- Keep fixtures small, fake, and reviewable.
- Do not publish dirty trees, generated output, or local cache files.
