from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional


PASS_CHECK_STATUSES = {"pass", "passed", "success", "ok"}
FAIL_CHECK_STATUSES = {"fail", "failed", "failure", "error", "blocked"}


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


def proof_issue(severity: str, code: str, message: str, evidence: str) -> dict[str, str]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "evidence": evidence[:220],
    }


def proof_packet_failure(path: str, code: str, message: str, evidence: str) -> dict[str, object]:
    return {
        "path": path,
        "status": "fail",
        "verdict": "",
        "changed_files": [],
        "passing_checks": [],
        "issues": [proof_issue("high", code, message, evidence)],
    }


def audit_proof_packet(path: str, diff_paths: Iterable[str]) -> dict[str, object]:
    issues: list[dict[str, str]] = []
    packet_files: list[str] = []
    passing_checks: list[str] = []
    check_statuses: list[str] = []

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        return proof_packet_failure(path, "proof-packet-unreadable", f"Proof packet could not be read: {exc}", path)
    except json.JSONDecodeError as exc:
        return proof_packet_failure(path, "proof-packet-invalid-json", f"Proof packet is not valid JSON: {exc}", path)

    if not isinstance(payload, dict):
        return proof_packet_failure(path, "proof-packet-invalid-shape", "Proof packet must be a JSON object.", path)

    if payload.get("schema_version") != "agent-proof-packet.v1":
        issues.append(proof_issue("high", "proof-packet-wrong-schema", "Proof packet schema_version is not agent-proof-packet.v1.", path))

    verdict = str(payload.get("verdict", "")).strip()
    if verdict != "complete":
        issues.append(proof_issue("high", "proof-packet-incomplete", f"Proof packet verdict is {verdict or 'missing'}, not complete.", path))

    raw_changed_files = payload.get("changed_files")
    if not isinstance(raw_changed_files, list) or not raw_changed_files:
        issues.append(proof_issue("high", "proof-packet-missing-changed-files", "Proof packet has no changed-file evidence.", path))
    else:
        for item in raw_changed_files:
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].strip():
                packet_files.append(clean_path(item["path"]))
            else:
                issues.append(proof_issue("high", "proof-packet-invalid-changed-file", "Proof packet contains an invalid changed_files entry.", path))

    raw_checks = payload.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        issues.append(proof_issue("high", "proof-packet-missing-checks", "Proof packet has no checks.", path))
    else:
        for item in raw_checks:
            if not isinstance(item, dict):
                issues.append(proof_issue("high", "proof-packet-invalid-check", "Proof packet contains an invalid check entry.", path))
                continue
            name = str(item.get("name", "")).strip()
            status = str(item.get("status", "")).strip().lower()
            detail = str(item.get("detail", "")).strip()
            if not name or not status:
                issues.append(proof_issue("high", "proof-packet-invalid-check", "Proof packet contains a nameless or statusless check.", path))
                continue
            check_statuses.append(status)
            if status in PASS_CHECK_STATUSES:
                passing_checks.append(name + (f" - {detail}" if detail else ""))
            elif status not in FAIL_CHECK_STATUSES:
                issues.append(proof_issue("medium", "proof-packet-unknown-check-status", f"Proof packet check `{name}` uses an unrecognized status.", status))

    if any(status in FAIL_CHECK_STATUSES for status in check_statuses):
        issues.append(proof_issue("high", "proof-packet-failing-checks", "Proof packet includes failing checks.", path))
    if not any(status in PASS_CHECK_STATUSES for status in check_statuses):
        issues.append(proof_issue("high", "proof-packet-no-passing-checks", "Proof packet has no passing checks.", path))

    missing_evidence = payload.get("missing_evidence")
    if isinstance(missing_evidence, list) and missing_evidence:
        issues.append(
            proof_issue(
                "high",
                "proof-packet-missing-evidence",
                "Proof packet still has missing evidence.",
                ", ".join(str(item) for item in missing_evidence[:5]),
            )
        )
    elif missing_evidence is not None and not isinstance(missing_evidence, list):
        issues.append(proof_issue("high", "proof-packet-invalid-missing-evidence", "Proof packet missing_evidence must be a list when present.", path))

    open_questions = payload.get("open_questions")
    if isinstance(open_questions, list) and open_questions:
        issues.append(
            proof_issue(
                "medium",
                "proof-packet-open-questions",
                "Proof packet still has open questions.",
                ", ".join(str(item) for item in open_questions[:5]),
            )
        )
    elif open_questions is not None and not isinstance(open_questions, list):
        issues.append(proof_issue("medium", "proof-packet-invalid-open-questions", "Proof packet open_questions should be a list when present.", path))

    diff_file_set = {clean_path(diff_path) for diff_path in diff_paths}
    packet_file_set = set(packet_files)
    if diff_file_set and packet_file_set and diff_file_set != packet_file_set:
        issues.append(
            proof_issue(
                "high",
                "proof-packet-diff-mismatch",
                "Proof packet changed files do not match the provided diff or path list.",
                f"diff={sorted(diff_file_set)} packet={sorted(packet_file_set)}",
            )
        )

    status = "fail" if any(issue["severity"] == "high" for issue in issues) else "pass"
    return {
        "path": path,
        "status": status,
        "verdict": verdict,
        "changed_files": packet_files,
        "passing_checks": passing_checks,
        "issues": issues,
    }


def build_report(result: ScopeResult, proof_packets: Iterable[dict[str, object]]) -> dict[str, object]:
    report = asdict(result)
    packet_list = list(proof_packets)
    if not packet_list:
        return report

    allowed_set = set(result.allowed_paths)
    unexpected_set = set(result.unexpected_paths)
    report["proof_packets"] = packet_list
    report["proof_packet_evidence"] = []
    for packet in packet_list:
        if packet.get("status") != "pass":
            continue
        packet_files = {str(path) for path in packet.get("changed_files", [])}
        report["proof_packet_evidence"].append(
            {
                "path": str(packet.get("path", "")),
                "matching_allowed_paths": sorted(allowed_set.intersection(packet_files)),
                "matching_unexpected_paths": sorted(unexpected_set.intersection(packet_files)),
                "passing_checks": [str(check) for check in packet.get("passing_checks", [])],
            }
        )
    return report


def render_text(result: ScopeResult, report: Optional[dict[str, object]] = None) -> str:
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
    if report and report.get("proof_packets"):
        lines.extend(["", "Proof packets:"])
        for packet in report["proof_packets"]:
            checks = ", ".join(packet["passing_checks"]) if packet["passing_checks"] else "none"
            lines.append(f"- {packet['path']} status: {packet['status']}; verdict: {packet['verdict'] or 'unknown'}; passing checks: {checks}")
            for issue in packet["issues"]:
                lines.append(f"  - [{issue['severity']}] {issue['code']}: {issue['message']} Evidence: {issue['evidence']}")
        for evidence in report.get("proof_packet_evidence", []):
            allowed = ", ".join(evidence["matching_allowed_paths"]) or "none"
            unexpected = ", ".join(evidence["matching_unexpected_paths"]) or "none"
            checks = ", ".join(evidence["passing_checks"]) if evidence["passing_checks"] else "none"
            lines.append(f"- Evidence from {evidence['path']}: allowed={allowed}; unexpected={unexpected}; checks={checks}")
        lines.append("Proof-packet checks do not authorize unexpected paths.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-scope-guard")
    parser.add_argument("input", help="Unified diff, path list, or '-' for stdin.")
    parser.add_argument("--allow", action="append", default=[], help="Allowed path or glob. Can be repeated.")
    parser.add_argument("--allow-file", help="File containing allowed paths/globs, one per line.")
    parser.add_argument("--paths-only", action="store_true", help="Treat input as newline-delimited paths instead of unified diff.")
    parser.add_argument("--proof-packet", action="append", default=[], help="Optional agent-proof-packet.v1 JSON evidence to verify against the same changed paths.")
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
    proof_packets = [audit_proof_packet(path, paths) for path in args.proof_packet]
    report = build_report(result, proof_packets)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_text(result, report))
    return 1 if result.status == "fail" or any(packet.get("status") == "fail" for packet in proof_packets) else 0
