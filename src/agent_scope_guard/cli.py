from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScopeResult:
    status: str
    allowed_paths: list[str]
    unexpected_paths: list[str]
    allow_patterns: list[str]


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def clean_path(path: str) -> str:
    path = path.strip()
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def paths_from_diff(diff_text: str) -> list[str]:
    paths: list[str] = []
    for line in diff_text.splitlines():
        if not line.startswith("diff --git "):
            continue
        match = re.match(r"diff --git\s+(.+?)\s+(.+)$", line)
        if match:
            paths.append(clean_path(match.group(2)))
    return sorted(set(paths))


def paths_from_list(text: str) -> list[str]:
    return sorted(set(clean_path(line) for line in text.splitlines() if line.strip()))


def read_allow_patterns(patterns: list[str], allow_file: str | None) -> list[str]:
    result = [pattern.strip() for pattern in patterns if pattern.strip()]
    if allow_file:
        for line in Path(allow_file).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                result.append(stripped)
    return result


def is_allowed(path: str, patterns: list[str]) -> bool:
    return any(path == pattern or fnmatch.fnmatch(path, pattern) for pattern in patterns)


def check_scope(paths: list[str], patterns: list[str]) -> ScopeResult:
    allowed = [path for path in paths if is_allowed(path, patterns)]
    unexpected = [path for path in paths if not is_allowed(path, patterns)]
    return ScopeResult(
        status="fail" if unexpected else "pass",
        allowed_paths=allowed,
        unexpected_paths=unexpected,
        allow_patterns=patterns,
    )


def render_text(result: ScopeResult) -> str:
    lines = [
        f"Agent Scope Guard: {result.status}",
        f"Allowed: {len(result.allowed_paths)}",
        f"Unexpected: {len(result.unexpected_paths)}",
        "",
    ]
    if result.unexpected_paths:
        lines.append("Unexpected paths:")
        lines.extend(f"- {path}" for path in result.unexpected_paths)
    else:
        lines.append("All changed paths are within declared scope.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-scope-guard")
    parser.add_argument("input", help="Unified diff, path list, or '-' for stdin.")
    parser.add_argument("--allow", action="append", default=[], help="Allowed path or glob. Can be repeated.")
    parser.add_argument("--allow-file", help="File containing allowed paths/globs, one per line.")
    parser.add_argument("--paths-only", action="store_true", help="Treat input as newline-delimited paths instead of unified diff.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    patterns = read_allow_patterns(args.allow, args.allow_file)
    if not patterns:
        print("At least one --allow or --allow-file entry is required.", file=sys.stderr)
        return 2

    input_text = read_input(args.input)
    paths = paths_from_list(input_text) if args.paths_only else paths_from_diff(input_text)
    if not paths:
        print("No changed paths found.", file=sys.stderr)
        return 2

    result = check_scope(paths, patterns)
    if args.format == "json":
        print(json.dumps(asdict(result), indent=2))
    else:
        print(render_text(result))
    return 1 if result.status == "fail" else 0

