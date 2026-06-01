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


if __name__ == "__main__":
    unittest.main()

