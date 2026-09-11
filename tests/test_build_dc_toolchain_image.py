"""Regression checks for source selection, GDB support, and build failures."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from click.testing import CliRunner

import build_dc_toolchain_image as toolchain


class ToolchainBuildTests(unittest.TestCase):
    """Exercise the CLI with real temporary sources and mocked Git/Docker calls."""

    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.local_path = Path(self.workspace.name) / "local kos"
        self.write_checkout(self.local_path)

    @staticmethod
    def write_checkout(path, dockerfile="ARG include_gdb=0\n"):
        dockerfile_path = path / "utils/kos-chain/docker/Dockerfile"
        dockerfile_path.parent.mkdir(parents=True, exist_ok=True)
        dockerfile_path.write_text(dockerfile, encoding="utf-8")

    def run_build(self, use_gdb=False, kos_path=None, docker_code=0, clone_code=0):
        """Create fresh sources when Git is invoked and simulate process failures."""
        def process_run(command, **kwargs):
            code = clone_code if command[0] == "git" else docker_code
            if kwargs.get("check") and code:
                raise subprocess.CalledProcessError(code, command)
            if command[0] == "git" and code == 0:
                self.write_checkout(Path(command[-1]))
            if command[0] == "docker":
                self.assertTrue(Path(command[-1]).is_dir())
                self.assertTrue(Path(command[command.index("-f") + 1]).is_file())
            return subprocess.CompletedProcess(command, code)

        args = ["-u", "test", "-p", "16.2.0"]
        if use_gdb:
            args.append("--use-gdb")
        if kos_path is not None:
            args.extend(["--kos-path", str(kos_path)])
        with patch.object(toolchain.subprocess, "run", side_effect=process_run) as processes:
            result = CliRunner().invoke(toolchain.main, args)
        return result, processes

    def assert_build_command(self, command, source, use_gdb):
        repository = "dc-chain-gdb" if use_gdb else "dc-chain"
        self.assertEqual(command[0:2], ["docker", "build"])
        self.assertEqual(command[command.index("-t") + 1], f"test/{repository}:16.2.0")
        self.assertEqual(
            Path(command[command.index("-f") + 1]),
            source / "utils/kos-chain/docker/Dockerfile",
        )
        self.assertIn(f"include_gdb={int(use_gdb)}", command)
        self.assertIn("profile=16.2.0", command)
        self.assertEqual(Path(command[-1]), source)

    def test_default_clones_fresh_sources_and_cleans_up(self):
        for use_gdb in (False, True):
            with self.subTest(use_gdb=use_gdb):
                result, processes = self.run_build(use_gdb=use_gdb)
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(processes.call_count, 2)
                clone, build = [call.args[0] for call in processes.call_args_list]
                self.assertEqual(
                    clone[:-1], ["git", "clone", "--depth", "1", toolchain.KOS_REPOSITORY]
                )
                source = Path(clone[-1])
                self.assert_build_command(build, source, use_gdb)
                self.assertFalse(source.parent.exists())
                self.assertIn("Using fresh KallistiOS sources", result.output)

    def test_local_sources_are_used_without_clone_or_modification(self):
        original_cwd = Path.cwd()
        marker = self.local_path / "local-changes.txt"
        marker.write_text("keep my changes", encoding="utf-8")
        for use_gdb in (False, True):
            with self.subTest(use_gdb=use_gdb):
                result, processes = self.run_build(use_gdb=use_gdb, kos_path=self.local_path)
                self.assertEqual(result.exit_code, 0, result.output)
                processes.assert_called_once()
                self.assert_build_command(processes.call_args.args[0], self.local_path, use_gdb)
                self.assertIn("no updates fetched", result.output)
                self.assertEqual(marker.read_text(encoding="utf-8"), "keep my changes")
                self.assertEqual(Path.cwd(), original_cwd)

    def test_build_failure_is_reported_and_temporary_sources_are_removed(self):
        for use_gdb in (False, True):
            with self.subTest(use_gdb=use_gdb):
                result, processes = self.run_build(use_gdb=use_gdb, docker_code=17)
                self.assertEqual(result.exit_code, 1)
                self.assertEqual(processes.call_count, 2)
                source = Path(processes.call_args.args[0][-1])
                self.assertFalse(source.parent.exists())
                self.assertIn("Toolchain Docker build failed (exit code 17)", result.output)
                self.assertNotIn("Successfully built", result.output)
                self.assertNotIn("Traceback", result.output)

    def test_failed_local_build_preserves_sources(self):
        result, processes = self.run_build(kos_path=self.local_path, docker_code=17)
        self.assertEqual(result.exit_code, 1)
        processes.assert_called_once()
        self.assertTrue((self.local_path / "utils/kos-chain/docker/Dockerfile").is_file())

    def test_clone_failure_prevents_build_and_cleans_up(self):
        result, processes = self.run_build(clone_code=128)
        self.assertEqual(result.exit_code, 1)
        processes.assert_called_once()
        self.assertIn("KallistiOS clone failed (exit code 128)", result.output)
        self.assertFalse(Path(processes.call_args.args[0][-1]).parent.exists())

    def test_gdb_requires_updated_local_checkout(self):
        self.write_checkout(self.local_path, dockerfile="ARG profile=stable\n")
        result, processes = self.run_build(use_gdb=True, kos_path=self.local_path)
        self.assertEqual(result.exit_code, 1)
        processes.assert_not_called()
        self.assertIn(f"Update your checkout at {self.local_path}", result.output)

    def test_old_local_checkout_can_still_build_without_gdb(self):
        self.write_checkout(self.local_path, dockerfile="ARG profile=stable\n")
        result, processes = self.run_build(kos_path=self.local_path)
        self.assertEqual(result.exit_code, 0)
        processes.assert_called_once()

    def test_invalid_local_sources_fail_before_build(self):
        for source in (Path(self.workspace.name), self.local_path / "missing"):
            with self.subTest(source=source):
                result, processes = self.run_build(kos_path=source)
                self.assertNotEqual(result.exit_code, 0)
                processes.assert_not_called()
                self.assertNotIn("Traceback", result.output)

    def test_help_explains_source_selection(self):
        result = CliRunner().invoke(toolchain.main, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("fresh upstream checkout by default", result.output)
        self.assertIn("--kos-path", result.output)

    def test_missing_tools_and_interruption_preserve_source_ownership(self):
        marker = self.local_path / "local-changes.txt"
        marker.write_text("keep my changes", encoding="utf-8")
        for local, stage in ((False, "git"), (False, "docker"), (True, "docker")):
            for error in (FileNotFoundError, KeyboardInterrupt):
                with self.subTest(local=local, stage=stage, error=error):
                    owned_sources = []

                    def process_run(command, **_kwargs):
                        if command[0] == "git":
                            source = Path(command[-1])
                            owned_sources.append(source)
                            self.write_checkout(source)
                        if command[0] == stage:
                            raise error()
                        return subprocess.CompletedProcess(command, 0)

                    args = ["-u", "test"]
                    if local:
                        args.extend(["--kos-path", str(self.local_path)])
                    with patch.object(toolchain.subprocess, "run", side_effect=process_run):
                        result = CliRunner().invoke(toolchain.main, args)
                    self.assertEqual(result.exit_code, 1, result.output)
                    expected = "Aborted" if error is KeyboardInterrupt else f"{stage.title()} is required"
                    self.assertIn(expected, result.output)
                    self.assertNotIn("Traceback", result.output)
                    self.assertNotIn("Successfully built", result.output)
                    for source in owned_sources:
                        self.assertFalse(source.parent.exists())
                    self.assertEqual(marker.read_text(encoding="utf-8"), "keep my changes")
                    self.assertTrue((self.local_path / "utils/kos-chain/docker/Dockerfile").is_file())

    def test_builds_from_an_unrelated_working_directory(self):
        with CliRunner().isolated_filesystem():
            caller = Path.cwd()
            for local in (False, True):
                with self.subTest(local=local):
                    result, _processes = self.run_build(kos_path=self.local_path if local else None)
                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertEqual(Path.cwd(), caller)


if __name__ == "__main__":
    unittest.main()
