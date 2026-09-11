"""Full-image CLI behavior with discovery and Docker isolated from the network."""

# Test method names describe their behavior.
# pylint: disable=missing-function-docstring

from pathlib import Path
import shlex
import subprocess
import unittest
from unittest.mock import Mock, patch

from click.testing import CliRunner

from dcdocker import cli, defaults, docker, sources

import build_dc_kos_full_image as full_image


class FullImageBuildTests(unittest.TestCase):
    """Drive real menus and inspect the resulting Docker arguments."""

    def setUp(self):
        self.enterContext(patch.object(cli, "is_interactive", return_value=True))
        self.contexts = []
        original_copy = sources.copy_resources

        def copy_context(source, destination):
            self.contexts.append(destination)
            original_copy(source, destination)

        self.enterContext(patch.object(sources, "copy_resources", side_effect=copy_context))
        self.addCleanup(self.assert_contexts_removed)
        self.docker = self.enterContext(
            patch.object(docker.subprocess, "run", side_effect=self.check_context)
        )
        self.http = self.enterContext(patch.object(sources.requests, "get"))
        self.http.return_value = Mock(
            status_code=200, json=Mock(return_value=[{"name": "master"}])
        )

    def assert_contexts_removed(self):
        """Every CLI exit, including cancellation and discovery failure, releases its context."""
        for context in self.contexts:
            self.assertFalse(context.exists(), f"Leaked build context: {context}")

    def check_context(self, command, **_kwargs):
        """Assert Docker can read every required file while the context is alive."""
        context = Path(command[-1])
        for name in defaults.READY_CONTEXT_FILES:
            self.assertTrue((context / name).is_file())

    @staticmethod
    def invoke(args=(), answers="3\n3\n1\n1\n"):
        """Default menu answers choose master for all sources and confirm."""
        return CliRunner().invoke(full_image.main, ["-u", "test", *args], input=answers)

    def test_default_and_gdb_builds(self):
        for gdb in (False, True):
            with self.subTest(gdb=gdb):
                self.docker.reset_mock()
                result = self.invoke(["--gdb"] if gdb else [])
                self.assertEqual(result.exit_code, 0, result.output)
                self.docker.assert_called_once()
                command = self.docker.call_args.args[0]
                self.assertEqual(command[:2], ["docker", "build"])
                base = "dc-chain-gdb" if gdb else "dc-chain"
                tag = "16.2.0-gdb-latest" if gdb else "16.2.0-latest"
                self.assertIn(f"base_image=maishuji/{base}:16.2.0", command)
                self.assertNotIn("dc_chain_version=16.2.0", command)
                for source in ("kos", "kosports", "gldc"):
                    self.assertIn(f"snapshot_{source}=master", command)
                self.assertEqual(command[command.index("-t") + 1], f"test/dc-kos-image:{tag}")

    def test_snapshot_names_and_arguments(self):
        self.http.side_effect = [
            Mock(status_code=200, json=Mock(return_value=[{"ref": "refs/tags/01MAR25"}])),
            Mock(status_code=200, json=Mock(return_value=[{"ref": "refs/tags/02MAR25"}])),
            Mock(status_code=200, json=Mock(return_value=[{"name": "release/03MAR25"}])),
        ]
        result = self.invoke(["-p", "custom"], "2\n1\n2\n1\n1\n1\n")
        self.assertEqual(result.exit_code, 0, result.output)
        command = self.docker.call_args.args[0]
        self.assertIn("test/dc-kos-image:custom-01mar25-kp02mar25-gl03mar25", command)
        self.assertIn("snapshot_kos=01MAR25", command)
        self.assertIn("snapshot_kosports=02MAR25", command)
        self.assertIn("snapshot_gldc=release/03MAR25", command)

    def test_explicit_kos_ports_skips_its_menu_and_discovery(self):
        result = self.invoke(["--kos-ports-branch", "feature/My-Branch"], "3\n1\n1\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.http.assert_called_once()
        self.assertIn("gitlab.com", self.http.call_args.args[0])
        command = self.docker.call_args.args[0]
        self.assertIn("snapshot_kosports=feature/My-Branch", command)
        self.assertIn("test/dc-kos-image:16.2.0-latest-kpfeature-my-branch-rc3f799196d8d", command)
        self.assertNotIn("year for the snapshot for kos-ports", result.output)

    def test_declining_confirmation_does_not_build(self):
        result = self.invoke(answers="3\n3\n1\n2\n")
        self.assertEqual(result.exit_code, 1)
        self.assertIn("cancelled", result.output)
        self.docker.assert_not_called()

    def test_docker_failure_is_reported(self):
        self.docker.side_effect = subprocess.CalledProcessError(17, ["docker", "build"])
        result = self.invoke()
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Docker build failed (exit code 17)", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_help_needs_no_discovery_or_docker(self):
        result = self.invoke(["--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--kos-ports-branch", result.output)
        self.http.assert_not_called()
        self.docker.assert_not_called()

    def test_discovery_failures_stop_before_docker(self):
        failures = [
            (sources.requests.ConnectionError("offline"), "connection"),
            (sources.requests.Timeout("slow service"), "timed out"),
            (Mock(status_code=404), "HTTP 404"),
            (Mock(status_code=500), "HTTP 500"),
            (Mock(status_code=403), "rate limit"),
            (Mock(status_code=429), "rate limit"),
            (Mock(status_code=200, json=Mock(side_effect=ValueError("bad JSON"))), "JSON"),
        ]
        # Each sequence reaches one of the three discovery providers first.
        for answers, source in (("1\n", "KallistiOS"),
                                ("3\n1\n", "kos-ports"), ("3\n3\n", "GLdc")):
            for response, message in failures:
                with self.subTest(source=source, message=message):
                    self.http.side_effect = [response]
                    result = self.invoke(answers=answers)
                    self.assertEqual(result.exit_code, 1, result.output)
                    self.assertIn(source, result.output)
                    self.assertIn(message, result.output)
                    self.assertIn("Error:", result.output)
                    self.assertNotIn("Traceback", result.output)
                    self.docker.assert_not_called()
                    self.assertEqual(self.http.call_args.kwargs["timeout"],
                                     defaults.REQUEST_TIMEOUT)

    def test_malformed_discovery_shapes_are_reported(self):
        for answers in ("1\n", "3\n1\n", "3\n3\n"):
            for payload in (None, {}, "invalid", [None], [{}],
                            [{"ref": 12, "name": 12}], [{"ref": "", "name": ""}]):
                with self.subTest(answers=answers, payload=payload):
                    self.http.return_value.json.return_value = payload
                    result = self.invoke(answers=answers)
                    self.assertEqual(result.exit_code, 1, result.output)
                    self.assertIn("Unexpected response", result.output)
                    self.assertNotIn("Traceback", result.output)
                    self.docker.assert_not_called()

    def test_empty_or_nonmatching_choices_fail_without_empty_menu(self):
        cases = [
            ("1\n", []),
            ("1\n", [{"ref": "refs/tags/01MAR24"}]),
            ("3\n1\n", []),
            ("3\n3\n", []),
            ("3\n3\n", [{"name": "feature/unrelated"}]),
        ]
        for answers, payload in cases:
            with self.subTest(answers=answers, payload=payload):
                self.http.return_value.json.return_value = payload
                result = self.invoke(answers=answers)
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn("No matching", result.output)
                self.assertNotIn("1-0", result.output)
                self.docker.assert_not_called()

    def test_invalid_menu_answers_retry(self):
        result = self.invoke(answers="bad\n0\n4\n3\n3\n1\n1\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Invalid input", result.output)
        self.assertIn("Invalid selection", result.output)
        self.docker.assert_called_once()

    def test_eof_and_keyboard_interrupt_abort_each_prompt(self):
        for completed in ([], ["3"], ["3", "3"], ["3", "3", "1"]):
            for error in (EOFError, KeyboardInterrupt):
                with self.subTest(completed=completed, error=error):
                    with patch("builtins.input", side_effect=[*completed, error()]):
                        result = self.invoke()
                    self.assertEqual(result.exit_code, 1, result.output)
                    self.assertIn("Aborted", result.output)
                    self.assertNotIn("Traceback", result.output)
                    self.docker.assert_not_called()

    def test_missing_docker_is_actionable(self):
        self.docker.side_effect = FileNotFoundError("docker")
        result = self.invoke()
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Docker is required", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_build_interruption_cleans_context_and_preserves_assets(self):
        self.docker.side_effect = KeyboardInterrupt()
        result = self.invoke()
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Aborted", result.output)
        context = Path(self.docker.call_args.args[0][-1])
        self.assertFalse(context.exists())
        assets = Path(sources.__file__).parent / "assets/kos-ready"
        self.assertTrue((assets / "Dockerfile").is_file())
        self.assertTrue((assets / "apk-retry.sh").is_file())

    def test_context_is_independent_of_working_directory(self):
        with CliRunner().isolated_filesystem():
            # A misleading caller context must never be selected.
            Path("kos-ready").mkdir()
            caller = Path.cwd()
            result = self.invoke()
            self.assertEqual(result.exit_code, 0, result.output)
            context = Path(self.docker.call_args.args[0][-1])
            self.assertNotEqual(context, caller / "kos-ready")
            self.assertFalse(context.exists())
            self.assertEqual(Path.cwd(), caller)

    def test_missing_context_files_fail_before_docker(self):
        for missing in ("Dockerfile", "apk-retry.sh"):
            with self.subTest(missing=missing), CliRunner().isolated_filesystem():
                root = Path.cwd()
                context = root / "assets/kos-ready"
                context.mkdir(parents=True)
                for name in ("Dockerfile", "apk-retry.sh"):
                    if name != missing:
                        (context / name).write_text("fixture", encoding="utf-8")
                with patch.object(sources.resources, "files", return_value=root):
                    result = self.invoke()
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn(missing, result.output)
                self.docker.assert_not_called()

    def test_context_with_spaces_has_copyable_display(self):
        with CliRunner().isolated_filesystem():
            root = Path.cwd() / "repo with spaces"
            context = root / "assets/kos-ready"
            context.mkdir(parents=True)
            for name in ("Dockerfile", "apk-retry.sh"):
                (context / name).write_text("fixture", encoding="utf-8")
            with patch.object(sources.resources, "files", return_value=root):
                result = self.invoke()
            self.assertEqual(result.exit_code, 0, result.output)
            command = self.docker.call_args.args[0]
            self.assertFalse(Path(command[-1]).exists())
            self.assertTrue(context.exists())
            self.assertIn(shlex.join(command), result.output)


if __name__ == "__main__":
    unittest.main()
