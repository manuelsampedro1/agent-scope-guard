import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from agent_scope_guard.cli import check_scope, main, paths_from_diff


SAMPLE_DIFF = """diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1,2 @@
+print("ok")
diff --git a/tests/test_app.py b/tests/test_app.py
index 3333333..4444444 100644
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1 +1,2 @@
+def test_ok(): pass
diff --git a/docs/roadmap.md b/docs/roadmap.md
index 5555555..6666666 100644
--- a/docs/roadmap.md
+++ b/docs/roadmap.md
@@ -1 +1,2 @@
+scope creep
"""


class ScopeGuardTests(unittest.TestCase):
    def test_paths_from_diff(self) -> None:
        self.assertEqual(paths_from_diff(SAMPLE_DIFF), ["docs/roadmap.md", "src/app.py", "tests/test_app.py"])

    def test_check_scope_fails_on_unexpected_paths(self) -> None:
        result = check_scope(paths_from_diff(SAMPLE_DIFF), ["src/**", "tests/**"])

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.unexpected_paths, ["docs/roadmap.md"])

    def test_cli_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diff_path = Path(tmp) / "sample.diff"
            diff_path.write_text(SAMPLE_DIFF, encoding="utf-8")
            stream = StringIO()

            with redirect_stdout(stream):
                exit_code = main([str(diff_path), "--allow", "src/**", "--allow", "tests/**", "--format", "json"])

            payload = json.loads(stream.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["unexpected_paths"], ["docs/roadmap.md"])

    def test_paths_only_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths_path = Path(tmp) / "paths.txt"
            paths_path.write_text("src/app.py\ntests/test_app.py\n", encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = main([str(paths_path), "--paths-only", "--allow", "src/**", "--allow", "tests/**"])

        self.assertEqual(exit_code, 0)

    def test_missing_allowlist_is_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diff_path = Path(tmp) / "sample.diff"
            diff_path.write_text(SAMPLE_DIFF, encoding="utf-8")

            with redirect_stderr(StringIO()):
                exit_code = main([str(diff_path)])

        self.assertEqual(exit_code, 2)

    def test_valid_proof_packet_does_not_override_unexpected_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diff_path = Path(tmp) / "sample.diff"
            proof_path = write_proof_packet(
                Path(tmp),
                changed_files=["docs/roadmap.md", "src/app.py", "tests/test_app.py"],
            )
            diff_path.write_text(SAMPLE_DIFF, encoding="utf-8")
            stream = StringIO()

            with redirect_stdout(stream):
                exit_code = main(
                    [
                        str(diff_path),
                        "--allow",
                        "src/**",
                        "--allow",
                        "tests/**",
                        "--proof-packet",
                        str(proof_path),
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stream.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["unexpected_paths"], ["docs/roadmap.md"])
        self.assertEqual(payload["proof_packets"][0]["status"], "pass")
        self.assertEqual(payload["proof_packet_evidence"][0]["matching_unexpected_paths"], ["docs/roadmap.md"])

    def test_incomplete_proof_packet_fails_even_when_scope_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths_path = Path(tmp) / "paths.txt"
            proof_path = write_proof_packet(
                Path(tmp),
                changed_files=["src/app.py", "tests/test_app.py"],
                verdict="incomplete",
            )
            paths_path.write_text("src/app.py\ntests/test_app.py\n", encoding="utf-8")
            stream = StringIO()

            with redirect_stdout(stream):
                exit_code = main(
                    [
                        str(paths_path),
                        "--paths-only",
                        "--allow",
                        "src/**",
                        "--allow",
                        "tests/**",
                        "--proof-packet",
                        str(proof_path),
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stream.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["proof_packets"][0]["status"], "fail")
        self.assertTrue(any(issue["code"] == "proof-packet-incomplete" for issue in payload["proof_packets"][0]["issues"]))

    def test_mismatched_proof_packet_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diff_path = Path(tmp) / "sample.diff"
            proof_path = write_proof_packet(Path(tmp), changed_files=["src/other.py"])
            diff_path.write_text(SAMPLE_DIFF, encoding="utf-8")
            stream = StringIO()

            with redirect_stdout(stream):
                exit_code = main(
                    [
                        str(diff_path),
                        "--allow",
                        "src/**",
                        "--allow",
                        "tests/**",
                        "--allow",
                        "docs/**",
                        "--proof-packet",
                        str(proof_path),
                        "--format",
                        "json",
                    ]
                )

            payload = json.loads(stream.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["proof_packets"][0]["status"], "fail")
        self.assertTrue(any(issue["code"] == "proof-packet-diff-mismatch" for issue in payload["proof_packets"][0]["issues"]))


def write_proof_packet(root: Path, *, changed_files: list[str], verdict: str = "complete") -> Path:
    payload = {
        "schema_version": "agent-proof-packet.v1",
        "title": "Scope guard evidence",
        "verdict": verdict,
        "changed_files": [{"path": path} for path in changed_files],
        "checks": [{"name": "make test", "status": "pass", "detail": "unit suite passed"}],
        "missing_evidence": [],
        "open_questions": [],
    }
    path = root / "proof-packet.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
