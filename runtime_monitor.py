"""Read-only Linux runtime snapshots. No agents, persistence, or process control."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path


SECRET = re.compile(r"(?:token|password|passwd|secret|api[-_]?key|authorization|credential)", re.I)
DEVELOPMENT = re.compile(r"(?:python[\d.]*|node|nodejs|uvicorn|gunicorn|pytest|jupyter|vite|webpack|playwright|blender|npm|pnpm|bun|deno)", re.I)


def safe_command(arguments):
    """Do not expose credential arguments, URL credentials, or URL query strings."""
    result, hide_next = [], False
    for argument in arguments:
        if hide_next:
            result.append("[已隐藏]")
            hide_next = False
        elif SECRET.search(argument.split("=", 1)[0]):
            key, separator, _ = argument.partition("=")
            result.append(key + "=[已隐藏]" if separator else key)
            hide_next = not separator
        else:
            argument = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[已隐藏]@", argument)
            argument = re.sub(r"(https?://[^?\s]+)\?\S+", r"\1?[已隐藏]", argument)
            result.append(argument)
    return shlex.join(result)


def parse_process_stat(text):
    # comm is parenthesized and can itself contain spaces and closing parentheses.
    name_end = text.rfind(")")
    fields = text[name_end + 2:].split()
    return {"name": text[text.index("(") + 1:name_end], "state": fields[0],
            "ppid": int(fields[1]), "ticks": int(fields[11]) + int(fields[12]),
            "startTicks": int(fields[19]), "rssPages": int(fields[21])}


def parse_listeners(text):
    listeners = []
    for line in text.splitlines():
        fields = line.split(None, 6)
        if len(fields) < 6:
            continue
        protocol, state, _, _, local, _ = fields[:6]
        host, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        host = host.strip("[]")
        owners = sorted({int(pid) for pid in re.findall(r"pid=(\d+)", fields[6] if len(fields) > 6 else "")})
        scope = "本机" if host == "::1" or host.startswith("127.") else "所有网卡" if host in {"*", "::", "0.0.0.0"} else "指定网卡"
        listeners.append({"protocol": protocol.upper(), "state": state, "address": host,
                          "port": int(port), "pids": owners, "scope": scope})
    return sorted(listeners, key=lambda item: (item["port"], item["protocol"], item["address"]))


class RuntimeMonitor:
    def __init__(self, proc=Path("/proc"), interval=2.0):
        self.proc = Path(proc)
        self.interval = interval
        self.lock = threading.Lock()
        self.cached = None
        self.sampled_at = 0.0
        self.previous_cpu = None
        self.previous_processes = {}
        self.hz = os.sysconf("SC_CLK_TCK")
        self.page_size = os.sysconf("SC_PAGE_SIZE")

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            if self.cached is not None and now - self.sampled_at < self.interval:
                return self.cached
            try:
                result = self._collect(now)
            except (OSError, ValueError) as error:
                return {"available": False, "error": "无法读取本机 Linux 运行状态", "detail": type(error).__name__}
            self.cached = result
            self.sampled_at = now
            return result

    def _collect(self, now):
        memory = {}
        for line in (self.proc / "meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            memory[key] = int(value.split()[0]) * 1024
        cpu = [int(value) for value in (self.proc / "stat").read_text().splitlines()[0].split()[1:9]]
        total, idle = sum(cpu), cpu[3] + cpu[4]
        cpu_percent = None
        if self.previous_cpu:
            delta = total - self.previous_cpu[0]
            if delta > 0:
                cpu_percent = round(100 * (1 - (idle - self.previous_cpu[1]) / delta), 1)
        self.previous_cpu = total, idle
        uptime = float((self.proc / "uptime").read_text().split()[0])
        warnings, listeners = [], []
        if shutil.which("ss"):
            try:
                output = subprocess.run(["ss", "-H", "-lntup"], capture_output=True, text=True, timeout=3, check=True)
                listeners = parse_listeners(output.stdout)
            except (OSError, subprocess.SubprocessError):
                warnings.append("端口采样失败，进程数据仍可查看。")
        else:
            warnings.append("未安装 ss（iproute2），无法列出监听端口。")
        processes, current_ticks = [], {}
        uid = os.getuid()
        for directory in self.proc.iterdir():
            if not directory.name.isdigit():
                continue
            try:
                if directory.stat().st_uid != uid:
                    continue
                pid = int(directory.name)
                stat = parse_process_stat((directory / "stat").read_text())
                arguments = (directory / "cmdline").read_bytes().decode("utf-8", "replace").strip("\0").split("\0")
                if not arguments[0]:
                    continue
                try:
                    cwd = os.readlink(directory / "cwd")
                except OSError:
                    cwd = ""
                identity = (pid, stat["startTicks"])
                previous = self.previous_processes.get(identity)
                usage = None
                if previous is not None and now > self.sampled_at:
                    usage = round(max(0, stat["ticks"] - previous) / self.hz / (now - self.sampled_at) * 100, 1)
                current_ticks[identity] = stat["ticks"]
                development = bool(DEVELOPMENT.fullmatch(stat["name"]) or DEVELOPMENT.fullmatch(Path(arguments[0]).name)
                                   or any(re.search(r"(?:pytest|http\.server|uvicorn|vite|playwright)", arg) for arg in arguments[1:4]))
                ports = sorted({item["port"] for item in listeners if pid in item["pids"]})
                age = max(0, uptime - stat["startTicks"] / self.hz)
                hints = []
                if development:
                    hints.append("开发 / 测试")
                if ports:
                    hints.append("监听端口")
                if development and age >= 6 * 3600:
                    hints.append("运行超过 6 小时")
                if cwd.startswith("/tmp/") or cwd.startswith("/var/tmp/"):
                    hints.append("临时目录")
                processes.append({"pid": pid, "ppid": stat["ppid"], "name": stat["name"],
                                  "command": safe_command(arguments), "cwd": cwd, "state": stat["state"],
                                  "cpuPercent": usage, "memoryBytes": max(0, stat["rssPages"]) * self.page_size,
                                  "ageSeconds": round(age), "startedAt": round((time.time() - age) * 1000),
                                  "development": development, "ports": ports, "hints": hints})
            except (OSError, ValueError, IndexError):
                # Processes can exit during a snapshot; protected processes are skipped.
                continue
        self.previous_processes = current_ticks
        processes.sort(key=lambda item: (bool(item["hints"]), item["cpuPercent"] or 0, item["memoryBytes"]), reverse=True)
        return {"available": True, "sampledAt": round(time.time() * 1000), "hostname": socket.gethostname(),
                "cpuPercent": cpu_percent, "logicalCpus": os.cpu_count(), "uptimeSeconds": round(uptime),
                "memoryTotal": memory["MemTotal"], "memoryUsed": memory["MemTotal"] - memory.get("MemAvailable", memory.get("MemFree", 0)),
                "swapTotal": memory.get("SwapTotal", 0), "swapUsed": memory.get("SwapTotal", 0) - memory.get("SwapFree", 0),
                "processes": processes, "listeners": listeners, "warnings": warnings,
                "scope": "进程仅限当前用户；端口为当前网络命名空间的 TCP 监听 / UDP 绑定，部分系统进程归属不可见。"}
