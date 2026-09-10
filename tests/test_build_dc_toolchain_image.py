"""Regression checks for upstream GDB selection and build failure handling."""

import subprocess
import unittest
from unittest.mock import patch

from click.testing import CliRunner

import build_dc_toolchain_image as toolchain


class ToolchainBuildTests(unittest.TestCase):
    """Exercise the CLI without running Docker or requiring a KOS checkout."""

    def run_build(self, returncode=0, use_gdb=False, dockerfile="ARG include_gdb=0\n"):
        """Simulate Docker's exit code, honoring subprocess's check argument."""
        def docker_run(command, **kwargs):
            if kwargs.get("check") and returncode:
                raise subprocess.CalledProcessError(returncode, command)
            return subprocess.CompletedProcess(command, returncode)

        args = ["-u", "test", "-p", "16.2.0"]
        if use_gdb:
            args.append("--use-gdb")
        with patch.object(toolchain.os, "chdir"), patch.object(
            toolchain.Path, "read_text", return_value=dockerfile
        ), patch.object(toolchain.subprocess, "run", side_effect=docker_run) as docker:
            result = CliRunner().invoke(toolchain.main, args)
        return result, docker

    def test_builds_one_image_with_upstream_gdb_argument(self):
        for use_gdb in (False, True):
            with self.subTest(use_gdb=use_gdb):
                result, docker = self.run_build(use_gdb=use_gdb)
                self.assertEqual(result.exit_code, 0, result.output)
                docker.assert_called_once()
                command = docker.call_args.args[0]
                repository = "dc-chain-gdb" if use_gdb else "dc-chain"
                self.assertEqual(command[command.index("-t") + 1], f"test/{repository}:16.2.0")
                self.assertEqual(
                    command[command.index("-f") + 1], "./utils/kos-chain/docker/Dockerfile"
                )
                self.assertIn(f"include_gdb={int(use_gdb)}", command)
                self.assertIn("profile=16.2.0", command)
                self.assertEqual(command[-1], ".")
                self.assertIn("Successfully built Docker image", result.output)

    def test_build_failure_is_reported_with_and_without_gdb(self):
        for use_gdb in (False, True):
            with self.subTest(use_gdb=use_gdb):
                result, docker = self.run_build(returncode=17, use_gdb=use_gdb)
                self.assertEqual(result.exit_code, 1)
                docker.assert_called_once()
                self.assertIn("Toolchain Docker build failed (exit code 17)", result.output)
                self.assertNotIn("Successfully built", result.output)
                self.assertNotIn("Traceback", result.output)

    def test_gdb_requires_updated_checkout(self):
        result, docker = self.run_build(use_gdb=True, dockerfile="ARG profile=stable\n")
        self.assertEqual(result.exit_code, 1)
        docker.assert_not_called()
        self.assertIn("Update your checkout", result.output)
        self.assertNotIn("Successfully built", result.output)

    def test_old_checkout_can_still_build_without_gdb(self):
        result, docker = self.run_build(dockerfile="ARG profile=stable\n")
        self.assertEqual(result.exit_code, 0)
        docker.assert_called_once()


if __name__ == "__main__":
    unittest.main()
