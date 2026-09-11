"""Installed command routing, aliases, and offline help contracts."""

from pathlib import Path
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from dcdocker import cli, sources


class CommandTests(unittest.TestCase):
    """New spellings and legacy aliases select the same shared builds."""

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
                    self.assertIn("dc_chain_version=custom", command)
                    self.assertIn("snapshot_kosports=feature/branch", command)
                    self.assertIn("base_image=dc-chain-gdb", command)

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
