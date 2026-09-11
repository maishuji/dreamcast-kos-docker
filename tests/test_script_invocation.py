"""Invoke absolute script paths in a separate interpreter outside the checkout."""

# Test method names describe their behavior.
# pylint: disable=missing-function-docstring

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


# run_path exercises each script's __main__ entry point and real __file__ value.
# Only discovery and build processes are substituted inside the child interpreter.
SCRIPT_HARNESS = """
import json
import runpy
from pathlib import Path
import sys
from unittest.mock import Mock, patch

script = sys.argv.pop(1)
sys.argv[0] = script
response = Mock(status_code=200, json=Mock(return_value=[{'name': 'master'}]))

def run_build(command, **kwargs):
    if command[:2] != ['docker', 'build']:
        raise AssertionError('Unexpected subprocess: ' + repr(command))
    if any(arg.startswith('snapshot_kos=') for arg in command):
        for name in ('Dockerfile', 'apk-retry.sh'):
            assert (Path(command[-1]) / name).is_file()
    print('CAPTURED_BUILD=' + json.dumps(command))

with patch('requests.get', return_value=response), patch('subprocess.run', side_effect=run_build):
    runpy.run_path(script, run_name='__main__')
"""


class ScriptInvocationTests(unittest.TestCase):
    """Check script path resolution independently of module imports in this suite."""

    def test_absolute_entry_points_from_an_unrelated_directory(self):
        repository = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(prefix="dcdocker caller ") as directory:
            caller = Path(directory)
            (caller / "kos-ready").mkdir()  # Must not shadow the real context.
            local_kos = caller / "local kos"
            dockerfile = local_kos / "utils/kos-chain/docker/Dockerfile"
            dockerfile.parent.mkdir(parents=True)
            dockerfile.write_text("ARG include_gdb=0\n", encoding="utf-8")
            scripts = (
                ("build_dc_kos_full_image.py", ["--kos-ref", "master", "--kos-ports-ref",
                                                   "master", "--gldc-ref", "master",
                                                   "--non-interactive"], None),
                ("build_dc_toolchain_image.py", ["--kos-path", str(local_kos)], local_kos),
            )
            for filename, options, expected_context in scripts:
                with self.subTest(script=filename):
                    result = subprocess.run(
                        [sys.executable, "-c", SCRIPT_HARNESS,
                         str(repository / filename), "-u", "test", *options],
                        cwd=caller, input="3\n3\n1\n1\n", text=True,
                        capture_output=True, timeout=10, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    captured = next(line for line in result.stdout.splitlines()
                                    if line.startswith("CAPTURED_BUILD="))
                    command = json.loads(captured.split("=", 1)[1])
                    self.assertEqual(result.stderr.count("compatibility entry point"), 1)
                    if expected_context is not None:
                        self.assertEqual(Path(command[-1]), expected_context)
                    self.assertTrue(dockerfile.is_file())
                    if filename == "build_dc_kos_full_image.py":
                        self.assertFalse(Path(command[-1]).exists())


if __name__ == "__main__":
    unittest.main()
