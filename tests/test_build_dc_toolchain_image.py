"""Regression checks for toolchain and GDB build failure handling."""

import subprocess
import unittest
from unittest.mock import patch

from click.testing import CliRunner

import build_dc_toolchain_image as toolchain


class BuildFailureTests(unittest.TestCase):
    """Exercise CLI exit status and build sequencing without running Docker."""

    def run_build(self, returncodes, use_gdb=True):
        """Simulate Docker exit codes, honoring subprocess's check argument."""
        codes = iter(returncodes)

        def docker_run(command, **kwargs):
            code = next(codes)
            if kwargs.get("check") and code:
                raise subprocess.CalledProcessError(code, command)
            return subprocess.CompletedProcess(command, code)

        args = ["-u", "test", "-p", "stable"]
        if use_gdb:
            args.append("--use-gdb")
        with patch.object(toolchain.os, "chdir"), patch.object(
            toolchain.subprocess, "run", side_effect=docker_run
        ) as docker:
            result = CliRunner().invoke(toolchain.main, args)
        return result, docker

    def test_base_failure_stops_before_gdb(self):
        result, docker = self.run_build([17, 0])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(docker.call_count, 1)
        self.assertIn("Toolchain Docker build failed (exit code 17)", result.output)
        self.assertNotIn("Successfully built", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_gdb_failure_is_reported(self):
        result, docker = self.run_build([0, 23])
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(docker.call_count, 2)
        self.assertIn("Successfully built Docker image: test/dc-chain:stable", result.output)
        self.assertIn("GDB Docker build failed (exit code 23)", result.output)
        self.assertNotIn("Successfully built GDB-enabled", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_successful_gdb_build(self):
        result, docker = self.run_build([0, 0])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(docker.call_count, 2)
        self.assertIn("base_image=test/dc-chain:stable", docker.call_args.args[0])
        self.assertIn("Successfully built GDB-enabled", result.output)

    def test_base_only_build(self):
        for code in (0, 17):
            with self.subTest(code=code):
                result, docker = self.run_build([code], use_gdb=False)
                self.assertEqual(result.exit_code, int(code != 0))
                self.assertEqual(docker.call_count, 1)
                self.assertNotIn("Successfully built GDB-enabled", result.output)


if __name__ == "__main__":
    unittest.main()
