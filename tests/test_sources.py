"""Source catalogs and selected-checkout compatibility without live services."""

# pylint: disable=missing-function-docstring

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import click
from click.testing import CliRunner
import requests

from dcdocker import cli, defaults, sources


def response(names, headers=None):
    """Use real Requests header/link parsing against an offline provider fixture."""
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps([{"name": name} for name in names]).encode()  # pylint: disable=protected-access
    result.headers.update(headers or {})
    return result


class DiscoveryTests(unittest.TestCase):
    """Catalogs must be complete, bounded, and separate tags from branches."""

    def test_github_pages_deduplicate_and_discover_years(self):
        url = defaults.KOS_TAGS_URL
        pages = [response(["01JAN24", "01JAN27"],
                          {"Link": f'<{url}?per_page=100&page=2>; rel="next"'}),
                 response(["01JAN24", "02FEB27", "feature27", "master"])]
        with patch.object(sources.requests, "get", side_effect=pages) as get:
            tags = sources.fetch_snapshot_kos_tags()
        self.assertEqual(tags, ["01JAN24", "01JAN27", "02FEB27", "feature27", "master"])
        self.assertEqual(sources.snapshot_years(tags), ["2027", "2024"])
        self.assertEqual(sources.filter_tags_by_year(tags, "2027"), ["01JAN27", "02FEB27"])
        self.assertEqual(sources.filter_tags_by_year(tags, "2025"), [])
        for page, call in enumerate(get.call_args_list, 1):
            self.assertEqual(call.args, (url,))
            self.assertEqual(call.kwargs, {"params": {"per_page": 100, "page": page},
                                          "timeout": defaults.REQUEST_TIMEOUT})

    def test_gitlab_next_page_and_branch_filtering(self):
        pages = [response(["feature/unrelated", "release/01JAN24"], {"X-Next-Page": "2"}),
                 response(["master", "release/01JAN27"], {"X-Next-Page": ""})]
        with patch.object(sources.requests, "get", side_effect=pages) as get:
            branches = sources.fetch_release_branches_gldc()
        self.assertEqual(branches, ["release/01JAN24", "master", "release/01JAN27"])
        self.assertEqual(get.call_count, 2)

    def test_full_pages_without_headers_continue_until_empty(self):
        pages = [response([str(number) for number in range(defaults.REF_PAGE_SIZE)]),
                 response([])]
        with patch.object(sources.requests, "get", side_effect=pages) as get:
            self.assertEqual(len(sources.fetch_snapshot_kosports_tags()), defaults.REF_PAGE_SIZE)
        self.assertEqual(get.call_count, 2)

    def test_repeated_pages_and_empty_intermediate_pages_fail(self):
        for second in (response(["01JAN24"]), response([], {"X-Next-Page": "3"})):
            with self.subTest(second=second.content):
                pages = [response(["01JAN24"], {"X-Next-Page": "2"}), second]
                with patch.object(sources.requests, "get", side_effect=pages) as get:
                    with self.assertRaises(click.ClickException):
                        sources.fetch_snapshot_kos_tags()
                self.assertEqual(get.call_count, 2)

    def test_invalid_pagination_never_follows_another_endpoint(self):
        url = defaults.KOS_TAGS_URL
        headers = [
            {"X-Next-Page": value} for value in ("1", "0", "3", "no", "-1", "٢")
        ] + [
            {"Link": f'<{target}>; rel="next"'} for target in (
                "https://example.org/tags?page=2", url + "?page=1", url + "?cursor=next",
                url + "?page=2&page=3", url.replace("/tags", "/branches") + "?page=2",
            )
        ]
        for header in headers:
            with self.subTest(header=header), patch.object(
                    sources.requests, "get", return_value=response(["01JAN24"], header)) as get:
                with self.assertRaises(click.ClickException):
                    sources.fetch_snapshot_kos_tags()
                get.assert_called_once()

    def test_page_limit_does_not_return_a_partial_catalog(self):
        pages = [response(["01JAN24"], {"X-Next-Page": "2"}),
                 response(["01JAN25"], {"X-Next-Page": "3"})]
        with patch.object(defaults, "MAX_REF_PAGES", 2), patch.object(
                sources.requests, "get", side_effect=pages) as get:
            with self.assertRaisesRegex(click.ClickException, "Pagination limit"):
                sources.fetch_snapshot_kos_tags()
        self.assertEqual(get.call_count, 2)

    def test_failure_on_later_page_discards_partial_results_without_retry(self):
        limited = response([])
        limited.status_code = 429
        limited.headers["Retry-After"] = "3600"
        for failure in (limited, requests.Timeout(), requests.ConnectionError()):
            with self.subTest(failure=failure), patch.object(sources.requests, "get", side_effect=[
                    response(["01JAN24"], {"X-Next-Page": "2"}), failure]) as get:
                with self.assertRaises(click.ClickException):
                    sources.fetch_snapshot_kos_tags()
                self.assertEqual(get.call_count, 2)

    def test_dynamic_menus_label_refs_and_fetch_each_catalog_once(self):
        pages = [response(["01JAN24", "02FEB27", "release27"]),
                 response(["03MAR23"]), response(["release/04APR27"])]
        with patch.object(cli, "is_interactive", return_value=True), patch.object(
                sources.requests, "get", side_effect=pages) as get, patch(
                    "dcdocker.docker.execute_build") as build:
            result = CliRunner().invoke(cli.main, ["build", "kos-image", "-u", "test"],
                                        input="1\n1\n1\n1\n1\n1\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(get.call_count, 3)
        self.assertIn("1. 2027\n2. 2024\n3. master (branch)", result.output)
        self.assertIn("KOS snapshot tag", result.output)
        self.assertIn("release branch for GLdc", result.output)
        self.assertIn("snapshot_kos=02FEB27", build.call_args.args[0])
        self.assertIn("snapshot_kosports=03MAR23", build.call_args.args[0])

    def test_empty_tag_catalog_requires_explicit_branch_selection(self):
        args = ["build", "kos-image", "-u", "test", "--kos-ports-ref", "master",
                "--gldc-ref", "master", "--yes"]
        with patch.object(cli, "is_interactive", return_value=True), patch.object(
                sources.requests, "get", return_value=response([])), patch(
                    "dcdocker.docker.execute_build") as build:
            aborted = CliRunner().invoke(cli.main, args, input="")
            self.assertEqual(aborted.exit_code, 1, aborted.output)
            build.assert_not_called()
            selected = CliRunner().invoke(cli.main, args, input="1\n")
            self.assertEqual(selected.exit_code, 0, selected.output)
            self.assertIn("1. master (branch)", selected.output)
            self.assertIn("snapshot_kos=master", build.call_args.args[0])


class CheckoutCompatibilityTests(unittest.TestCase):
    """Real local files reveal unsupported requests before Docker can start."""

    def setUp(self):
        # pylint: disable-next=consider-using-with
        self.directory = self.enterContext(TemporaryDirectory(prefix="local kos "))
        self.source = Path(self.directory)
        self.dockerfile = self.source / defaults.TOOLCHAIN_DOCKERFILE
        self.dockerfile.parent.mkdir(parents=True)
        self.profile = self.source / defaults.TOOLCHAIN_PROFILES / "custom.mk"
        self.profile.parent.mkdir(parents=True)
        self.profile.write_text("# locally maintained profile\n", encoding="utf-8")
        self.args = ["build", "dc-chain", "-u", "test", "--profile", "custom",
                     "--kos-path", str(self.source)]

    def test_custom_profile_and_supported_arguments_reach_docker(self):
        self.dockerfile.write_text("FROM alpine\nARG profile=stable\n"
                                   "arg\tinclude_gdb=0\nARG makejobs=8\n", encoding="utf-8")
        before = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        with patch("dcdocker.docker.execute_build") as build, patch(
                "subprocess.run", side_effect=AssertionError("Local inspection invoked a process")):
            result = CliRunner().invoke(cli.main, [*self.args, "--gdb"])
        self.assertEqual(result.exit_code, 0, result.output)
        for value in ("profile=custom", "include_gdb=1", "makejobs=4", "test/dc-chain-gdb:custom"):
            self.assertIn(value, build.call_args.args[0])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_optional_arguments_are_omitted_when_not_declared(self):
        self.dockerfile.write_text("FROM alpine\nARG profile=stable\n", encoding="utf-8")
        with patch("dcdocker.docker.execute_build") as build:
            result = CliRunner().invoke(cli.main, self.args)
        self.assertEqual(result.exit_code, 0, result.output)
        command = build.call_args.args[0]
        self.assertIn("profile=custom", command)
        self.assertNotIn("makejobs=4", command)
        self.assertNotIn("include_gdb=0", command)
        self.assertIn("upstream concurrency defaults", result.output)

    def test_missing_profile_or_interface_fails_before_docker(self):
        cases = [("FROM alpine\nARG include_gdb=0\n", [], "ARG profile"),
                 ("FROM alpine\nARG profile=stable\n", ["--gdb"], "include_gdb"),
                 ("FROM alpine\nARG profile=stable\n", ["--profile", "absent"], "absent.mk")]
        for recipe, options, error in cases:
            with self.subTest(error=error), patch("dcdocker.docker.execute_build") as build:
                self.dockerfile.write_text(recipe, encoding="utf-8")
                result = CliRunner().invoke(cli.main, [*self.args, *options])
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn(error, result.output)
                self.assertNotIn("Traceback", result.output)
                build.assert_not_called()

    def test_unreadable_sources_fail_with_controlled_errors(self):
        self.dockerfile.write_text("ARG profile=stable\n", encoding="utf-8")
        for target in (self.profile, self.dockerfile):
            original = target.read_bytes()
            for invalid in (b"\xff", None):
                with self.subTest(target=target, invalid=invalid):
                    target.unlink()
                    if invalid is None:
                        target.mkdir()
                    else:
                        target.write_bytes(invalid)
                    with patch("dcdocker.docker.execute_build") as build:
                        result = CliRunner().invoke(cli.main, self.args)
                    self.assertEqual(result.exit_code, 1, result.output)
                    self.assertIn("Cannot read", result.output)
                    build.assert_not_called()
                    if target.is_dir():
                        target.rmdir()
                    else:
                        target.unlink()
                    target.write_bytes(original)

    def test_arg_syntax_and_shell_text_are_distinguished(self):
        for declaration in ("ARG include_gdb", "arg\tinclude_gdb=0", '  Arg include_gdb="0"',
                            "ARG \\\n# comment\n include_gdb=0", "ARG profile=stable include_gdb=0",
                            "# escape=`\nARG `\n include_gdb=0"):
            with self.subTest(declaration=declaration):
                self.assertIn("include_gdb", sources.dockerfile_arguments(declaration))
        for body in ("# ARG include_gdb=0", "RUN echo ARG include_gdb=0",
                     "ARG include_gdb_extra=0", "ARG INCLUDE_GDB=0",
                     "RUN echo \\\nARG include_gdb=0", "RUN <<'SCRIPT'\nARG include_gdb=0\nSCRIPT",
                     "COPY <<EOF /file\nARG include_gdb=0\nEOF"):
            with self.subTest(body=body):
                self.assertNotIn("include_gdb", sources.dockerfile_arguments(body))
        with self.assertRaisesRegex(click.ClickException, "Cannot parse ARG"):
            sources.dockerfile_arguments('ARG include_gdb="unterminated')


if __name__ == "__main__":
    unittest.main()
