"""Behavioral contracts for pure plans and the shared Docker execution boundary."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch

from dcdocker import builds, defaults, docker


class BuildPlanTests(unittest.TestCase):
    """Keep plans usable before sources or build contexts exist."""

    def setUp(self):
        for boundary in ("builtins.input", "subprocess.run", "requests.get", "pathlib.Path.open"):
            self.enterContext(
                patch(boundary, side_effect=AssertionError("Planning has side effects"))
            )

    def test_toolchain_commands_preserve_defaults_and_custom_profiles(self):
        """Compare the complete command for normal and GDB builds."""
        source = Path("/not checked out/local kos")
        for gdb in (False, True):
            for profile in (defaults.DEFAULT_DC_CHAIN_PROFILE, "custom"):
                with self.subTest(gdb=gdb, profile=profile):
                    spec = builds.ToolchainBuild("test", profile, gdb)
                    plan = builds.plan_toolchain(spec, source)
                    image = f"test/dc-chain{'-gdb' if gdb else ''}:{profile}"
                    self.assertEqual(plan.image, image)
                    self.assertEqual(plan.command, (
                        "docker", "build", "--build-arg", f"profile={profile}",
                        "--build-arg", "makejobs=4", "--build-arg", f"include_gdb={int(gdb)}",
                        "-t", image, "-f", str(source / defaults.TOOLCHAIN_DOCKERFILE), str(source),
                    ))

    def test_full_image_snapshot_names_and_arguments(self):
        """Preserve legacy tag shapes for all combinations of snapshot selections."""
        for gdb in (False, True):
            for kos in ("master", "01MAR25"):
                for ports in ("master", "02MAR25"):
                    for gldc in ("master", "release/03MAR25"):
                        with self.subTest(gdb=gdb, kos=kos, ports=ports, gldc=gldc):
                            spec = builds.FullImageBuild("test", "16.2.0", kos, ports, gldc, gdb)
                            plan = builds.plan_full_image(spec, Path("/context with spaces"))
                            tag = "16.2.0-" + ("gdb-" if gdb else "")
                            tag += "latest" if kos == "master" else "01mar25"
                            tag += "" if ports == "master" else "-kp02mar25"
                            tag += "" if gldc == "master" else "-gl03mar25"
                            self.assertEqual(plan.image, f"test/dc-kos-image:{tag}")
                            self.assertEqual(plan.command, (
                                "docker", "build", "--build-arg",
                                f"base_image=maishuji/dc-chain{'-gdb' if gdb else ''}:16.2.0",
                                "--build-arg", f"snapshot_kos={kos}",
                                "--build-arg", f"snapshot_kosports={ports}",
                                "--build-arg", f"snapshot_gldc={gldc}",
                                "-t", plan.image, "/context with spaces",
                            ))

    def test_specs_and_plans_are_immutable(self):
        """A preview cannot silently mutate subsequent execution inputs."""
        spec = builds.ToolchainBuild("test")
        plan = builds.plan_toolchain(spec, Path("/sources"))
        with self.assertRaises(FrozenInstanceError):
            spec.profile = "different"
        with self.assertRaises(FrozenInstanceError):
            plan.image = "different"
        self.assertIsInstance(plan.command, tuple)


class DockerExecutionTests(unittest.TestCase):
    """Display quoting must never become a shell execution step."""

    def test_literal_arguments_survive_display_and_execution(self):
        """Spaces, quotes, dollars, and backticks stay in single argument values."""
        ref = "feature/literal '$HOME' `text`; echo example"
        command = docker.build_command("test/image:tag", Path("/context with 'quotes'"),
                                       (("snapshot_kosports", ref),))
        plan = builds.BuildPlan("test/image:tag", command)
        self.assertEqual(shlex.split(docker.display_command(plan.command)), list(plan.command))
        with patch.object(docker.subprocess, "run") as run:
            docker.execute_build(plan.command)
        run.assert_called_once_with(list(plan.command), check=True, shell=False)
        self.assertIn(f"snapshot_kosports={ref}", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
