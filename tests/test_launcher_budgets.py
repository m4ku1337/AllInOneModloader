"""Regression tests for the loader's bounded-wait guarantees.

Every case here corresponds to a stall that previously had no upper bound at
all: an installer JVM allowed 30 minutes per attempt, the prefetch loop walked
its URL list serially at 120s per jar, and the HTTP curl fallback re-spent a
full timeout that urllib had already burned. In CI those turned into jobs that
hung until the 6-hour default with nothing in the log to explain why.

These tests deliberately avoid the network: they drive the same code paths with
stubs and assert only on how long the caller is willing to wait.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from http.client import IncompleteRead
from pathlib import Path
from unittest import mock

from aiom.core import http, javart, launcher


class EnvIntTests(unittest.TestCase):
    def test_reads_positive_int(self):
        with mock.patch.dict(os.environ, {"AIOM_X": "300"}, clear=False):
            self.assertEqual(launcher._env_int("AIOM_X", 42), 300)

    def test_falls_back_on_junk(self):
        for junk in ("", "junk", "-5", "0"):
            with mock.patch.dict(os.environ, {"AIOM_X": junk}, clear=False):
                self.assertEqual(launcher._env_int("AIOM_X", 42), 42)

    def test_falls_back_when_absent(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(launcher._env_int("AIOM_MISSING", 42), 42)


class PrefetchBudgetTests(unittest.TestCase):
    """The prefetch pass must answer within its budget, not per-URL serially."""

    def test_many_urls_respect_total_budget(self):
        # 40 unreachable URLs at the old 120s each would be ~80 minutes.
        urls = " ".join(
            f"https://maven.minecraftforge.net/g/a{i}/1.0/a{i}-1.0.jar"
            for i in range(40)
        )
        tmp = Path(tempfile.mkdtemp())
        started = time.time()
        with mock.patch.dict(os.environ, {
            "AIOM_PREFETCH_TIMEOUT": "3", "AIOM_PREFETCH_URL_TIMEOUT": "30",
        }, clear=False), \
                mock.patch.object(launcher.shutil, "which",
                                  return_value="/usr/bin/curl"), \
                mock.patch.object(launcher.subprocess, "run",
                                  return_value=subprocess.CompletedProcess(
                                      [], 1, b"", b"")) as run:
            got = launcher._prefetch(tmp, urls)
        elapsed = time.time() - started

        self.assertEqual(got, 0, "failed downloads must not count as prefetched")
        self.assertLess(elapsed, 20,
                        "prefetch ignored its budget and ran per-URL serially")
        for _args, kwargs in ((c.args, c.kwargs) for c in run.call_args_list):
            cmd = kwargs.get("args") or _args[0]
            self.assertIn("--max-time", cmd)
            self.assertLessEqual(int(cmd[cmd.index("--max-time") + 1]), 30)

    def test_no_curl_means_no_work(self):
        tmp = Path(tempfile.mkdtemp())
        with mock.patch.object(launcher.shutil, "which", return_value=None), \
                mock.patch.object(launcher.subprocess, "run") as run:
            self.assertEqual(launcher._prefetch(tmp, "https://x/y-1.0.jar"), 0)
        run.assert_not_called()

    def test_existing_jar_is_not_refetched(self):
        tmp = Path(tempfile.mkdtemp())
        dest = tmp / "libraries" / "g" / "a" / "1.0" / "a-1.0.jar"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"already here")
        blob = "https://maven.minecraftforge.net/g/a/1.0/a-1.0.jar"
        with mock.patch.object(launcher.shutil, "which",
                               return_value="/usr/bin/curl"), \
                mock.patch.object(launcher.subprocess, "run") as run:
            self.assertEqual(launcher._prefetch(tmp, blob), 0)
        run.assert_not_called()

    def test_successful_download_counts(self):
        tmp = Path(tempfile.mkdtemp())

        def fake_run(cmd, **kwargs):
            # curl -o <dest>: create the file the way the real one would.
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"jar")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        with mock.patch.object(launcher.shutil, "which",
                               return_value="/usr/bin/curl"), \
                mock.patch.object(launcher.subprocess, "run",
                                  side_effect=fake_run):
            got = launcher._prefetch(
                tmp, "https://maven.minecraftforge.net/g/a/1.0/a-1.0.jar")
        self.assertEqual(got, 1)
        self.assertTrue((tmp / "libraries" / "g" / "a" / "1.0" / "a-1.0.jar").exists())


class InstallerTimeoutTests(unittest.TestCase):
    """A stalled installer must surface as a timeout, not an exception storm."""

    def test_timeout_becomes_partial_blob(self):
        tmp = Path(tempfile.mkdtemp())
        exc = subprocess.TimeoutExpired(
            cmd=["java"], timeout=5,
            output="a:b:1.0\nhttps://x/y-1.0.jar\n")
        with mock.patch.object(launcher.javart, "resolve",
                               return_value=(Path("/j"), 25)), \
                mock.patch.object(launcher.subprocess, "run",
                                  side_effect=exc):
            blob = launcher._run_installer_once(
                tmp, str(tmp / "i.jar"), timeout=5)
        # The coordinates printed before the stall are what the caller needs.
        self.assertIn("a:b:1.0", blob)
        self.assertIn("5", blob)

    def test_probe_pass_is_shorter_than_install_pass(self):
        # The whole point of the split: harvesting coordinates should not cost
        # as much as the real install, or CI gains nothing.
        self.assertLess(launcher.PROBE_TIMEOUT, launcher.INSTALL_TIMEOUT)


class HttpFallbackBudgetTests(unittest.TestCase):
    """curl leads because only it can bound a whole transfer."""

    def test_curl_is_tried_first(self):
        with mock.patch.object(http, "_has_curl", return_value=True), \
                mock.patch.object(http.subprocess, "run",
                                  return_value=subprocess.CompletedProcess(
                                      [], 0, b"payload", b"")) as run:
            self.assertEqual(http.fetch_bytes("https://x/y"), b"payload")
        cmd = run.call_args.args[0]
        self.assertEqual(int(cmd[cmd.index("--max-time") + 1]), 300)
        self.assertIsNotNone(run.call_args.kwargs.get("timeout"),
                             "subprocess.run must carry its own timeout")

    def test_urllib_used_when_curl_missing(self):
        resp = mock.MagicMock()
        resp.read.return_value = b"payload"
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        with mock.patch.object(http, "_has_curl", return_value=False), \
                mock.patch.object(http.urllib.request, "urlopen",
                                  return_value=resp) as urlopen:
            self.assertEqual(http.fetch_bytes("https://x/y"), b"payload")
        urlopen.assert_called_once()

    def test_incomplete_read_does_not_escape(self):
        # The bug this whole policy exists for: IncompleteRead is an
        # HTTPException, not an OSError, so it bypassed the handler meant to
        # reach the other transport and killed the run outright.
        resp = mock.MagicMock()
        resp.read.side_effect = IncompleteRead(b"partial")
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        with mock.patch.object(http, "_has_curl", return_value=False), \
                mock.patch.object(http.urllib.request, "urlopen",
                                  return_value=resp):
            with self.assertRaises(IncompleteRead):
                http.fetch_bytes("https://x/y")

    def test_curl_failure_falls_back_to_urllib(self):
        resp = mock.MagicMock()
        resp.read.return_value = b"payload"
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        with mock.patch.object(http, "_has_curl", return_value=True), \
                mock.patch.object(http.subprocess, "run",
                                  side_effect=subprocess.TimeoutExpired(
                                      "curl", 1)), \
                mock.patch.object(http.urllib.request, "urlopen",
                                  return_value=resp):
            self.assertEqual(http.fetch_bytes("https://x/y"), b"payload")

    def test_both_fail_reports_the_curl_error(self):
        """Callers see why the preferred transport gave up, not a red herring."""
        curl_exc = subprocess.CalledProcessError(22, "curl")
        with mock.patch.object(http, "_has_curl", return_value=True), \
                mock.patch.object(http.subprocess, "run",
                                  side_effect=curl_exc), \
                mock.patch.object(http.urllib.request, "urlopen",
                                  side_effect=IncompleteRead(
                                      b"partial")):
            with self.assertRaises(subprocess.CalledProcessError):
                http.fetch_bytes("https://x/y")

    def test_curl_process_has_a_python_side_timeout(self):
        with mock.patch.object(http, "_has_curl", return_value=True), \
                mock.patch.object(http.subprocess, "run",
                                  return_value=subprocess.CompletedProcess(
                                      [], 0, b"ok", b"")) as run:
            http.fetch_bytes("https://x/y", timeout=60)
        self.assertEqual(run.call_args.kwargs["timeout"], 75)


class JavaProbeTests(unittest.TestCase):
    """A stuck `java -version` must not cost a minute per candidate JDK."""

    def test_probe_timeout_is_short(self):
        self.assertLessEqual(javart.PROBE_TIMEOUT, 30)

    def test_stalled_probe_returns_none_quickly(self):
        with mock.patch.object(javart.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("java", 1)):
            started = time.time()
            self.assertIsNone(javart.probe_major(Path("/j/bin/java")))
            self.assertLess(time.time() - started, 5)

    def test_failed_probe_is_not_cached_as_success(self):
        # Only a real answer may be cached; caching a failure would make a
        # later, working JVM look permanently broken.
        with mock.patch.object(javart.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("java", 1)):
            javart.probe_major(Path("/j/bin/java"))
        self.assertNotIn("/j/bin/java", javart._VERSION_CACHE)

    def test_version_is_parsed_and_cached(self):
        java = Path("/jdk25/bin/java")
        resp = subprocess.CompletedProcess([], 0, "", 'openjdk version "25" 2024')
        with mock.patch.object(javart.subprocess, "run", return_value=resp):
            self.assertEqual(javart.probe_major(java), 25)
            javart.probe_major(java)
        self.assertEqual(javart._VERSION_CACHE[str(java)], 25)


if __name__ == "__main__":
    unittest.main()