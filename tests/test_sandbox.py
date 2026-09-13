import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from nightfall import sandbox


class SandboxBackendTests(unittest.TestCase):
    def setUp(self):
        self.project = Path("/tmp/nightfall-project")

    def test_seatbelt_wraps_shell_command(self):
        wrapped = sandbox.SeatbeltBackend(self.project).wrap("printf hello")
        self.assertEqual(wrapped[-2:], ["-c", "printf hello"])
        self.assertEqual(wrapped[0], "sandbox-exec")

    def test_bubblewrap_wraps_with_network_isolation(self):
        wrapped = sandbox.BubblewrapBackend(self.project).wrap("printf hello")
        self.assertIn("--unshare-net", wrapped)
        self.assertIn("--die-with-parent", wrapped)

    def test_unavailable_backend_fails_closed(self):
        with self.assertRaises(sandbox.SandboxUnavailable):
            sandbox.UnavailableBackend().run("echo unsafe")

    def test_windows_backend_reports_missing_native_api(self):
        with patch.object(sandbox.sys, "platform", "win32"):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.WindowsBackend(self.project)

    def test_timeout_is_preserved_by_backend_contract(self):
        class TimeoutBackend(sandbox.Backend):
            def run(self, command, timeout=60):
                raise subprocess.TimeoutExpired(command, timeout)

        with self.assertRaises(subprocess.TimeoutExpired):
            TimeoutBackend().run("sleep 100", timeout=1)


if __name__ == "__main__":
    unittest.main()
