import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runtime_monitor import RuntimeMonitor, parse_listeners, parse_process_stat, safe_command


def stat_line(ticks=0, start=100):
    fields = ["S", "1"] + ["0"] * 9 + [str(ticks), "0"] + ["0"] * 6 + [str(start), "0", "20"]
    return "42 (python (worker)) " + " ".join(fields)


class RuntimeMonitorTests(unittest.TestCase):
    def test_stat_names_with_spaces_and_parentheses(self):
        result = parse_process_stat(stat_line(120))
        self.assertEqual(result["name"], "python (worker)")
        self.assertEqual(result["ticks"], 120)
        self.assertEqual(result["startTicks"], 100)
        self.assertEqual(result["rssPages"], 20)

    def test_listeners_ipv6_wildcards_and_multiple_owners(self):
        result = parse_listeners('tcp LISTEN 0 128 [::1]:8765 [::]:* users:(("python",pid=42,fd=3),("python",pid=43,fd=3))\nudp UNCONN 0 0 0.0.0.0:5353 0.0.0.0:*\ntcp LISTEN 0 128 *:3000 *:*\n')
        self.assertEqual(result[0]["scope"], "所有网卡")
        self.assertEqual(result[-1]["address"], "::1")
        self.assertEqual(result[-1]["pids"], [42, 43])
        self.assertEqual(result[-1]["scope"], "本机")

    def test_credentials_are_redacted(self):
        result = safe_command(["python", "server.py", "--api-key=secret-value", "--password", "hunter2", "https://alice:pass@example.com/?access=private", "--port", "8765"])
        for secret in ["secret-value", "hunter2", "alice:pass", "private"]:
            self.assertNotIn(secret, result)
        self.assertIn("8765", result)
        self.assertIn("server.py", result)

    def test_sampling_cache_cpu_pid_reuse_and_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 400 kB\nSwapTotal: 200 kB\nSwapFree: 100 kB\n")
            (root / "stat").write_text("cpu 100 0 0 100 0 0 0 0\n")
            (root / "uptime").write_text("30000 0\n")
            process = root / "42"
            process.mkdir()
            (process / "stat").write_text(stat_line())
            (process / "cmdline").write_bytes(b"python3\0-m\0http.server\08765\0")
            (process / "cwd").symlink_to(temporary)
            monitor = RuntimeMonitor(root)
            with mock.patch("runtime_monitor.shutil.which", return_value="/usr/bin/ss"), mock.patch("runtime_monitor.subprocess.run") as command, mock.patch("runtime_monitor.time.monotonic", side_effect=[100, 101, 102, 104, 106]):
                command.return_value.stdout = 'tcp LISTEN 0 128 127.0.0.1:8765 0.0.0.0:* users:(("python",pid=42,fd=3))'
                first = monitor.snapshot()
                self.assertIsNone(first["processes"][0]["cpuPercent"])
                self.assertEqual(first["processes"][0]["ports"], [8765])
                self.assertTrue(first["processes"][0]["development"])
                self.assertIs(monitor.snapshot(), first)
                self.assertEqual(command.call_count, 1)
                (process / "stat").write_text(stat_line(monitor.hz))
                (root / "stat").write_text("cpu 200 0 0 200 0 0 0 0\n")
                second = monitor.snapshot()
                self.assertEqual(second["processes"][0]["cpuPercent"], 50)
                self.assertEqual(second["cpuPercent"], 50)
                self.assertEqual(second["memoryUsed"], 600 * 1024)
                (process / "stat").write_text(stat_line(monitor.hz, start=200))
                self.assertIsNone(monitor.snapshot()["processes"][0]["cpuPercent"])
                (process / "stat").unlink()
                self.assertEqual(monitor.snapshot()["processes"], [])

    def test_missing_proc_reports_unavailable(self):
        self.assertFalse(RuntimeMonitor(Path("/nonexistent-proc-runtime")).snapshot()["available"])

    def test_real_snapshot_is_current_user_only(self):
        snapshot = RuntimeMonitor().snapshot()
        self.assertTrue(snapshot["available"])
        self.assertIn(os.getpid(), [p["pid"] for p in snapshot["processes"]])
        for process in snapshot["processes"]:
            try:
                self.assertEqual(Path(f'/proc/{process["pid"]}').stat().st_uid, os.getuid())
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
