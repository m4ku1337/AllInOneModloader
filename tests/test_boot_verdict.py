"""Regression tests for readiness detection and profile completeness.

Both bugs here were found by CI artifacts rather than by any local run, which
is why they are worth pinning down:

- Paper logged `Done (18.668s)!` and was still scored a failure, because the
  readiness scan only looked at the last 400 lines and Paper emits thousands
  before it. The marker had scrolled out of the window.
- Fabric produced a launcher jar but no `server.jar`, and its installer exits
  without that being noticed, so the boot died with "Missing game jar".
"""
from __future__ import annotations

import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from aiom.core import launcher


class ReadinessMarkerTests(unittest.TestCase):
    """The marker must be caught whenever it streams past, not by re-scanning."""

    def test_marker_found_far_earlier_in_output(self):
        tmp = Path(tempfile.mkdtemp())
        script = tmp / "srv.py"
        # 5000 lines of noise, then readiness -- the shape that defeated the
        # sliding-window scan.
        script.write_text(
            "import sys, time\n"
            "for i in range(5000):\n"
            "    print('noise line %d' % i, flush=True)\n"
            "print('Done (12.5s)! For help, type \"help\"', flush=True)\n"
            "time.sleep(120)\n",
            encoding="utf-8",
        )
        import sys as _sys
        cmd = [_sys.executable, str(script)]
        started = time.time()
        out, _code = launcher.boot(cmd, tmp / "boot.log", timeout=60,
                                   stop_marker="Done (", cwd=tmp)
        elapsed = time.time() - started

        self.assertIn("Done (12.5s)!", out)
        outcome, why = launcher.classify(out, None)
        self.assertEqual(outcome, launcher.Outcome.PASS,
                         f"expected pass, got {outcome.value}: {why}")
        # It must stop promptly rather than running the full timeout.
        self.assertLess(elapsed, 55, "boot did not stop after readiness")

    def test_marker_never_printed_times_out_as_not_ready(self):
        tmp = Path(tempfile.mkdtemp())
        script = tmp / "quiet.py"
        script.write_text(
            "import time\nprint('starting up', flush=True)\ntime.sleep(300)\n",
            encoding="utf-8",
        )
        import sys as _sys
        out, _code = launcher.boot([_sys.executable, str(script)],
                                   tmp / "boot.log", timeout=3,
                                   stop_marker="Done (", cwd=tmp)
        outcome, _why = launcher.classify(out, None)
        self.assertEqual(outcome, launcher.Outcome.FAIL_NOT_READY)


class FabricProfileTests(unittest.TestCase):
    """A launcher jar without server.jar cannot boot; fail earlier instead."""

    def test_server_jar_downloaded_when_installer_omits_it(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "fabric-server-launch.jar").write_bytes(b"launcher")

        with mock.patch.object(launcher, "FABRIC_INSTALLER", "http://x/i.jar"), \
                mock.patch.object(launcher, "CACHE", tmp), \
                mock.patch.object(launcher, "fetch_file",
                                  return_value=tmp / "installer.jar"), \
                mock.patch.object(launcher.fabric, "latest_loader",
                                  return_value="0.19.5"), \
                mock.patch.object(launcher.mcmeta, "java_major",
                                  return_value=25),                 mock.patch.object(launcher.javart, "resolve",
                                  return_value=(Path("/j"), 25)), \
                mock.patch.object(launcher.subprocess, "run",
                                  return_value=subprocess.CompletedProcess(
                                      [], 0, "", "")), \
                mock.patch.object(launcher.mcmeta, "server_jar") as server_jar:
            server_jar.side_effect = \
                lambda mc, dest=None: dest.write_bytes(b"x" * 2048) or dest
            launcher.prepare_fabric(tmp, "26.2")
        server_jar.assert_called_once()

    def test_installer_failure_reports_its_output(self):
        tmp = Path(tempfile.mkdtemp())
        with mock.patch.object(launcher, "FABRIC_INSTALLER", "http://x/i.jar"), \
                mock.patch.object(launcher, "CACHE", tmp), \
                mock.patch.object(launcher, "fetch_file",
                                  return_value=tmp / "installer.jar"), \
                mock.patch.object(launcher.fabric, "latest_loader",
                                  return_value="0.19.5"), \
                mock.patch.object(launcher.mcmeta, "java_major",
                                  return_value=25),                 mock.patch.object(launcher.javart, "resolve",
                                  return_value=(Path("/j"), 25)), \
                mock.patch.object(launcher.subprocess, "run",
                                  return_value=subprocess.CompletedProcess(
                                      [], 1, "", "network unreachable")):
            with self.assertRaises(RuntimeError) as ctx:
                launcher.prepare_fabric(tmp, "26.2")
        # A silent installer must not look like a generic failure.
        self.assertIn("network unreachable", str(ctx.exception))

    def test_existing_server_jar_is_left_alone(self):
        tmp = Path(tempfile.mkdtemp())
        existing = tmp / "server.jar"
        existing.write_bytes(b"x" * 4096)
        with mock.patch.object(launcher.mcmeta, "server_jar") as server_jar:
            launcher._ensure_server_jar(tmp, "26.2")
        server_jar.assert_not_called()


if __name__ == "__main__":
    unittest.main()