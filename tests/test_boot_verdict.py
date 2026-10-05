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


class ServerFileLogTests(unittest.TestCase):
    """Paper and Forge signal readiness in logs/latest.log, not on stdout.

    Scoring the run from the pipe alone marked both healthy loaders as broken
    while their own logs plainly said Done (...).
    """

    def test_marker_written_only_to_file_is_still_pass(self):
        tmp = Path(tempfile.mkdtemp())
        logs = tmp / "logs"
        logs.mkdir()
        script = tmp / "srv.py"
        script.write_text(
            "import pathlib, time\n"
            "p = pathlib.Path('logs/latest.log')\n"
            "p.write_text('starting\\n', encoding='utf-8')\n"
            "time.sleep(1)\n"
            "with p.open('a', encoding='utf-8') as fh:\n"
            "    fh.write('Done (9.9s)! For help, type \\\"help\\\"\\n')\n"
            "time.sleep(120)\n",
            encoding="utf-8",
        )
        import sys as _sys
        out, _code = launcher.boot([_sys.executable, str(script)],
                                   tmp / "boot.log", timeout=60,
                                   stop_marker="Done (", cwd=tmp)
        outcome, why = launcher.classify(out, None)
        self.assertEqual(outcome, launcher.Outcome.PASS,
                         f"expected pass, got {outcome.value}: {why}")

    def test_file_log_is_appended_to_returned_output(self):
        tmp = Path(tempfile.mkdtemp())
        logs = tmp / "logs"
        logs.mkdir()
        (logs / "latest.log").write_text(
            'Done (3.3s)! For help, type "help"\n', encoding="utf-8")
        tail = launcher._LogTail(tmp)
        self.assertTrue(tail.contains("Done ("))
        self.assertIn("Done (3.3s)!", tail.text)

    def test_tail_reads_new_content_each_call(self):
        tmp = Path(tempfile.mkdtemp())
        logs = tmp / "logs"
        logs.mkdir()
        target = logs / "latest.log"
        target.write_text("alpha\n", encoding="utf-8")
        tail = launcher._LogTail(tmp)
        # The first poll must see what is already there: on a retry the marker
        # may predate our first look.
        self.assertTrue(tail.contains("alpha"))
        with target.open("a", encoding="utf-8") as fh:
            fh.write("beta\n")
        self.assertTrue(tail.contains("beta"))
        # Incremental: the second poll appended only the new line, so "alpha"
        # must appear exactly once rather than being re-read. (Line endings
        # differ per platform, so compare content rather than exact bytes.)
        self.assertEqual(tail.text.count("alpha"), 1)
        self.assertEqual(tail.text.count("beta"), 1)
        self.assertLess(tail.text.index("alpha"), tail.text.index("beta"))

    def test_rotation_resets_offset(self):
        tmp = Path(tempfile.mkdtemp())
        logs = tmp / "logs"
        logs.mkdir()
        target = logs / "latest.log"
        target.write_text("x" * 500, encoding="utf-8")
        tail = launcher._LogTail(tmp)
        tail.contains("x")
        target.write_text("fresh start\n", encoding="utf-8")
        self.assertTrue(tail.contains("fresh start"))

    def test_missing_log_dir_is_not_an_error(self):
        tmp = Path(tempfile.mkdtemp())
        tail = launcher._LogTail(tmp)
        self.assertFalse(tail.contains("anything"))


class ArgsFileSelectionTests(unittest.TestCase):
    """The installer writes both args files everywhere; pick by platform.

    Preferring win_args.txt made every Linux run boot the Windows command line
    and fail with "Could not find or load main class", which reads like a
    broken loader but is our own selection bug.
    """

    def test_unix_preferred_when_both_exist(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "win_args.txt").write_text("--windows", encoding="utf-8")
        (tmp / "unix_args.txt").write_text("--unix", encoding="utf-8")
        with mock.patch.object(launcher.os, "name", "posix"):
            picked = launcher._pick_args(tmp, "Forge", "1", tmp)
        self.assertEqual(picked.name, "unix_args.txt")

    def test_windows_preferred_on_nt(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "win_args.txt").write_text("--windows", encoding="utf-8")
        (tmp / "unix_args.txt").write_text("--unix", encoding="utf-8")
        with mock.patch.object(launcher.os, "name", "nt"):
            picked = launcher._pick_args(tmp, "Forge", "1", tmp)
        self.assertEqual(picked.name, "win_args.txt")

    def test_falls_back_when_only_one_exists(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "unix_args.txt").write_text("--unix", encoding="utf-8")
        with mock.patch.object(launcher.os, "name", "nt"):
            picked = launcher._pick_args(tmp, "Forge", "1", tmp)
        self.assertEqual(picked.name, "unix_args.txt")

    def test_missing_both_names_the_directory(self):
        tmp = Path(tempfile.mkdtemp())
        with self.assertRaises(RuntimeError) as ctx:
            launcher._pick_args(tmp, "NeoForge", "26.2.0.88", tmp)
        self.assertIn(str(tmp), str(ctx.exception))


if __name__ == "__main__":
    unittest.main()