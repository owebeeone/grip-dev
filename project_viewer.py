from __future__ import annotations

import configparser
import asyncio
import contextlib
import fcntl
import html
import json
import os
import pty
import re
import resource
import secrets
import select
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import graphviz
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse


PORT = 8000
ROOT_KEY = "__root__"
WORKSPACE_ROOT = Path(__file__).resolve().parent
GITMODULES_PATH = WORKSPACE_ROOT / ".gitmodules"
SENTINEL_PATH = WORKSPACE_ROOT / ".project_viewer_server.json"
LOCK_PATH = WORKSPACE_ROOT / ".project_viewer_server.lock"
RUNS_ROOT = WORKSPACE_ROOT / ".project_viewer" / "runs"
SHUTDOWN_TIMEOUT_SECONDS = 4.0
DONE_SENTINEL = "__PROJECT_VIEWER_DONE__"

app = FastAPI()
ACTIVE_RUNS: dict[str, "CommandRun"] = {}


class SingleInstanceServer:
    def __init__(
        self,
        sentinel_path: Path = SENTINEL_PATH,
        lock_path: Path = LOCK_PATH,
        default_port: int = PORT,
    ) -> None:
        self.sentinel_path = sentinel_path
        self.lock_path = lock_path
        self.default_port = default_port
        self.pid = os.getpid()
        self.token = secrets.token_urlsafe(24)
        self.port = default_port

    @contextlib.contextmanager
    def locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def read_sentinel(self) -> dict[str, object] | None:
        if not self.sentinel_path.exists():
            return None
        try:
            return json.loads(self.sentinel_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def write_sentinel(self) -> None:
        payload = {
            "pid": self.pid,
            "port": self.port,
            "token": self.token,
            "started_at": time.time(),
            "script": str(Path(__file__).resolve()),
        }
        self.sentinel_path.write_text(json.dumps(payload, indent=2) + "\n")

    def cleanup_sentinel(self) -> None:
        with self.locked():
            current = self.read_sentinel()
            if current and current.get("pid") == self.pid:
                self.sentinel_path.unlink(missing_ok=True)

    @staticmethod
    def pid_is_running(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def port_is_available(port: int) -> bool:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                return False
        return True

    @staticmethod
    def find_available_port(start_port: int) -> int:
        for port in range(start_port, start_port + 100):
            if SingleInstanceServer.port_is_available(port):
                return port
        raise RuntimeError(f"No available port found from {start_port} to {start_port + 99}")

    def request_shutdown(self, port: int, token: str) -> None:
        url = f"http://127.0.0.1:{port}/__project_viewer_shutdown?token={token}"
        request = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(request, timeout=1.0):
            pass

    def terminate_pid(self, pid: int) -> None:
        if pid == self.pid or not self.pid_is_running(pid):
            return
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)

    def wait_for_exit_or_port(self, pid: int, port: int, timeout: float = SHUTDOWN_TIMEOUT_SECONDS) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.pid_is_running(pid) or self.port_is_available(port):
                return True
            time.sleep(0.1)
        return not self.pid_is_running(pid) or self.port_is_available(port)

    def stop_previous(self, previous: dict[str, object]) -> int:
        previous_pid = int(previous.get("pid") or 0)
        previous_port = int(previous.get("port") or self.default_port)
        token = str(previous.get("token") or "")

        if previous_pid == self.pid or not self.pid_is_running(previous_pid):
            return previous_port

        if token:
            with contextlib.suppress(OSError, urllib.error.URLError, TimeoutError):
                self.request_shutdown(previous_port, token)

        if self.wait_for_exit_or_port(previous_pid, previous_port):
            return previous_port

        self.terminate_pid(previous_pid)
        self.wait_for_exit_or_port(previous_pid, previous_port)
        return previous_port

    async def prepare(self) -> int:
        def prepare_sync() -> int:
            with self.locked():
                previous = self.read_sentinel()
                preferred_port = self.default_port
                if previous:
                    preferred_port = self.stop_previous(previous)

                self.port = (
                    preferred_port
                    if self.port_is_available(preferred_port)
                    else self.find_available_port(preferred_port)
                )
                self.write_sentinel()
                return self.port

        return await asyncio.to_thread(prepare_sync)


class CommandRun:
    def __init__(self, repo_key: str, cwd: Path, argv: list[str], loop: asyncio.AbstractEventLoop) -> None:
        self.repo_key = repo_key
        self.cwd = cwd
        self.argv = argv
        self.loop = loop
        self.run_id = self.make_run_id(repo_key, argv)
        self.run_dir = RUNS_ROOT / self.safe_name(repo_key) / self.run_id
        self.meta_path = self.run_dir / "meta.yaml"
        self.log_path = self.run_dir / "output.log"
        self.process: subprocess.Popen[bytes] | None = None
        self.master_fd: int | None = None
        self.status = "created"
        self.exit_code: int | None = None
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.ended_at: str | None = None
        self.started_monotonic: float | None = None
        self.start_usage: resource.struct_rusage | None = None
        self.elapsed_seconds: float | None = None
        self.user_seconds: float | None = None
        self.system_seconds: float | None = None
        self.cpu_percent: float | None = None
        self.subscribers: set[asyncio.Queue[str]] = set()

    @staticmethod
    def safe_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "run"

    @classmethod
    def make_run_id(cls, repo_key: str, argv: list[str]) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        action = cls.safe_name("-".join(argv[:2]))
        return f"{stamp}-{cls.safe_name(repo_key)}-{action}-{secrets.token_hex(3)}"

    def write_meta(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            f"id: {self.run_id}",
            f"repo: {self.repo_key}",
            f"cwd: {self.cwd.relative_to(WORKSPACE_ROOT) if self.cwd.is_relative_to(WORKSPACE_ROOT) else self.cwd}",
            "command:",
            *[f"  - {json.dumps(part)}" for part in self.argv],
            f"status: {self.status}",
            f"pid: {self.process.pid if self.process else ''}",
            f"started_at: {json.dumps(self.started_at)}",
            f"ended_at: {json.dumps(self.ended_at) if self.ended_at else ''}",
            f"exit_code: {self.exit_code if self.exit_code is not None else ''}",
            f"elapsed_seconds: {self.elapsed_seconds if self.elapsed_seconds is not None else ''}",
            f"user_seconds: {self.user_seconds if self.user_seconds is not None else ''}",
            f"system_seconds: {self.system_seconds if self.system_seconds is not None else ''}",
            f"cpu_percent: {self.cpu_percent if self.cpu_percent is not None else ''}",
            f"log: {self.log_path.relative_to(WORKSPACE_ROOT)}",
        ]
        self.meta_path.write_text("\n".join(lines) + "\n")

    def append_log(self, text: str) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", errors="replace") as log_file:
            log_file.write(text)
            log_file.flush()
        for queue in list(self.subscribers):
            self.loop.call_soon_threadsafe(queue.put_nowait, text)

    def start(self) -> None:
        self.status = "running"
        self.started_monotonic = time.monotonic()
        self.start_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.write_meta()
        self.append_log(f"$ {' '.join(self.argv)}\n")
        self.append_log(f"cwd: {self.cwd.relative_to(WORKSPACE_ROOT)}\nstarted_at: {self.started_at}\n\n")

        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd
        try:
            self.process = subprocess.Popen(
                self.argv,
                cwd=self.cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                start_new_session=True,
            )
        finally:
            os.close(slave_fd)
        self.write_meta()
        threading.Thread(target=self._reader, name=f"project-viewer-{self.run_id}", daemon=True).start()

    def _reader(self) -> None:
        assert self.process is not None
        assert self.master_fd is not None
        try:
            while True:
                ready, _, _ = select.select([self.master_fd], [], [], 0.2)
                if ready:
                    try:
                        data = os.read(self.master_fd, 4096)
                    except OSError:
                        break
                    if not data:
                        break
                    self.append_log(data.decode(errors="replace"))
                if self.process.poll() is not None and not ready:
                    break
        finally:
            self.exit_code = self.process.wait()
            self.status = "done" if self.exit_code == 0 else "failed"
            self.ended_at = datetime.now(timezone.utc).isoformat()
            self.record_usage()
            self.append_log(
                "\n"
                f"{DONE_SENTINEL} exit_code={self.exit_code} "
                f"elapsed={self.elapsed_seconds:.2f}s "
                f"user={self.user_seconds:.2f}s "
                f"system={self.system_seconds:.2f}s "
                f"cpu={self.cpu_percent:.0f}%\n"
            )
            self.write_meta()
            if self.master_fd is not None:
                with contextlib.suppress(OSError):
                    os.close(self.master_fd)

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self.subscribers.discard(queue)

    def send_signal(self, signum: int) -> None:
        if not self.process or self.process.poll() is not None:
            return
        os.killpg(self.process.pid, signum)

    def record_usage(self) -> None:
        if self.started_monotonic is None or self.start_usage is None:
            return
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.elapsed_seconds = max(time.monotonic() - self.started_monotonic, 0.001)
        self.user_seconds = max(usage.ru_utime - self.start_usage.ru_utime, 0.0)
        self.system_seconds = max(usage.ru_stime - self.start_usage.ru_stime, 0.0)
        self.cpu_percent = ((self.user_seconds + self.system_seconds) / self.elapsed_seconds) * 100

    def payload(self) -> dict[str, object]:
        return {
            "id": self.run_id,
            "repo": self.repo_key,
            "command": self.argv,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "elapsed_seconds": self.elapsed_seconds,
            "log_url": f"/api/runs/{self.run_id}/log",
            "stream_url": f"/api/runs/{self.run_id}/stream",
        }


RELATIONSHIPS = [
    ("astichi", "yidl"),
    ("yidl", "yidl-lifecycle"),
    ("yidl-lifecycle", "pyrolyze"),
    ("pyrolyze", "grip-py-demo"),
    ("grip-py", "grip-py-demo"),
    ("grip-py", "grip-pyrolyze"),
    ("pyrolyze", "grip-pyrolyze"),
    ("grip-pyrolyze", "grip-pyrolyze-examples"),
    ("grip-core", "grip-react"),
    ("grip-react", "grip-react-demo"),
    ("grip-core", "grip-vue"),
    ("grip-vue", "grip-vue-demo"),
]


STATUS_STYLES = {
    "clean": {"fillcolor": "#dcfce7", "color": "#16a34a"},
    "dirty": {"fillcolor": "#fef3c7", "color": "#d97706"},
    "unavailable": {"fillcolor": "#e5e7eb", "color": "#6b7280"},
}


def github_url(remote_url: str) -> str:
    if remote_url.startswith("git@github.com:"):
        path = remote_url.removeprefix("git@github.com:").removesuffix(".git")
        return f"https://github.com/{path}"
    return remote_url.removesuffix(".git")


def git_remote_url(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "config", "--get", "remote.origin.url"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return github_url(result.stdout.strip())
    return ""


def read_submodule_paths() -> dict[str, dict[str, str]]:
    parser = configparser.ConfigParser()
    parser.read(GITMODULES_PATH)

    modules: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        if not section.startswith("submodule "):
            continue
        name = section.removeprefix("submodule ").strip('"')
        path = parser.get(section, "path")
        url = parser.get(section, "url")
        modules[name] = {
            "key": name,
            "name": name,
            "path": path,
            "url": github_url(url),
            "remote_url": url,
        }
    return modules


def first_regex(path: Path, pattern: str) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(errors="replace")
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def read_description(repo_path: Path) -> tuple[str, str]:
    description = first_regex(repo_path / "pyproject.toml", r'^\s*description\s*=\s*["\']([^"\']+)["\']')
    if description:
        return description, "pyproject.toml"

    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            value = json.loads(package_json.read_text()).get("description")
        except json.JSONDecodeError:
            value = None
        if value:
            return str(value), "package.json"

    for readme_name in ("README.md", "README.rst", "README.txt"):
        readme = repo_path / readme_name
        if readme.exists():
            for line in readme.read_text(errors="replace").splitlines():
                cleaned = line.strip(" #=\t")
                if cleaned:
                    return cleaned[:220], readme_name

    return "No project description found in pyproject.toml, package.json, or README.", "fallback"


def read_version(repo_path: Path) -> tuple[str | None, str | None]:
    version = first_regex(repo_path / "pyproject.toml", r'^\s*version\s*=\s*["\']([^"\']+)["\']')
    if version:
        return version, "pyproject.toml"

    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            value = json.loads(package_json.read_text()).get("version")
        except json.JSONDecodeError:
            value = None
        if value:
            return str(value), "package.json"

    return None, None


def git_status(repo_path: Path) -> dict[str, object]:
    if not repo_path.exists():
        return {
            "state": "unavailable",
            "label": "Unavailable",
            "summary": "Submodule path is missing.",
            "details": [],
        }

    result = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {
            "state": "unavailable",
            "label": "Unavailable",
            "summary": "Could not read git status.",
            "details": [result.stderr.strip()],
        }

    lines = [line for line in result.stdout.splitlines() if line]
    if not lines:
        return {
            "state": "clean",
            "label": "Clean",
            "summary": "All checked in.",
            "details": [],
        }

    untracked = sum(1 for line in lines if line.startswith("??"))
    changed = len(lines) - untracked
    parts = []
    if changed:
        parts.append(f"{changed} changed")
    if untracked:
        parts.append(f"{untracked} untracked")

    return {
        "state": "dirty",
        "label": "Local changes",
        "summary": ", ".join(parts),
        "details": lines[:12],
    }


def read_submodules() -> dict[str, dict[str, object]]:
    modules = read_submodule_paths()
    for name, info in modules.items():
        repo_path = WORKSPACE_ROOT / str(info["path"])
        description, source = read_description(repo_path)
        version, version_source = read_version(repo_path)
        info["description"] = description
        info["description_source"] = source
        info["version"] = version
        info["version_source"] = version_source
        info["status"] = git_status(repo_path)
    return modules


def read_root_repo_info() -> dict[str, object]:
    description, source = read_description(WORKSPACE_ROOT)
    version, version_source = read_version(WORKSPACE_ROOT)
    return {
        "key": ROOT_KEY,
        "name": WORKSPACE_ROOT.name,
        "path": ".",
        "url": git_remote_url(WORKSPACE_ROOT),
        "remote_url": git_remote_url(WORKSPACE_ROOT),
        "description": description,
        "description_source": source,
        "version": version,
        "version_source": version_source,
        "status": git_status(WORKSPACE_ROOT),
    }


def add_node(dot: graphviz.Digraph, key: str, modules: dict[str, dict[str, object]]) -> None:
    info = modules[key]
    status = info["status"]
    assert isinstance(status, dict)
    style = STATUS_STYLES.get(str(status["state"]), STATUS_STYLES["unavailable"])
    dot.node(
        key,
        str(info["name"]),
        _attributes={
            "fillcolor": style["fillcolor"],
            "color": style["color"],
        },
    )


def generate_graphviz_svg(modules: dict[str, dict[str, object]]) -> str:
    dot = graphviz.Digraph(
        "grip_pyrolyze_dev",
        graph_attr={
            "rankdir": "LR",
            "bgcolor": "transparent",
            "compound": "true",
            "nodesep": "0.55",
            "ranksep": "0.85",
            "splines": "curved",
        },
        node_attr={
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "#f8fafc",
            "color": "#334155",
            "fontname": "Helvetica",
            "fontsize": "12",
            "margin": "0.12,0.08",
        },
        edge_attr={"color": "#64748b", "arrowsize": "0.75", "penwidth": "1.4"},
    )

    with dot.subgraph(name="cluster_core") as c:
        c.attr(label="Core Libraries", style="rounded,filled", fillcolor="#e0f2fe", color="#7dd3fc")
        for key in ("astichi", "yidl", "yidl-lifecycle", "pyrolyze"):
            if key in modules:
                add_node(c, key, modules)

    with dot.subgraph(name="cluster_grip_framework") as c:
        c.attr(label="GRIP Framework", style="rounded,filled", fillcolor="#ede9fe", color="#c4b5fd")
        if "grip-core" in modules:
            add_node(c, "grip-core", modules)

    with dot.subgraph(name="cluster_grip_python") as c:
        c.attr(label="GRIP Python Ecosystem", style="rounded,filled", fillcolor="#dcfce7", color="#86efac")
        for key in ("grip-py", "grip-py-demo", "grip-pyrolyze", "grip-pyrolyze-examples"):
            if key in modules:
                add_node(c, key, modules)

    with dot.subgraph(name="cluster_grip_frontend") as c:
        c.attr(label="GRIP Frontend Ecosystem", style="rounded,filled", fillcolor="#ffedd5", color="#fdba74")
        for key in ("grip-react", "grip-react-demo", "grip-vue", "grip-vue-demo"):
            if key in modules:
                add_node(c, key, modules)

    for source, target in RELATIONSHIPS:
        if source in modules and target in modules:
            dot.edge(source, target)

    return annotate_svg(dot.pipe(format="svg").decode("utf-8"))


NODE_TITLE_RE = re.compile(r'(<g id="node\d+" class="node")>\s*<title>([^<]+)</title>')


def annotate_svg(svg: str) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix, node_id = match.groups()
        node_id = html.unescape(node_id)
        escaped = html.escape(node_id, quote=True)
        return f'{prefix} data-node-id="{escaped}">\n'

    svg = re.sub(r"<\?xml[^>]*>\s*", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg)
    return NODE_TITLE_RE.sub(replace, svg)


HTML_TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>grip-pyrolyze-dev Submodule Infographic</title>
  <style>
    body {
      margin: 0;
      padding: 28px;
      background: #f1f5f9;
      color: #0f172a;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    h1 { margin: 0 0 8px; text-align: center; color: #0f4c81; }
    .intro { text-align: center; color: #475569; margin: 0 0 22px; }
    .toolbar {
      display: flex;
      justify-content: center;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 18px;
      color: #475569;
      font-size: 13px;
    }
    .toolbar button {
      padding: 8px 12px;
      border: 1px solid #94a3b8;
      border-radius: 10px;
      background: white;
      color: #0f172a;
      cursor: pointer;
      font-weight: 600;
    }
    .toolbar button[data-node-id] {
      border-width: 2px;
    }
    .toolbar button[data-status-state="clean"] {
      border-color: #16a34a;
      background: #f0fdf4;
    }
    .toolbar button[data-status-state="dirty"] {
      border-color: #d97706;
      background: #fffbeb;
    }
    .toolbar button[data-status-state="unavailable"] {
      border-color: #6b7280;
      background: #f9fafb;
    }
    .legend {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .legend span { display: inline-flex; align-items: center; gap: 5px; }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 999px;
      border: 1px solid currentColor;
    }
    .clean { color: #16a34a; }
    .dirty { color: #d97706; }
    .unavailable { color: #6b7280; }
    #graph-container {
      max-width: 96vw;
      margin: 0 auto;
      padding: 22px;
      overflow: auto;
      border: 1px solid #cbd5e1;
      border-radius: 18px;
      background: white;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.10);
    }
    #graph-container svg { max-width: none; height: auto; }
    g.node[data-node-id] polygon {
      cursor: pointer;
      transition: filter 120ms ease, stroke-width 120ms ease;
    }
    g.node[data-node-id]:hover polygon {
      filter: drop-shadow(0 2px 4px rgba(15, 23, 42, 0.25));
      stroke-width: 2px;
    }
    #tooltip, #repo-menu {
      position: absolute;
      z-index: 50;
      max-width: 360px;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.22);
      text-align: left;
    }
    #tooltip {
      display: none;
      padding: 10px 12px;
      background: rgba(15, 23, 42, 0.92);
      color: #f8fafc;
      font-size: 13px;
      line-height: 1.35;
      pointer-events: none;
    }
    #tooltip strong { color: #fde68a; display: block; margin-bottom: 4px; }
    #tooltip .meta { color: #cbd5e1; display: block; margin-top: 6px; font-size: 12px; }
    #repo-menu {
      display: none;
      min-width: 270px;
      padding: 12px;
      background: white;
      border: 1px solid #cbd5e1;
      color: #0f172a;
    }
    #repo-menu h2 { margin: 0 0 6px; font-size: 16px; }
    #repo-menu p { margin: 0 0 10px; color: #475569; font-size: 13px; line-height: 1.35; }
    #repo-menu dl { margin: 0 0 10px; font-size: 12px; color: #475569; }
    #repo-menu dt { font-weight: 700; color: #334155; }
    #repo-menu dd { margin: 0 0 6px; }
    #repo-menu pre {
      max-height: 140px;
      overflow: auto;
      padding: 8px;
      border-radius: 8px;
      background: #f8fafc;
      color: #334155;
      font-size: 11px;
      white-space: pre-wrap;
    }
    #repo-menu a {
      display: inline-block;
      padding: 7px 10px;
      border-radius: 8px;
      background: #0f4c81;
      color: white;
      text-decoration: none;
      font-size: 13px;
    }
    #repo-menu button {
      display: inline-block;
      margin-left: 8px;
      padding: 7px 10px;
      border: 0;
      border-radius: 8px;
      background: #334155;
      color: white;
      cursor: pointer;
      font-size: 13px;
    }
    #terminal-panel {
      display: none;
      max-width: 96vw;
      margin: 18px auto 0;
      border: 1px solid #1e293b;
      border-radius: 14px;
      overflow: hidden;
      background: #020617;
      color: #e2e8f0;
      box-shadow: 0 12px 30px rgba(15, 23, 42, 0.20);
    }
    #terminal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 10px 12px;
      background: #0f172a;
      font-size: 13px;
    }
    #terminal-header button {
      padding: 5px 9px;
      border: 1px solid #64748b;
      border-radius: 8px;
      background: #1e293b;
      color: #e2e8f0;
      cursor: pointer;
    }
    #terminal-header button:disabled {
      cursor: not-allowed;
      opacity: 0.45;
    }
    #terminal-output {
      margin: 0;
      max-height: 360px;
      overflow: auto;
      padding: 12px;
      white-space: pre-wrap;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    #sessions-panel {
      max-width: 96vw;
      margin: 18px auto 0;
      padding: 16px;
      border: 1px solid #cbd5e1;
      border-radius: 16px;
      background: white;
    }
    #sessions-panel h2 { margin: 0 0 12px; font-size: 16px; }
    #batch-controls { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; }
    #batch-controls button {
      padding: 7px 10px;
      border: 1px solid #94a3b8;
      border-radius: 9px;
      background: #f8fafc;
      cursor: pointer;
    }
    #batch-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .run-card {
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      padding: 10px;
      background: #f8fafc;
      cursor: pointer;
      min-height: 86px;
    }
    .run-card.running { border-color: #2563eb; }
    .run-card.done { border-color: #16a34a; }
    .run-card.failed { border-color: #dc2626; }
    .run-card strong { display: block; margin-bottom: 4px; }
    .run-card code { color: #475569; font-size: 12px; }
    #sessions-list {
      max-height: 220px;
      overflow: auto;
      border-top: 1px solid #e2e8f0;
      padding-top: 10px;
    }
    .session-row {
      display: grid;
      grid-template-columns: 1.1fr 1.6fr 0.7fr 0.7fr;
      gap: 8px;
      padding: 7px 4px;
      border-bottom: 1px solid #f1f5f9;
      cursor: pointer;
      font-size: 12px;
    }
    .session-row:hover { background: #f8fafc; }
  </style>
</head>
<body>
  <h1>grip-pyrolyze-dev Submodule Relationships</h1>
  <p class="intro">Hover for repo information. Click a node for actions. Status is recomputed on each refresh.</p>
  <div class="toolbar">
    <button type="button" onclick="window.location.reload()">Refresh project view</button>
    <button
      id="root-status-button"
      type="button"
      data-node-id="__root__"
      data-status-state="__ROOT_STATUS_STATE__"
    >Root repo status</button>
    <div class="legend" aria-label="Git status legend">
      <span class="clean"><span class="swatch"></span>Clean</span>
      <span class="dirty"><span class="swatch"></span>Local changes</span>
      <span class="unavailable"><span class="swatch"></span>Unavailable</span>
    </div>
  </div>
  <div id="graph-container">__GRAPH_SVG__</div>
  <section id="terminal-panel" aria-live="polite">
    <div id="terminal-header">
      <strong id="terminal-title">Command session</strong>
      <span>
        <button id="interrupt-run" type="button" disabled>Interrupt</button>
        <button id="close-terminal" type="button">Close</button>
      </span>
    </div>
    <pre id="terminal-output"></pre>
  </section>
  <section id="sessions-panel">
    <h2>Command Sessions</h2>
    <div id="batch-controls">
      <button id="git-branch-all" type="button">Git branch: all repos</button>
      <button id="refresh-sessions" type="button">Refresh sessions</button>
    </div>
    <div id="batch-grid"></div>
    <div id="sessions-list"></div>
  </section>
  <div id="tooltip"></div>
  <div id="repo-menu" role="menu" aria-hidden="true"></div>
  <script>
    const submoduleInfo = __SUBMODULE_DATA__;
    const graphContainer = document.getElementById("graph-container");
    const rootButton = document.getElementById("root-status-button");
    const tooltip = document.getElementById("tooltip");
    const menu = document.getElementById("repo-menu");
    const terminalPanel = document.getElementById("terminal-panel");
    const terminalTitle = document.getElementById("terminal-title");
    const terminalOutput = document.getElementById("terminal-output");
    const interruptButton = document.getElementById("interrupt-run");
    const closeTerminalButton = document.getElementById("close-terminal");
    const gitBranchAllButton = document.getElementById("git-branch-all");
    const refreshSessionsButton = document.getElementById("refresh-sessions");
    const sessionsList = document.getElementById("sessions-list");
    const batchGrid = document.getElementById("batch-grid");
    let activeRunId = null;
    let activeSocket = null;

    function nodeFromEvent(event) {
      return event.target.closest("[data-node-id]");
    }

    function showTooltip(info, event) {
      const version = info.version ? `Version ${info.version}` : "Version not found";
      tooltip.innerHTML = `
        <strong>${info.name}</strong>
        ${info.description}
        <span class="meta">${version}</span>
        <span class="meta">${info.status.label}: ${info.status.summary}</span>
      `;
      tooltip.style.left = `${event.pageX + 12}px`;
      tooltip.style.top = `${event.pageY + 12}px`;
      tooltip.style.display = "block";
    }

    function showMenu(info, event) {
      const details = info.status.details?.length
        ? `<pre>${info.status.details.join("\n")}</pre>`
        : "";
      menu.innerHTML = `
        <h2>${info.name}</h2>
        <p>${info.description}</p>
        <dl>
          <dt>Path</dt><dd>${info.path}</dd>
          <dt>Status</dt><dd>${info.status.label}: ${info.status.summary}</dd>
          <dt>Version</dt><dd>${info.version || "Not found"}</dd>
          <dt>Version source</dt><dd>${info.version_source || "n/a"}</dd>
          <dt>Description source</dt><dd>${info.description_source}</dd>
        </dl>
        ${details}
        <a href="${info.url}" target="_blank" rel="noopener noreferrer">Open GitHub</a>
        <button type="button" data-action="git-pull" data-node-id="${info.key}">Git pull</button>
      `;
      menu.style.left = "0px";
      menu.style.top = "0px";
      menu.style.visibility = "hidden";
      menu.style.display = "block";
      menu.setAttribute("aria-hidden", "false");

      const margin = 12;
      const rect = menu.getBoundingClientRect();
      let left = event.pageX + margin;
      let top = event.pageY + margin;

      if (event.clientX + rect.width + margin > window.innerWidth) {
        left = event.pageX - rect.width - margin;
      }
      if (event.clientY + rect.height + margin > window.innerHeight) {
        top = event.pageY - rect.height - margin;
      }

      menu.style.left = `${Math.max(window.scrollX + margin, left)}px`;
      menu.style.top = `${Math.max(window.scrollY + margin, top)}px`;
      menu.style.visibility = "visible";
    }

    function hideMenu() {
      menu.style.display = "none";
      menu.style.visibility = "hidden";
      menu.setAttribute("aria-hidden", "true");
    }

    function handleInfoMove(event) {
      const node = nodeFromEvent(event);
      if (!node) {
        tooltip.style.display = "none";
        return;
      }
      const info = submoduleInfo[node.dataset.nodeId];
      if (info) showTooltip(info, event);
    }

    function handleInfoLeave() {
      tooltip.style.display = "none";
    }

    function handleInfoClick(event) {
      const node = nodeFromEvent(event);
      if (!node) return;
      event.preventDefault();
      event.stopPropagation();
      tooltip.style.display = "none";
      const info = submoduleInfo[node.dataset.nodeId];
      if (info) showMenu(info, event);
    }

    graphContainer.addEventListener("mousemove", handleInfoMove);
    graphContainer.addEventListener("mouseleave", handleInfoLeave);
    graphContainer.addEventListener("click", handleInfoClick);
    rootButton.addEventListener("mousemove", handleInfoMove);
    rootButton.addEventListener("mouseleave", handleInfoLeave);
    rootButton.addEventListener("click", handleInfoClick);

    document.addEventListener("click", (event) => {
      if (!menu.contains(event.target)) hideMenu();
    });

    menu.addEventListener("click", async (event) => {
      const actionButton = event.target.closest("button[data-action='git-pull']");
      if (!actionButton) return;
      event.preventDefault();
      event.stopPropagation();
      const info = submoduleInfo[actionButton.dataset.nodeId];
      if (info) await startGitPull(info);
    });

    async function startGitPull(info) {
      hideMenu();
      openTerminal(`${info.name}: git pull --ff-only`, "Starting git pull...\\n");

      const response = await fetch(`/api/runs/git-pull/${encodeURIComponent(info.key)}`, { method: "POST" });
      if (!response.ok) {
        terminalOutput.textContent += `Failed to start run: ${response.status} ${response.statusText}\\n`;
        return;
      }

      const run = await response.json();
      connectRun(run.run_id, run.stream_url, false);
    }

    function openTerminal(title, initialText = "") {
      terminalPanel.style.display = "block";
      terminalTitle.textContent = title;
      terminalOutput.textContent = initialText;
    }

    function setInterruptEnabled(enabled) {
      interruptButton.disabled = !enabled;
    }

    function connectRun(runId, streamUrl, append = false) {
      activeRunId = runId;
      if (activeSocket) activeSocket.close();
      if (!append) terminalOutput.textContent = terminalOutput.textContent || "";
      setInterruptEnabled(true);
      activeSocket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${streamUrl}`);
      activeSocket.onmessage = (message) => {
        const payload = JSON.parse(message.data);
        if (payload.type === "output") {
          terminalOutput.textContent += payload.text;
          terminalOutput.scrollTop = terminalOutput.scrollHeight;
        }
        if (payload.type === "done") {
          terminalOutput.textContent += `\\n[project-viewer] run finished with exit code ${payload.exit_code}\\n`;
          terminalOutput.scrollTop = terminalOutput.scrollHeight;
          setInterruptEnabled(false);
        }
        if (payload.type === "error") {
          terminalOutput.textContent += `\\n[project-viewer] ${payload.message}\\n`;
          setInterruptEnabled(false);
        }
      };
      activeSocket.onerror = () => {
        terminalOutput.textContent += "\\n[project-viewer] websocket error\\n";
        setInterruptEnabled(false);
      };
      activeSocket.onclose = () => {
        setInterruptEnabled(false);
      };
    }

    async function loadRunLog(run) {
      openTerminal(`${run.repo}: ${(run.command || []).join(" ")}`, "Loading log...\\n");
      const response = await fetch(run.log_url);
      const payload = await response.json();
      terminalOutput.textContent = payload.log;
      if (run.status === "running" && run.stream_url) {
        connectRun(run.id, run.stream_url, true);
      } else {
        setInterruptEnabled(false);
      }
    }

    function renderRunCard(run) {
      const command = (run.command || []).join(" ");
      const card = document.createElement("div");
      card.className = `run-card ${run.status || ""}`;
      card.dataset.runId = run.id;
      card.innerHTML = `
        <strong>${run.repo}</strong>
        <div>${run.status || "unknown"} ${run.exit_code ? `(${run.exit_code})` : ""}</div>
        <code>${command}</code>
      `;
      card.addEventListener("click", () => loadRunLog(run));
      return card;
    }

    async function refreshSessions() {
      const response = await fetch("/api/runs");
      const payload = await response.json();
      const runs = payload.runs || [];
      sessionsList.innerHTML = "";
      for (const run of runs.slice(0, 30)) {
        const row = document.createElement("div");
        row.className = "session-row";
        row.innerHTML = `
          <span>${run.repo || ""}</span>
          <span>${(run.command || []).join(" ")}</span>
          <span>${run.status || ""}</span>
          <span>${run.exit_code || ""}</span>
        `;
        row.addEventListener("click", () => loadRunLog(run));
        sessionsList.appendChild(row);
      }
    }

    async function startGitBranchAll() {
      batchGrid.innerHTML = "";
      const response = await fetch("/api/runs/git-branch-all", { method: "POST" });
      const payload = await response.json();
      for (const run of payload.runs || []) {
        batchGrid.appendChild(renderRunCard(run));
        const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${run.stream_url}`);
        let lastOutput = "";
        const card = batchGrid.lastElementChild;
        socket.onmessage = (message) => {
          const event = JSON.parse(message.data);
          if (event.type === "output") {
            lastOutput = event.text.trim().split("\\n").slice(-1)[0] || lastOutput;
            card.querySelector("div").textContent = lastOutput || "running";
          }
          if (event.type === "done") {
            card.classList.remove("running");
            card.classList.add(event.exit_code === 0 ? "done" : "failed");
            card.querySelector("div").textContent = `exit ${event.exit_code}: ${lastOutput}`;
          }
        };
      }
      refreshSessions();
    }

    interruptButton.addEventListener("click", async () => {
      if (!activeRunId) return;
      await fetch(`/api/runs/${encodeURIComponent(activeRunId)}/interrupt`, { method: "POST" });
    });

    closeTerminalButton.addEventListener("click", () => {
      terminalPanel.style.display = "none";
    });

    gitBranchAllButton.addEventListener("click", startGitBranchAll);
    refreshSessionsButton.addEventListener("click", refreshSessions);
    refreshSessions();

    console.log("INFO graph ready", {
      nodes: document.querySelectorAll("g.node[data-node-id]").length,
      repos: Object.keys(submoduleInfo).length,
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def read_root() -> HTMLResponse:
    submodules = read_submodules()
    root_info = read_root_repo_info()
    root_status = root_info["status"]
    assert isinstance(root_status, dict)
    view_info = {ROOT_KEY: root_info, **submodules}
    content = (
        HTML_TEMPLATE
        .replace("__GRAPH_SVG__", generate_graphviz_svg(submodules))
        .replace("__SUBMODULE_DATA__", json.dumps(view_info))
        .replace("__ROOT_STATUS_STATE__", str(root_status["state"]))
    )
    return HTMLResponse(content=content)


def repo_cwd(repo_key: str) -> Path:
    if repo_key == ROOT_KEY:
        return WORKSPACE_ROOT
    modules = read_submodule_paths()
    if repo_key not in modules:
        raise HTTPException(status_code=404, detail=f"Unknown repository: {repo_key}")
    path = WORKSPACE_ROOT / modules[repo_key]["path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Repository path is missing: {repo_key}")
    return path


def repo_keys(include_root: bool = True) -> list[str]:
    keys = sorted(read_submodule_paths())
    return ([ROOT_KEY] if include_root else []) + keys


def parse_meta_file(path: Path) -> dict[str, object]:
    data: dict[str, object] = {"id": path.parent.name, "log_url": f"/api/runs/{path.parent.name}/log"}
    command: list[str] = []
    in_command = False
    for line in path.read_text(errors="replace").splitlines():
        if line == "command:":
            in_command = True
            continue
        if in_command and line.startswith("  - "):
            with contextlib.suppress(json.JSONDecodeError):
                command.append(json.loads(line[4:]))
            continue
        in_command = False
        if ": " in line:
            key, value = line.split(": ", 1)
            data[key] = value.strip().strip('"')
    data["command"] = command
    return data


def recent_runs(limit: int = 50) -> list[dict[str, object]]:
    metas = sorted(RUNS_ROOT.glob("*/*/meta.yaml"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [parse_meta_file(path) for path in metas[:limit]]


@app.post("/api/runs/git-pull/{repo_key:path}")
async def start_git_pull(repo_key: str) -> dict[str, str]:
    cwd = repo_cwd(repo_key)
    run = CommandRun(repo_key=repo_key, cwd=cwd, argv=["git", "pull", "--ff-only"], loop=asyncio.get_running_loop())
    ACTIVE_RUNS[run.run_id] = run
    run.start()
    return {
        "run_id": run.run_id,
        "status": run.status,
        "stream_url": f"/api/runs/{run.run_id}/stream",
        "log_url": f"/api/runs/{run.run_id}/log",
    }


@app.post("/api/runs/git-branch-all")
async def start_git_branch_all() -> dict[str, object]:
    runs: list[dict[str, object]] = []
    loop = asyncio.get_running_loop()
    for repo_key in repo_keys(include_root=True):
        cwd = repo_cwd(repo_key)
        run = CommandRun(repo_key=repo_key, cwd=cwd, argv=["git", "branch", "--show-current"], loop=loop)
        ACTIVE_RUNS[run.run_id] = run
        run.start()
        runs.append(run.payload())
    return {"runs": runs}


@app.get("/api/runs")
async def list_runs() -> dict[str, object]:
    live = {
        run_id: run.payload()
        for run_id, run in ACTIVE_RUNS.items()
        if run.status in {"created", "running"}
    }
    return {"runs": recent_runs(), "live": live}


@app.get("/api/runs/{run_id}/log")
async def read_run_log(run_id: str) -> dict[str, str]:
    run = ACTIVE_RUNS.get(run_id)
    if not run:
        matches = list(RUNS_ROOT.glob(f"*/*{run_id}*/output.log"))
        if not matches:
            raise HTTPException(status_code=404, detail="Unknown run")
        return {"run_id": run_id, "log": matches[0].read_text(errors="replace")}
    return {"run_id": run_id, "log": run.log_path.read_text(errors="replace") if run.log_path.exists() else ""}


@app.post("/api/runs/{run_id}/interrupt")
async def interrupt_run(run_id: str) -> dict[str, str]:
    run = ACTIVE_RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Unknown run")
    run.send_signal(signal.SIGINT)
    return {"status": "interrupt_sent"}


@app.websocket("/api/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    run = ACTIVE_RUNS.get(run_id)
    if not run:
        await websocket.send_json({"type": "error", "message": "Unknown run"})
        await websocket.close()
        return

    if run.log_path.exists():
        await websocket.send_json({"type": "output", "text": run.log_path.read_text(errors="replace")})

    queue = run.subscribe()
    try:
        while True:
            text = await queue.get()
            await websocket.send_json({"type": "output", "text": text})
            if DONE_SENTINEL in text:
                await websocket.send_json({"type": "done", "exit_code": run.exit_code})
                await websocket.close()
                return
    except WebSocketDisconnect:
        return
    finally:
        run.unsubscribe(queue)


@app.post("/__project_viewer_shutdown")
async def shutdown_previous_server(request: Request, token: str) -> dict[str, str]:
    if token != getattr(request.app.state, "shutdown_token", None):
        raise HTTPException(status_code=403, detail="Invalid shutdown token")

    server = getattr(request.app.state, "uvicorn_server", None)
    if server is None:
        raise HTTPException(status_code=503, detail="Server handle unavailable")

    server.should_exit = True
    return {"status": "shutting down"}


async def run_server() -> None:
    instance = SingleInstanceServer()
    port = await instance.prepare()
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    app.state.shutdown_token = instance.token
    app.state.uvicorn_server = server
    try:
        await server.serve()
    finally:
        instance.cleanup_sentinel()


if __name__ == "__main__":
    asyncio.run(run_server())
