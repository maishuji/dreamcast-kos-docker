"""Automation, reference selection, output naming and offline preview contracts."""

from itertools import product
from pathlib import Path
import unittest
from unittest.mock import patch

import click
from click.testing import CliRunner

from dcdocker import builds, cli, docker, validation


REF_FLAGS = ("--kos-ref", "--kos-ports-ref", "--gldc-ref")
EXPLICIT = [item for flag in REF_FLAGS for item in (flag, "master")]


class AutomationTests(unittest.TestCase):
    """Every combination of missing refs has an explicit prompt policy."""

    def test_all_ref_combinations(self):
        """Interactive builds ask only for omitted refs; automation requires all three."""
        for selected in product((False, True), repeat=3):
            for interactive in (False, True):
                for automated in (False, True):
                    with self.subTest(selected=selected, tty=interactive, automated=automated):
                        self.check_ref_combination(selected, interactive, automated)

    def check_ref_combination(self, selected, interactive, automated):
        """Use failing stdin/HTTP stubs to catch accidental discovery or prompts."""
        args = ["build", "kos-image", "-u", "test"]
        for flag, supplied in zip(REF_FLAGS, selected):
            if supplied:
                args.extend([flag, "master"])
        if automated:
            args.append("--non-interactive")
        with patch.object(cli, "is_interactive", return_value=interactive), \
             patch.object(cli, "choose_snapshot_kos", return_value="master") as kos, \
             patch.object(cli, "choose_snapshot_kosports", return_value="master") as ports, \
             patch.object(cli, "choose_snapshot_gldc", return_value="master") as gldc, \
             patch.object(cli, "prompt_choice", return_value="Yes") as confirm, \
             patch.object(docker, "execute_build") as execute, \
             patch("builtins.input", side_effect=AssertionError("Unexpected stdin")), \
             patch("requests.get", side_effect=AssertionError("Unexpected HTTP")):
            result = CliRunner().invoke(cli.main, args)
        allowed = (automated and all(selected)) or (not automated and interactive)
        self.assertEqual(result.exit_code, 0 if allowed else 2, result.output)
        self.assertEqual(execute.call_count, int(allowed))
        self.assertEqual(confirm.call_count, int(allowed and not automated))
        for supplied, chooser in zip(selected, (kos, ports, gldc)):
            self.assertEqual(chooser.call_count, int(allowed and not supplied))

    def test_yes_skips_only_confirmation(self):
        """--yes still prompts for missing refs on a TTY and fails without one."""
        with patch.object(cli, "is_interactive", return_value=True), \
             patch.object(cli, "choose_snapshot_kos", return_value="master") as kos, \
             patch.object(cli, "choose_snapshot_kosports", return_value="master") as ports, \
             patch.object(cli, "choose_snapshot_gldc", return_value="master") as gldc, \
             patch.object(cli, "prompt_choice", side_effect=AssertionError("Confirmation")), \
             patch.object(docker, "execute_build"):
            result = CliRunner().invoke(cli.main, ["build", "kos-image", "-u", "test", "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        for chooser in (kos, ports, gldc):
            chooser.assert_called_once()
        result = CliRunner().invoke(cli.main, ["build", "kos-image", "-u", "test", "--yes"])
        self.assertEqual(result.exit_code, 2, result.output)

    def test_fully_specified_yes_build_never_reads_stdin(self):
        """Non-TTY explicit refs plus --yes are enough to start execution."""
        with patch("builtins.input", side_effect=AssertionError("Unexpected stdin")), \
             patch("requests.get", side_effect=AssertionError("Unexpected HTTP")), \
             patch.object(docker, "execute_build") as execute:
            result = CliRunner().invoke(cli.main,
                                        ["build", "kos-image", "-u", "test", *EXPLICIT, "--yes"])
        self.assertEqual(result.exit_code, 0, result.output)
        execute.assert_called_once()

    def test_dry_runs_have_no_external_operations(self):
        """No input, HTTP, processes, checkout or temporary context on previews."""
        for boundary in ("builtins.input", "requests.get", "subprocess.run",
                         "dcdocker.sources.ready_context", "dcdocker.sources.toolchain_checkout",
                         "dcdocker.sources.TemporaryDirectory"):
            self.enterContext(patch(boundary, side_effect=AssertionError("Preview side effect")))
        with CliRunner().isolated_filesystem():
            local = Path("local sources")
            local.mkdir()
            for args in (["dc-chain"], ["dc-chain", "--kos-path", str(local)],
                         ["kos-image", *EXPLICIT],
                         ["kos-image", *EXPLICIT, "--base-image", "registry:5000/team/base:v1"]):
                result = CliRunner().invoke(cli.main, ["build", *args, "-u", "test", "--dry-run"])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("Output image:", result.output)
                self.assertIn("Preview only", result.output)
            for selected in product((False, True), repeat=3):
                refs = [item for flag, present in zip(REF_FLAGS, selected)
                        if present for item in (flag, "master")]
                result = CliRunner().invoke(cli.main,
                    ["build", "kos-image", "-u", "test", "--dry-run", *refs])
                self.assertEqual(result.exit_code, 0 if all(selected) else 2, result.output)

    def test_base_conflicts_include_legacy_aliases(self):
        """Only an explicitly supplied toolchain tag conflicts with a custom base."""
        for alias in ("--toolchain-tag", "--profile", "-p"):
            result = CliRunner().invoke(cli.main, ["build", "kos-image", "-u", "test",
                "--base-image", "team/base:v1", alias, "16.2.0", *EXPLICIT, "--dry-run"])
            self.assertEqual(result.exit_code, 2)
            self.assertIn("conflicts", result.output)

    def test_invalid_inputs_fail_before_source_operations(self):
        """Validate names and explicit refs before menus, Git, HTTP or context extraction."""
        for boundary in ("builtins.input", "requests.get", "subprocess.run",
                         "dcdocker.sources.ready_context", "dcdocker.sources.toolchain_checkout"):
            self.enterContext(
                patch(boundary, side_effect=AssertionError("Invalid input side effect"))
            )
        for extra in (["--image-tag", "bad/tag"], ["--image-tag", ""],
                      ["--base-image", "https://registry/base:v1"],
                      ["--base-image", "base@sha256:bad"], ["--kos-ref", ""],
                      ["--kos-ref", "feature/../bad"], ["--gldc-ref", "branch&bad"],
                      ["--namespace", "Bad Namespace"], ["--toolchain-tag", "bad/tag"]):
            with self.subTest(extra=extra):
                result = CliRunner().invoke(cli.main, ["build", "kos-image", "-u", "test", *extra])
                self.assertEqual(result.exit_code, 2, result.output)
        result = CliRunner().invoke(cli.main, ["build", "dc-chain", "-u", "test",
                                               "--profile", "../../bad"])
        self.assertEqual(result.exit_code, 2, result.output)


class ImageSelectionTests(unittest.TestCase):
    """Image references, naming boundaries and source disambiguation are pure."""

    def test_custom_bases_and_gdb_are_authoritative(self):
        """Registry ports and digest references pass unchanged; namespace is output-only."""
        for base in ("team/base:v1", "registry.example:5000/team/base:v1",
                     "[::1]:5000/team/base:v1", "team/base@sha256:" + "a" * 64,
                     "team/base:v1@sha256:" + "b" * 64):
            for gdb in (False, True):
                spec = builds.FullImageBuild("output", gdb=gdb, base_image=base, image_tag="chosen")
                plan = builds.plan_full_image(spec, Path("context"))
                self.assertIn("base_image=" + base, plan.command)
                self.assertEqual(plan.image, "output/dc-kos-image:chosen")
                self.assertFalse(any(arg.startswith("dc_chain_version=") for arg in plan.command))

    def test_default_bases_and_untagged_output_rules(self):
        """Digest-only/untagged bases require a tag override; tagged bases provide the prefix."""
        for base in ("team/base", "team/base@sha256:" + "a" * 64):
            with self.assertRaises(click.BadParameter):
                builds.plan_full_image(builds.FullImageBuild("test", base_image=base), Path("ctx"))
        spec = builds.FullImageBuild("test", base_image="team/base:v2", gdb=True)
        self.assertEqual(builds.plan_full_image(spec, Path("ctx")).image,
                         "test/dc-kos-image:v2-gdb-latest")
        for gdb in (False, True):
            spec = builds.FullImageBuild("custom-output", gdb=gdb)
            self.assertIn(f"base_image=maishuji/dc-chain{'-gdb' if gdb else ''}:16.2.0",
                          builds.plan_full_image(spec, Path("ctx")).command)

    def test_tag_length_and_override_boundaries(self):
        """Reject invalid/oversized output names; overrides do not change profiles or refs."""
        validation.image_tag("a" * 128)
        boundary = builds.FullImageBuild("test", profile="a" * 121)
        self.assertEqual(len(builds.full_image_tag(boundary)), 128)
        with self.assertRaises(click.BadParameter):
            builds.full_image_tag(builds.FullImageBuild("test", profile="a" * 122))
        for value in ("", "-bad", ".bad", "a/b", "a:b", "a" * 129, "é"):
            with self.assertRaises(click.BadParameter):
                validation.image_tag(value)
        spec = builds.FullImageBuild("test", kos_ref="feature/" + "a" * 120)
        with self.assertRaises(click.BadParameter):
            builds.plan_full_image(spec, Path("ctx"))
        spec = builds.FullImageBuild("test", kos_ref="feature/" + "a" * 120, image_tag="short")
        self.assertEqual(builds.plan_full_image(spec, Path("ctx")).image, "test/dc-kos-image:short")
        toolchain = builds.ToolchainBuild("test", "custom-profile", image_tag="custom-output")
        plan = builds.plan_toolchain(toolchain, Path("ctx"))
        self.assertEqual(plan.image, "test/dc-chain:custom-output")
        self.assertIn("profile=custom-profile", plan.command)

    def test_supported_refs_and_image_names(self):
        """Reject invalid source names, image names and malformed digest values offline."""
        for ref in ("feature/nested-name", "release/12SEP26", "version_1.2", "master"):
            validation.source_ref(ref, "--kos-ref")
        for ref in ("/branch", "branch/", "a//b", "a/.b", "a/b.lock", "-branch", "branch."):
            with self.subTest(ref=ref), self.assertRaises(click.BadParameter):
                validation.source_ref(ref, "--kos-ref")
        for reference in ("team/Upper:v1", "registry:port/team/image:v1", "team/image:",
                          "team/image@sha256:" + "A" * 64, "team/image@unknown:" + "a" * 64):
            with self.subTest(reference=reference), self.assertRaises(click.BadParameter):
                validation.image_reference(reference)

    def test_ref_normalization_is_deterministic_and_distinct(self):
        """Case, slash normalization and GLdc branch suffixes cannot silently alias."""
        for field in ("kos_ref", "kos_ports_ref", "gldc_ref"):
            tags = []
            for ref in ("feature/A", "feature/a", "feature-a", "release/one", "other/one"):
                spec = builds.FullImageBuild("test", **{field: ref})
                plan = builds.plan_full_image(spec, Path("ctx"))
                self.assertEqual(plan, builds.plan_full_image(spec, Path("ctx")))
                tags.append(plan.image)
                self.assertRegex(plan.image, r"-r[0-9a-f]{12}$")
            self.assertEqual(len(tags), len(set(tags)))


if __name__ == "__main__":
    unittest.main()
