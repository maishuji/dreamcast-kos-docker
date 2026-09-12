"""Opt-in archive installation tests; provisioning may require package-index access."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


FAKE_TOOL = '''
import json
import os
from pathlib import Path
import sys

if Path(sys.argv[0]).name == 'git':
    assert sys.argv[1:4] == ['clone', '--depth', '1']
    source = Path(sys.argv[-1])
    dockerfile = source / 'utils/kos-chain/docker/Dockerfile'
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text('ARG profile=stable\\nARG include_gdb=0\\n')
    profile = dockerfile.parents[1] / 'profiles/dreamcast/16.2.0.mk'
    profile.parent.mkdir(parents=True)
    profile.write_text('# Test profile\\n')
else:
    args = sys.argv[1:]
    assert args[0] == 'build'
    context = Path(args[-1])
    if '-f' in args:
        assert Path(args[args.index('-f') + 1]).is_file()
        files = {}
    else:
        files = {name: (context / name).read_text() for name in ('Dockerfile', 'apk-retry.sh')}
    Path(os.environ['DCDOCKER_CAPTURE']).write_text(json.dumps({'args': args, 'files': files}))
    sys.exit(int(os.environ.get('DCDOCKER_FAKE_EXIT', '0')))
'''

RUNTIME_GUARD = '''
import os
from pathlib import Path
import sys
import requests

checkout = Path(os.environ['DCDOCKER_FORBIDDEN_CHECKOUT']).resolve()
assert not any(Path(item).resolve().is_relative_to(checkout) for item in sys.path if item)

def audit(event, args):
    if event in ('open', 'os.listdir', 'os.scandir') and args:
        if isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(checkout):
                raise AssertionError('Installed command accessed checkout: ' + str(path))
    if event == 'socket.connect':
        raise AssertionError('Unexpected network access')

sys.addaudithook(audit)

def get(url, **kwargs):
    assert os.environ.get('DCDOCKER_ALLOW_DISCOVERY') == '1', 'Help attempted discovery'
    assert url.startswith('https://gitlab.com/api/v4/projects/')
    assert kwargs['timeout'] == 30
    response = requests.Response()
    response.status_code = 200
    response._content = b'[{"name": "master"}]'
    return response

requests.get = get
sys._dcdocker_guard_enabled = True
'''


@unittest.skipUnless(os.environ.get("DCDOCKER_TEST_PACKAGES") == "1", "use make test-package")
class PackageInstallTests(unittest.TestCase):
    """Install independently built wheels; execute only their code and resources."""

    def run_command(self, command, *, cwd, env, input_text=None):
        """Give provisioning and executable checks bounded runtime and useful failures."""
        result = subprocess.run(command, cwd=cwd, env=env, input=input_text,
                                text=True, capture_output=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_wheel_and_sdist_installations(self):
        """Both archive paths provide a working command with the checkout inaccessible."""
        repository = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(prefix="dcdocker-packages-") as directory:
            workspace = Path(directory)
            project = workspace / "source"
            project.mkdir()
            for name in ("src", "kos-alpine"):
                shutil.copytree(repository / name, project / name,
                                ignore=shutil.ignore_patterns("__pycache__"))
            for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE",
                         "build_dc_toolchain_image.py", "build_dc_kos_full_image.py"):
                shutil.copy2(repository / name, project / name)
            env = os.environ.copy()
            for name in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
                env.pop(name, None)
            uv = shutil.which("uv")
            self.assertIsNotNone(uv, "Package tests require uv")
            self.run_command([uv, "build", "--wheel", "--out-dir", str(workspace / "wheel")],
                             cwd=project, env=env)
            self.run_command([uv, "build", "--sdist", "--out-dir", str(workspace / "sdist")],
                             cwd=project, env=env)
            sdist = next((workspace / "sdist").glob("*.tar.gz"))
            self.run_command([uv, "build", str(sdist), "--wheel", "--out-dir",
                              str(workspace / "rebuilt")], cwd=workspace, env=env)
            # A staged source tree is unnecessary at runtime and must not mask missing assets.
            shutil.rmtree(project)
            for name in ("wheel", "rebuilt"):
                with self.subTest(artifact=name):
                    wheel = next((workspace / name).glob("*.whl"))
                    self.check_installation(uv, wheel, workspace / name, repository, env)

    def check_installation(self, uv, wheel, workspace, repository, environment):
        """Use an isolated environment, stub executables, and a checkout access guard."""
        venv = workspace / "venv"
        self.run_command([uv, "venv", "--python", sys.executable, str(venv)],
                         cwd=workspace, env=environment)
        python = venv / "bin/python"
        self.run_command([uv, "pip", "install", "--python", str(python), str(wheel)],
                         cwd=workspace, env=environment)
        purelib = self.run_command(
            [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            cwd=workspace, env=environment,
        ).stdout.strip()
        # A .pth hook avoids a system sitecustomize shadowing the test guard on Debian.
        (Path(purelib) / "_dcdocker_test_guard.py").write_text(RUNTIME_GUARD, encoding="utf-8")
        (Path(purelib) / "dcdocker_test_guard.pth").write_text(
            "import _dcdocker_test_guard\n", encoding="utf-8"
        )
        fake_bin = workspace / "tools"
        fake_bin.mkdir()
        for name in ("docker", "git"):
            executable = fake_bin / name
            executable.write_text(f"#!{python}\n" + FAKE_TOOL, encoding="utf-8")
            executable.chmod(0o755)
        env = dict(environment, PATH=str(fake_bin), DCDOCKER_FORBIDDEN_CHECKOUT=str(repository),
                   DCDOCKER_CAPTURE=str(workspace / "capture.json"))
        origin = self.run_command(
            [str(python), "-I", "-c", "import sys, dcdocker; "
             "assert sys._dcdocker_guard_enabled; print(dcdocker.__file__)"],
            cwd=workspace, env=env,
        )
        self.assertTrue(Path(origin.stdout.strip()).is_relative_to(venv))
        for command in ([], ["build"], ["build", "dc-chain"], ["build", "kos-image"]):
            self.assertIn("Usage:", self.run_command(
                [str(venv / "bin/dcdocker"), *command, "--help"],
                cwd=workspace, env=dict(env, PATH=""),
            ).stdout)
        self.run_command([str(python), "-m", "dcdocker", "--help"], cwd=workspace, env=env)
        env["DCDOCKER_ALLOW_DISCOVERY"] = "0"
        self.check_builds(venv / "bin/dcdocker", workspace, env)
        self.check_automation(venv / "bin/dcdocker", workspace, env)

    def check_builds(self, executable, workspace, env):
        """Exercise real CLI/process boundaries without a Docker daemon or remote Git."""
        for gdb in (False, True):
            args = [str(executable), "build", "kos-image", "--namespace", "test",
                    "--toolchain-tag", "16.2.0", "--kos-ports-ref", "master",
                    "--kos-ref", "master", "--gldc-ref", "master", "--non-interactive"]
            if gdb:
                args.append("--gdb")
            self.run_command(args, cwd=workspace, env=env, input_text="3\n1\n1\n")
            captured = json.loads(Path(env["DCDOCKER_CAPTURE"]).read_text(encoding="utf-8"))
            self.assertIn(
                f"base_image=maishuji/dc-chain{'-gdb' if gdb else ''}:16.2.0", captured["args"]
            )
            self.assertIn("COPY --chmod=755 apk-retry.sh", captured["files"]["Dockerfile"])
            self.assertIn("#!/bin/sh", captured["files"]["apk-retry.sh"])
            self.assertFalse(Path(captured["args"][-1]).exists())
        result = subprocess.run(args, cwd=workspace, env=dict(env, DCDOCKER_FAKE_EXIT="17"),
                                input="3\n1\n1\n", text=True, capture_output=True,
                                timeout=30, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("exit code 17", result.stderr)
        captured = json.loads(Path(env["DCDOCKER_CAPTURE"]).read_text(encoding="utf-8"))
        self.assertFalse(Path(captured["args"][-1]).exists())
        local = workspace / "local kos"
        dockerfile = local / "utils/kos-chain/docker/Dockerfile"
        dockerfile.parent.mkdir(parents=True)
        dockerfile.write_text("ARG profile=stable\nARG include_gdb=0\n", encoding="utf-8")
        profile = dockerfile.parents[1] / "profiles/dreamcast/16.2.0.mk"
        profile.parent.mkdir(parents=True)
        profile.write_text("# Test profile\n", encoding="utf-8")
        for selection in ([], ["--kos-path", str(local)]):
            self.run_command([str(executable), "build", "dc-chain", "-u", "test", "--gdb",
                              *selection], cwd=workspace, env=env)
            captured = json.loads(Path(env["DCDOCKER_CAPTURE"]).read_text(encoding="utf-8"))
            self.assertIn("include_gdb=1", captured["args"])
            if not selection:
                self.assertFalse(Path(captured["args"][-1]).exists())
            self.assertTrue(dockerfile.is_file())

    def check_automation(self, executable, workspace, env):
        """Installed custom bases and offline previews use the packaged implementation."""
        explicit = ["--kos-ref", "master", "--kos-ports-ref", "master", "--gldc-ref", "master"]
        base = "registry.example:5000/team/toolchain@sha256:" + "a" * 64
        args = [str(executable), "build", "kos-image", "--namespace", "output", *explicit,
                "--base-image", base, "--image-tag", "chosen", "--gdb"]
        self.run_command([*args, "--non-interactive"], cwd=workspace, env=env)
        captured = json.loads(Path(env["DCDOCKER_CAPTURE"]).read_text(encoding="utf-8"))
        self.assertIn("base_image=" + base, captured["args"])
        self.assertIn("output/dc-kos-image:chosen", captured["args"])
        self.assertIn("FROM ${base_image}", captured["files"]["Dockerfile"])
        self.assertNotIn("dc_chain_version", captured["files"]["Dockerfile"])
        capture = Path(env["DCDOCKER_CAPTURE"])
        capture.unlink()
        for command in ([*args, "--dry-run"],
                        [str(executable), "build", "dc-chain", "-u", "test", "--dry-run"]):
            preview = self.run_command(command, cwd=workspace, env=dict(env, PATH=""))
            self.assertIn("Preview only", preview.stdout)
            self.assertFalse(capture.exists())


if __name__ == "__main__":
    unittest.main()
