"""Provenance uses real local Git histories and mocked Docker, with no remote services."""

# pylint: disable=missing-function-docstring

import importlib.util
import json
from functools import partial
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import click
from click.testing import CliRunner

from dcdocker import builds, cli, defaults, docker, provenance, sources


IMAGE_ID = "sha256:" + "a" * 64
CONTAINER_ID = "b" * 64
HELPER_PATH = Path(__file__).resolve().parents[1] / "src/dcdocker/assets/kos-ready/source_build.py"
HELPER_SPEC = importlib.util.spec_from_file_location("source_build", HELPER_PATH)
HELPER = importlib.util.module_from_spec(HELPER_SPEC)
HELPER_SPEC.loader.exec_module(HELPER)


def git(path, *arguments):
    """Use independent fixture identity and disable contributor hooks."""
    return subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "core.hooksPath=/dev/null", "-C", str(path), *arguments],
        check=True, capture_output=True, text=True, timeout=20,
    ).stdout.strip()


def fake_metadata_command(*args, captured, manifest):
    """Stub Docker metadata commands for full-image report tests."""
    captured.append(args)
    if args[0] == "create":
        assert args[-1] == IMAGE_ID
        return CONTAINER_ID
    if args[0] == "cp":
        Path(args[-1]).write_text(json.dumps(manifest), "utf-8")
    return ""


class LocalRepositoryTests(unittest.TestCase):
    """Real histories distinguish pinned commits, moved refs and local modifications."""

    def setUp(self):
        # pylint: disable-next=consider-using-with
        self.root = Path(self.enterContext(TemporaryDirectory(prefix="dcdocker-history-")))
        self.repository = self.root / "remote"
        self.repository.mkdir()
        git(self.repository, "init", "-b", "master")
        dockerfile = self.repository / defaults.TOOLCHAIN_DOCKERFILE
        dockerfile.parent.mkdir(parents=True)
        dockerfile.write_text("FROM scratch\nARG profile=stable\nARG include_gdb=0\n", "utf-8")
        profile = self.repository / defaults.TOOLCHAIN_PROFILES / "16.2.0.mk"
        profile.parent.mkdir(parents=True)
        profile.write_text("# profile\n", "utf-8")
        git(self.repository, "add", ".")
        git(self.repository, "commit", "-m", "initial")
        self.initial = git(self.repository, "rev-parse", "HEAD")
        git(self.repository, "tag", "snapshot")
        git(self.repository, "tag", "-a", "annotated", "-m", "annotated snapshot")

    def advance(self):
        (self.repository / "new.txt").write_text("new revision", "utf-8")
        git(self.repository, "add", ".")
        git(self.repository, "commit", "-m", "advance branch")
        return git(self.repository, "rev-parse", "HEAD")

    def test_read_only_local_clean_dirty_untracked_and_detached_states(self):
        git(self.repository, "remote", "add", "origin",
            "https://user:secret@example.org/kos?token=x")
        index = self.repository / ".git/index"
        before = (index.read_bytes(), index.stat().st_mtime_ns)
        source = provenance.inspect_source(self.repository)
        self.assertEqual(source["commit"], self.initial)
        self.assertEqual(source["state"], "clean")
        self.assertFalse(source["dirty"])
        self.assertEqual(source["repository"], "https://example.org/kos")
        self.assertEqual(before, (index.read_bytes(), index.stat().st_mtime_ns))
        (self.repository / defaults.TOOLCHAIN_DOCKERFILE).write_text("changed\n", "utf-8")
        (self.repository / "untracked").write_text("local file\n", "utf-8")
        dirty = provenance.inspect_source(self.repository)
        self.assertTrue(dirty["dirty"])
        self.assertEqual(dirty["commit"], self.initial)
        git(self.repository, "checkout", "--detach", self.initial)
        self.assertEqual(provenance.inspect_source(self.repository)["commit"], self.initial)
        self.assertEqual((self.repository / "untracked").read_text("utf-8"), "local file\n")

    def test_non_git_and_unavailable_git_do_not_invent_parent_revisions(self):
        nested = self.repository / "nested"
        nested.mkdir()
        with patch.object(provenance, "git_read", side_effect=AssertionError("parent inspection")):
            source = provenance.inspect_source(nested)
        self.assertEqual(source["state"], "non-git")
        self.assertIsNone(source["commit"])
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("git", 30)):
            with self.subTest(error=error), patch.object(provenance, "git_read", side_effect=error):
                source = provenance.inspect_source(self.repository)
            self.assertEqual(source["state"], "unknown")
            self.assertIsNone(source["dirty"])

    def test_remote_checkout_handles_branches_tags_commits_and_moved_refs(self):
        moved = self.advance()
        refs = {"master": moved, "snapshot": self.initial, "annotated": self.initial,
                "refs/heads/master": moved, "refs/tags/snapshot": self.initial,
                self.initial: self.initial}
        with patch.object(defaults, "KOS_REPOSITORY", self.repository.as_uri()):
            for ref, expected in refs.items():
                with self.subTest(ref=ref), sources.toolchain_checkout(kos_ref=ref) as checkout:
                    observed = provenance.inspect_source(checkout, ref)
                    self.assertEqual(observed["commit"], expected)
                    self.assertEqual(observed["requested_ref"], ref)
                    self.assertEqual(git(checkout, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")
                self.assertFalse(checkout.exists())
            for ref in ("missing", "f" * 40):
                with self.subTest(ref=ref), self.assertRaisesRegex(
                        click.ClickException, "fallback"):
                    with sources.toolchain_checkout(kos_ref=ref):
                        self.fail("Missing revision must never yield a checkout")

    def test_recipe_checkout_uses_identical_pin_semantics(self):
        moved = self.advance()
        for number, (ref, expected) in enumerate((
                ("master", moved), ("snapshot", self.initial),
                ("annotated", self.initial), (self.initial, self.initial))):
            with self.subTest(ref=ref):
                path = self.root / str(number)
                self.assertEqual(HELPER.checkout(self.repository.as_uri(), ref, path), expected)
                self.assertEqual(HELPER.observe(path, ref)["commit"], expected)
        with self.assertRaises(subprocess.CalledProcessError):
            HELPER.checkout(self.repository.as_uri(), "absent", self.root / "failed")

    def test_gldc_port_compiles_seeded_checkout_without_updating_moved_branch(self):
        ports = self.root / "ports"
        (ports / "libGL").mkdir(parents=True)
        (ports / "scripts").mkdir()
        # Minimal make fixture exercises the upstream download/unpack contract: an existing
        # dist + nonempty GIT_TAG skips pull, and unpack copies that Git checkout to build.
        (ports / "scripts/download.mk").write_text('''fetch:
	@if [ ! -d "dist/${PORTNAME}-${PORTVERSION}" ]; then exit 99; \\
	elif [ -z "${GIT_TAG}" ]; then cd dist/${PORTNAME}-${PORTVERSION} && git pull; fi
''', "utf-8")
        (ports / "scripts/unpack.mk").write_text('''unpack: fetch
	mkdir -p build
	cd build && cp -r ../dist/${PORTNAME}-${PORTVERSION} .
''', "utf-8")
        (ports / "libGL/Makefile").write_text('''PORTNAME = libGL
PORTVERSION = 1.0
GIT_REPOSITORY = unused
include ../scripts/download.mk
include ../scripts/unpack.mk
install: unpack
	test -f build/libGL-1.0/utils/kos-chain/docker/Dockerfile
''', "utf-8")
        selection = self.root / "selected.json"
        HELPER.prepare_gldc(ports, "master", selection, self.repository.as_uri())
        self.advance()
        subprocess.run(["make", "-C", str(ports / "libGL"), "install"],
                       check=True, capture_output=True, timeout=20)
        record = self.root / "gldc.json"
        HELPER.record_gldc(selection, record)
        self.assertEqual(json.loads(record.read_text("utf-8"))["commit"], self.initial)
        git(ports / "libGL/build/libGL-1.0", "fetch", "origin", "master")
        git(ports / "libGL/build/libGL-1.0", "checkout", "--detach", "FETCH_HEAD")
        with self.assertRaisesRegex(ValueError, "different commit"):
            HELPER.record_gldc(selection, record)
        (ports / "scripts/download.mk").write_text("unsupported\n", "utf-8")
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            HELPER.prepare_gldc(ports, "master", selection, self.repository.as_uri())


class MetadataTests(unittest.TestCase):
    """Reports bind to completed build IDs and expose failures without stale success."""

    def setUp(self):
        # pylint: disable-next=consider-using-with
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.metadata = self.root / "report.json"
        self.local = self.root / "local"
        recipe = self.local / defaults.TOOLCHAIN_DOCKERFILE
        recipe.parent.mkdir(parents=True)
        recipe.write_text("FROM scratch\nARG profile=stable\n", "utf-8")
        profile = self.local / defaults.TOOLCHAIN_PROFILES / "16.2.0.mk"
        profile.parent.mkdir(parents=True)
        profile.write_text("# profile", "utf-8")

    @staticmethod
    def successful_build(command, *_args):
        Path(command[command.index("--iidfile") + 1]).write_text(IMAGE_ID, "utf-8")

    def test_toolchain_report_contains_unknown_source_and_recipe_identity(self):
        with patch.object(docker, "execute_build", side_effect=self.successful_build):
            result = CliRunner().invoke(cli.main, ["build", "dc-chain", "-u", "test",
                "--kos-path", str(self.local), "--metadata-file", str(self.metadata)])
        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(self.metadata.read_text("utf-8"))
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["image"]["id"], IMAGE_ID)
        self.assertIsNone(report["sources"]["kos"]["commit"])
        self.assertIsNone(report["sources"]["kos"]["dirty"])
        self.assertEqual(report["sources"]["kos"]["state"], "non-git")
        self.assertEqual(report["profile"], "16.2.0")
        self.assertEqual(len(report["dockerfile"]["sha256"]), 64)
        self.assertIsNotNone(report["finished_at"])

    def test_failed_and_interrupted_builds_never_record_success(self):
        for error, state in ((click.ClickException("build exit 17"), "failed"),
                             (KeyboardInterrupt(), "cancelled")):
            with self.subTest(state=state), patch.object(
                    docker, "execute_build", side_effect=error):
                self.metadata.unlink(missing_ok=True)
                result = CliRunner().invoke(cli.main, ["build", "dc-chain", "-u", "test",
                    "--kos-path", str(self.local), "--metadata-file", str(self.metadata)])
            self.assertEqual(result.exit_code, 1, result.output)
            report = json.loads(self.metadata.read_text("utf-8"))
            self.assertEqual(report["status"], state)
            self.assertIsNone(report["image"]["id"])
            self.assertTrue(report["error"])

    def test_conflicting_source_and_existing_or_unwritable_report_fail_before_build(self):
        self.metadata.write_text("existing", "utf-8")
        base = ["build", "dc-chain", "-u", "test", "--kos-path", str(self.local)]
        cases = [("--kos-ref", "master"), ("--metadata-file", str(self.metadata)),
                 ("--metadata-file", str(self.root / "absent/report.json")),
                 ("--metadata-file", str(self.local / "metadata.json"))]
        for options in cases:
            with self.subTest(options=options), patch.object(docker, "execute_build") as build:
                result = CliRunner().invoke(cli.main, [*base, *options])
            self.assertNotEqual(result.exit_code, 0, result.output)
            build.assert_not_called()
        self.assertEqual(self.metadata.read_text("utf-8"), "existing")

    def test_metadata_write_failure_after_docker_is_visible(self):
        original = provenance.write_report
        def fail_final(path, report):
            if report["status"] == "success":
                raise click.ClickException("Cannot write build metadata")
            original(path, report)
        with patch.object(docker, "execute_build", side_effect=self.successful_build), patch.object(
                provenance, "write_report", side_effect=fail_final):
            result = CliRunner().invoke(cli.main, ["build", "dc-chain", "-u", "test",
                "--kos-path", str(self.local), "--metadata-file", str(self.metadata)])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Cannot write build metadata", result.output)
        self.assertEqual(json.loads(self.metadata.read_text("utf-8"))["status"], "running")

    def test_preview_does_not_fetch_inspect_or_write_metadata(self):
        for arguments in (["dc-chain", "--kos-ref", "a" * 40],
                          ["kos-image", "--kos-ref", "master", "--kos-ports-ref", "master",
                           "--gldc-ref", "master"]):
            with self.subTest(arguments=arguments), patch(
                    "subprocess.run", side_effect=AssertionError), \
                    patch.object(provenance, "inspect_source", side_effect=AssertionError), \
                    patch.object(provenance, "write_report", side_effect=AssertionError):
                result = CliRunner().invoke(cli.main, ["build", *arguments, "-u", "test",
                    "--dry-run", "--metadata-file", str(self.metadata)])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("not written in preview", result.output)
            self.assertFalse(self.metadata.exists())

    def test_full_image_observations_come_from_output_id_and_are_validated(self):
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), sources.ready_context() as context:
                self.metadata.unlink(missing_ok=True)
                spec = builds.FullImageBuild("test")
                observed = {"requested_ref": "master", "commit": "c" * 40,
                            "repository": "https://example.org/source", "path": "/source",
                            "dirty": False, "state": "clean"}
                data = {"schema_version": 1,
                        "sources": {name: dict(observed) for name in ("kos", "kos_ports", "gldc")}}
                if corrupt:
                    data["sources"]["kos"]["requested_ref"] = "wrong"
                calls = []
                with patch.object(docker, "execute_build", side_effect=self.successful_build), \
                        patch.object(docker, "read_command", side_effect=partial(
                            fake_metadata_command, captured=calls, manifest=data)):
                    if corrupt:
                        with self.assertRaisesRegex(click.ClickException, "Invalid build evidence"):
                            builds.build_full_image(spec, builds.plan_full_image(spec, context),
                                                    self.metadata)
                    else:
                        builds.build_full_image(spec, builds.plan_full_image(spec, context),
                                                self.metadata)
                self.assertEqual([call[0] for call in calls], ["create", "cp", "rm"])
                self.assertEqual(calls[-1], ("rm", "--volumes", CONTAINER_ID))
                report = json.loads(self.metadata.read_text("utf-8"))
                self.assertEqual(report["status"], "failed" if corrupt else "success")
                self.assertEqual(report["image"]["id"], IMAGE_ID)
                self.assertIsNone(report["base"]["digest"])
                if not corrupt:
                    self.assertEqual(report["sources"]["kos"]["commit"], "c" * 40)

    def test_container_cleanup_after_copy_failure(self):
        with patch.object(docker, "read_command", side_effect=[CONTAINER_ID,
                click.ClickException("copy failed"), ""]) as process:
            with self.assertRaisesRegex(click.ClickException, "copy failed"):
                docker.copy_image_file(IMAGE_ID, "/sources.json", self.metadata)
        self.assertEqual(process.call_args.args, ("rm", "--volumes", CONTAINER_ID))


if __name__ == "__main__":
    unittest.main()
