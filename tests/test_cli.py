"""Installed command routing, aliases, and offline help contracts."""

from pathlib import Path
import unittest
from unittest.mock import patch

import click
from click.testing import CliRunner

from dcdocker import cli, sources


class CommandTests(unittest.TestCase):
    """New spellings and legacy aliases select the same shared builds."""

    def setUp(self):
        self.enterContext(patch.object(cli, "is_interactive", return_value=True))

    def test_help_at_every_level_has_no_side_effects(self):
        """Help must not need Git, Docker, HTTP, stdin, or resource extraction."""
        for boundary in ("subprocess.run", "requests.get", "builtins.input",
                         "dcdocker.sources.ready_context"):
            self.enterContext(patch(boundary, side_effect=AssertionError("Unexpected side effect")))
        for prefix in ([], ["build"], ["build", "dc-chain"], ["build", "kos-image"]):
            with self.subTest(prefix=prefix):
                result = CliRunner().invoke(cli.main, [*prefix, "--help"])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("Usage:", result.output)

    def test_toolchain_option_aliases(self):
        """Every namespace/GDB alias produces the same specification."""
        for namespace in ("--namespace", "--username", "-u"):
            for gdb in ("--gdb", "--use-gdb", "-g"):
                with self.subTest(namespace=namespace, gdb=gdb):
                    with patch.object(cli.builds, "build_toolchain") as build:
                        result = CliRunner().invoke(
                            cli.main, ["build", "dc-chain", namespace, "test", gdb]
                        )
                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertEqual(
                        build.call_args.args[0], cli.builds.ToolchainBuild("test", gdb=True)
                    )

    def test_full_image_aliases(self):
        """Base-tag and kos-ports aliases preserve selections and skip the ports menu."""
        with patch.object(cli, "choose_snapshot_kos", return_value="master"), \
             patch.object(cli, "choose_snapshot_gldc", return_value="master"), \
             patch.object(cli, "choose_snapshot_kosports",
                          side_effect=AssertionError("Ports menu")), \
             patch.object(cli.docker, "execute_build") as execute:
            for tag in ("--toolchain-tag", "--profile", "-p"):
                for ports in ("--kos-ports-ref", "--kos-ports-branch"):
                    result = CliRunner().invoke(
                        cli.main, ["build", "kos-image", "--namespace", "test", tag, "custom",
                                   ports, "feature/branch", "--gdb"], input="1\n",
                    )
                    self.assertEqual(result.exit_code, 0, result.output)
                    command = execute.call_args.args[0]
                    self.assertIn("base_image=maishuji/dc-chain-gdb:custom", command)
                    self.assertIn("snapshot_kosports=feature/branch", command)
                    self.assertIn("base_image=maishuji/dc-chain-gdb:custom", command)

    def test_invalid_input_fails_before_building(self):
        """Usage errors remain exit 2 without external operations."""
        with patch.object(cli.builds, "build_toolchain") as toolchain, \
             patch.object(sources, "ready_context") as context:
            for args in (["build", "unknown"], ["build", "dc-chain"],
                         ["build", "kos-image", "--namespace", "test", "--unknown"],
                         ["build", "dc-chain", "-u", "test", "--kos-path", __file__]):
                result = CliRunner().invoke(cli.main, args)
                self.assertEqual(result.exit_code, 2, result.output)
            toolchain.assert_not_called()
            context.assert_not_called()

    def test_list_snapshots_prints_typed_refs_without_building(self):
        """Snapshot listing prints refs without invoking Docker."""
        with patch.object(cli.sources, "fetch_snapshot_entries",
                          return_value=[("tag", "01FEB25"), ("branch", "master")]), \
             patch.object(cli.docker, "execute_build",
                          side_effect=AssertionError("Docker invoked")):
            result = CliRunner().invoke(cli.main, ["list", "snapshots", "kos"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("TYPE\tREF", result.output)
        self.assertIn("tag\t01FEB25", result.output)
        self.assertIn("branch\tmaster", result.output)

    def test_remote_profile_listing_uses_api_without_checkout_or_docker(self):
        """Remote profiles use the small catalog endpoint instead of cloning."""
        with patch.object(cli.sources, "fetch_toolchain_profiles",
                          return_value=["16.2.0", "stable"]) as profiles, patch.object(
                              cli.sources, "toolchain_checkout",
                              side_effect=AssertionError("Checkout invoked")), patch.object(
                                  cli.docker, "execute_build",
                                  side_effect=AssertionError("Docker invoked")):
            result = CliRunner().invoke(cli.main, ["list", "profiles"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("16.2.0", result.output)
        self.assertIn("stable", result.output)
        profiles.assert_called_once_with(None, False)

    def test_listing_prefix_filters_output_and_short_profile_alias(self):
        """The short alias accepts a prefix and filters normal output."""
        with patch.object(cli.sources, "fetch_toolchain_profiles",
                          return_value=["16.2.0", "stable"]):
            result = CliRunner().invoke(cli.main, ["profiles", "16"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("16.2.0", result.output)
        self.assertNotIn("\nstable\n", result.output)

    def test_profile_completion_reads_cache_only(self):
        """Profile completion never falls back to a network fetch."""
        context = click.Context(cli.list_profiles)
        context.params = {"kos_path": None, "kos_ref": None}
        with patch.object(cli.sources, "cached_toolchain_profiles",
                          return_value=["16.2.0", "stable"]), patch.object(
                              cli.sources, "fetch_toolchain_profiles",
                              side_effect=AssertionError("Network fetch invoked")):
            matches = cli.ProfilePrefixType().shell_complete(context, None, "16")
        self.assertEqual([match.value for match in matches], ["16.2.0"])

    def test_snapshot_completion_filters_cached_source_and_year(self):
        """Snapshot completion forwards source and year to the cache lookup."""
        context = click.Context(cli.list_snapshots)
        context.params = {"source": "kos", "year": 2025}
        with patch.object(cli.sources, "cached_snapshot_entries", return_value=[
                ("tag", "01JAN25"), ("tag", "02FEB24"), ("branch", "master")
        ]) as cached:
            matches = cli.SnapshotPrefixType().shell_complete(context, None, "0")
        self.assertEqual([match.value for match in matches], ["01JAN25", "02FEB24"])
        cached.assert_called_once_with("kos", 2025)


class ResourceTests(unittest.TestCase):
    """Resource lifetime is independent of filesystem or ZIP package installation."""

    def test_context_copies_files_and_cleans_after_failure(self):
        """The copy survives execution; package originals survive cleanup."""
        original = sources.resources.files("dcdocker").joinpath("assets", "kos-ready")
        with self.assertRaisesRegex(RuntimeError, "build failed"):
            with sources.ready_context() as context:
                for name in ("Dockerfile", "apk-retry.sh"):
                    self.assertEqual(
                        (context / name).read_bytes(), original.joinpath(name).read_bytes()
                    )
                raise RuntimeError("build failed")
        self.assertFalse(context.exists())
        self.assertTrue(original.joinpath("Dockerfile").is_file())

    def test_zip_resources_support_python_311(self):
        """Copy Traversable directories without relying on directory as_file support."""
        import zipfile  # pylint: disable=import-outside-toplevel

        with CliRunner().isolated_filesystem():
            with zipfile.ZipFile("assets.zip", "w") as archive:
                archive.writestr("assets/kos-ready/Dockerfile", "FROM scratch\n")
                archive.writestr("assets/kos-ready/apk-retry.sh", "#!/bin/sh\n")
                archive.writestr("assets/kos-ready/source_build.py", "# source helper\n")
                archive.writestr("assets/kos-ready/nested/file", "extra context data")
            with zipfile.ZipFile("assets.zip") as archive:
                with patch.object(sources.resources, "files", return_value=zipfile.Path(archive)):
                    with sources.ready_context() as context:
                        self.assertEqual(
                            (context / "nested/file").read_text(encoding="utf-8"),
                            "extra context data",
                        )
                self.assertFalse(Path(context).exists())


if __name__ == "__main__":
    unittest.main()
