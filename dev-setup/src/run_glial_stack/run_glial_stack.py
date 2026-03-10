from __future__ import annotations

import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Iterable


DEFAULT_HOST = "127.0.0.1"
DEFAULT_ROUTER_PORT = 8765
DEFAULT_REACT_DEMO_PORT = 5173
DEFAULT_VIEWER_PORT = 5174
DEFAULT_GLIAL_USER_ID = "demo-user"
DEFAULT_VERIFY_TIMEOUT_SECS = 30.0


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def parse_env_file(env_path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if not env_path.exists():
        return parsed
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def expand_env_value(value: str, env: dict[str, str]) -> str:
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return env.get(key, "")

    expanded = value
    previous = None
    while previous != expanded:
        previous = expanded
        expanded = pattern.sub(replace, expanded)
    return expanded


def normalize_pythonpath(value: str) -> str:
    parts = [part for part in re.split(r"[;:]", value) if part]
    return os.pathsep.join(parts)


def build_base_env(root: Path, env_file: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("WORKSPACE_FOLDER", str(root))
    if env_file is not None:
        file_values = parse_env_file(env_file)
        resolved = dict(env)
        for key, raw_value in file_values.items():
            lookup_env = dict(resolved)
            lookup_env[key] = env.get(key, "")
            expanded = expand_env_value(raw_value, lookup_env)
            if key == "PYTHONPATH":
                expanded = normalize_pythonpath(expanded)
            resolved[key] = expanded
        env.update(resolved)
    env.setdefault("PYTHONPATH", "")
    return env


def wait_for_http(url: str, timeout_secs: float) -> bool:
    deadline = time.time() + timeout_secs
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if 200 <= response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(0.4)
    if last_error is not None:
        print(f"Timed out waiting for {url}: {last_error}", file=sys.stderr)
    return False


def run_blocking(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


@dataclass
class ManagedProcess:
    name: str
    process: subprocess.Popen[str]
    log_path: Path | None = None


def start_process(
    *,
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    background: bool,
    logs_dir: Path,
) -> ManagedProcess:
    stdout: int | IO[str] | None = None
    stderr: int | IO[str] | None = None
    log_path: Path | None = None
    kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "env": env,
        "text": True,
    }
    if background:
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"{name}.log"
        log_file = log_path.open("a", encoding="utf-8")
        stdout = log_file
        stderr = subprocess.STDOUT
        kwargs["start_new_session"] = True
    process = subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=stderr,
        **kwargs,
    )
    return ManagedProcess(name=name, process=process, log_path=log_path)


def terminate_processes(processes: Iterable[ManagedProcess]) -> None:
    alive = [managed for managed in processes if managed.process.poll() is None]
    for managed in alive:
        managed.process.terminate()
    deadline = time.time() + 5.0
    while time.time() < deadline and any(managed.process.poll() is None for managed in alive):
        time.sleep(0.1)
    for managed in alive:
        if managed.process.poll() is None:
            managed.process.kill()


def npm_command(*parts: str) -> list[str]:
    return ["npm", *parts]


def python_module_command(module: str, *parts: str) -> list[str]:
    return [sys.executable, "-m", module, *parts]


def router_command(host: str, port: int, store_dir: Path) -> list[str]:
    code = (
        "from glial_router import FilesystemRemoteSessionStore, InMemoryGlialCoordinator, create_app;"
        f"store = FilesystemRemoteSessionStore({str(store_dir)!r});"
        "coordinator = InMemoryGlialCoordinator(remote_session_store=store);"
        "app = create_app(coordinator=coordinator);"
        "import uvicorn;"
        f"uvicorn.run(app, host={host!r}, port={port}, log_level='info')"
    )
    return [sys.executable, "-c", code]


def vite_dev_command(host: str, port: int) -> list[str]:
    return ["npm", "run", "dev", "--", "--host", host, "--port", str(port)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Glial router, web demos, and Python demos from one command.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=workspace_root() / ".vscode" / ".env",
        help="Environment file to load before launching subprocesses.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Listening IP address.")
    parser.add_argument(
        "--router-port",
        type=int,
        default=DEFAULT_ROUTER_PORT,
        help="Port for the Glial router.",
    )
    parser.add_argument(
        "--react-demo-mode",
        choices=["router", "dev", "off"],
        default="router",
        help="Serve the React demo through the router, its own Vite server, or disable it.",
    )
    parser.add_argument(
        "--viewer-mode",
        choices=["router", "dev", "off"],
        default="router",
        help="Serve the Glial viewer through the router, its own Vite server, or disable it.",
    )
    parser.add_argument(
        "--react-demo-port",
        type=int,
        default=DEFAULT_REACT_DEMO_PORT,
        help="Port for standalone grip-react-demo Vite dev server.",
    )
    parser.add_argument(
        "--viewer-port",
        type=int,
        default=DEFAULT_VIEWER_PORT,
        help="Port for standalone glial-viewer-ts Vite dev server.",
    )
    parser.add_argument(
        "--python-demo-count",
        type=int,
        default=1,
        help="Number of grip-py-demo instances to launch.",
    )
    parser.add_argument(
        "--glial-user-id",
        default=DEFAULT_GLIAL_USER_ID,
        help="User ID passed to Glial-aware clients.",
    )
    parser.add_argument(
        "--router-store-dir",
        type=Path,
        default=workspace_root() / ".glial-router-store",
        help="Filesystem store directory used by the router.",
    )
    parser.add_argument(
        "--verify-timeout-secs",
        type=float,
        default=DEFAULT_VERIFY_TIMEOUT_SECS,
        help="How long to wait for HTTP services to become reachable.",
    )
    parser.add_argument(
        "--skip-web-build",
        action="store_true",
        help="Do not run npm build before serving router-hosted web apps.",
    )
    parser.add_argument(
        "--no-router",
        action="store_true",
        help="Do not start the router process.",
    )
    parser.add_argument(
        "--no-open-demo-browser",
        action="store_true",
        help="Do not open the React demo in a browser.",
    )
    parser.add_argument(
        "--no-open-viewer-browser",
        action="store_true",
        help="Do not open the Glial viewer in a browser.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--background",
        action="store_true",
        help="Start long-running processes detached and return immediately.",
    )
    group.add_argument(
        "--wait",
        action="store_true",
        help="Wait in the foreground and stop child processes on Ctrl-C (default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    parser.set_defaults(wait=True)
    return parser.parse_args()


def print_command(label: str, cmd: list[str], cwd: Path) -> None:
    rendered = " ".join(shlex.quote(part) for part in cmd)
    print(f"[{label}] (cd {cwd} && {rendered})")


def main() -> int:
    args = parse_args()
    root = workspace_root()
    env_file = args.env_file if args.env_file.exists() else None
    env = build_base_env(root, env_file)
    env["GLIAL_USER_ID"] = args.glial_user_id
    router_base_url = f"http://{args.host}:{args.router_port}"
    env["GLIAL_BASE_URL"] = router_base_url
    logs_dir = root / ".run-glial-stack"

    react_demo_dir = root / "grip-react-demo"
    viewer_dir = root / "glial-viewer-ts"
    python_demo_dir = root

    managed: list[ManagedProcess] = []

    try:
        if args.react_demo_mode == "router" and not args.skip_web_build:
            cmd = npm_command("run", "build")
            print_command("build-react-demo", cmd, react_demo_dir)
            if not args.dry_run:
                run_blocking(cmd, cwd=react_demo_dir, env=env)

        if args.viewer_mode == "router" and not args.skip_web_build:
            cmd = npm_command("run", "build")
            print_command("build-viewer", cmd, viewer_dir)
            if not args.dry_run:
                run_blocking(cmd, cwd=viewer_dir, env=env)

        if not args.no_router:
            cmd = router_command(args.host, args.router_port, args.router_store_dir)
            print_command("router", cmd, root)
            if not args.dry_run:
                managed.append(
                    start_process(
                        name="router",
                        cmd=cmd,
                        cwd=root,
                        env=env,
                        background=args.background,
                        logs_dir=logs_dir,
                    )
                )

        if args.react_demo_mode == "dev":
            cmd = vite_dev_command(args.host, args.react_demo_port)
            print_command("react-demo-dev", cmd, react_demo_dir)
            if not args.dry_run:
                managed.append(
                    start_process(
                        name="react-demo-dev",
                        cmd=cmd,
                        cwd=react_demo_dir,
                        env=env,
                        background=args.background,
                        logs_dir=logs_dir,
                    )
                )

        if args.viewer_mode == "dev":
            cmd = vite_dev_command(args.host, args.viewer_port)
            print_command("viewer-dev", cmd, viewer_dir)
            if not args.dry_run:
                managed.append(
                    start_process(
                        name="viewer-dev",
                        cmd=cmd,
                        cwd=viewer_dir,
                        env=env,
                        background=args.background,
                        logs_dir=logs_dir,
                    )
                )

        for index in range(args.python_demo_count):
            cmd = python_module_command("grip_py_demo.main")
            print_command(f"python-demo-{index + 1}", cmd, python_demo_dir)
            if not args.dry_run:
                demo_env = dict(env)
                demo_env["GRIP_PY_DEMO_INSTANCE"] = str(index + 1)
                managed.append(
                    start_process(
                        name=f"python-demo-{index + 1}",
                        cmd=cmd,
                        cwd=python_demo_dir,
                        env=demo_env,
                        background=args.background,
                        logs_dir=logs_dir,
                    )
                )

        if args.dry_run:
            return 0

        router_needed = (
            not args.no_router
            or args.react_demo_mode == "router"
            or args.viewer_mode == "router"
        )
        if router_needed:
            if not wait_for_http(router_base_url, args.verify_timeout_secs):
                terminate_processes(managed)
                return 1

        react_demo_url: str | None = None
        if args.react_demo_mode == "router":
            react_demo_url = f"{router_base_url}/demo/"
        elif args.react_demo_mode == "dev":
            react_demo_url = f"http://{args.host}:{args.react_demo_port}/"
            if not wait_for_http(react_demo_url, args.verify_timeout_secs):
                terminate_processes(managed)
                return 1

        viewer_url: str | None = None
        if args.viewer_mode == "router":
            viewer_url = f"{router_base_url}/viewer/"
        elif args.viewer_mode == "dev":
            viewer_url = f"http://{args.host}:{args.viewer_port}/"
            if not wait_for_http(viewer_url, args.verify_timeout_secs):
                terminate_processes(managed)
                return 1

        if react_demo_url is not None and not args.no_open_demo_browser:
            webbrowser.open(react_demo_url)
        if viewer_url is not None and not args.no_open_viewer_browser:
            webbrowser.open(viewer_url)

        print(f"Router base URL: {router_base_url}")
        if react_demo_url is not None:
            print(f"React demo URL: {react_demo_url}")
        if viewer_url is not None:
            print(f"Viewer URL: {viewer_url}")

        if args.background:
            for item in managed:
                if item.log_path is not None:
                    print(f"{item.name}: pid={item.process.pid} log={item.log_path}")
                else:
                    print(f"{item.name}: pid={item.process.pid}")
            return 0

        while managed:
            still_running: list[ManagedProcess] = []
            for item in managed:
                code = item.process.poll()
                if code is None:
                    still_running.append(item)
                else:
                    print(f"{item.name} exited with code {code}")
            managed = still_running
            time.sleep(0.25)
        return 0
    except KeyboardInterrupt:
        print("Stopping launched processes...")
        terminate_processes(managed)
        return 130
    except subprocess.CalledProcessError as error:
        print(f"Command failed with exit code {error.returncode}: {error.cmd}", file=sys.stderr)
        terminate_processes(managed)
        return error.returncode
    except Exception:
        terminate_processes(managed)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
