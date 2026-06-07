import subprocess
import sys
import os
import threading
import time
import select as select_module
import pty
import re
import signal

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.markup import escape
from docker.errors import NotFound
from docker.utils import socket as docker_socket

from dck.client import get_client
from dck.i18n import t

console = Console()

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x1b]*\x1b\\')


def _pick_shell(container_name):
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        return "sh"
    for shell in ["bash", "sh", "ash", "powershell"]:
        r = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             f"command -v {shell} >/dev/null 2>&1 && echo found"],
            capture_output=True, timeout=5,
        )
        if "found" in r.stdout.decode():
            return shell
    return "sh"


def exec_container(container_name, cmd):
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]{t('error')}:[/red] {t('container.notfound', name=container_name)}")
        return

    if container.status != "running":
        console.print(f"[yellow]Container '{container_name}' is not running.[/yellow]")
        return

    if not cmd or cmd == ["sh"]:
        cmd = [_pick_shell(container_name)]

    subprocess.run(
        ["docker", "exec", "-it", container_name] + cmd,
    )


def inspect_container(container_name):
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]{t('error')}:[/red] {t('container.notfound', name=container_name)}")
        return

    attrs = container.attrs

    table = Table(title=f"Container: {container_name}", border_style="cyan")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    config = attrs.get("Config", {})
    state = attrs.get("State", {})
    host_config = attrs.get("HostConfig", {})
    network_settings = attrs.get("NetworkSettings", {})

    table.add_row("ID", container.short_id)
    table.add_row("Image", config.get("Image", "-"))
    table.add_row("Status", state.get("Status", "-"))
    table.add_row("Created", attrs.get("Created", "-")[:19])
    table.add_row("Platform", f"{attrs.get('Platform', '-')}")

    if config.get("ExposedPorts"):
        ports = ", ".join(config.get("ExposedPorts", {}).keys())
        table.add_row("Exposed Ports", ports)

    if network_settings.get("Ports"):
        port_strs = []
        for c_port, mappings in network_settings.get("Ports", {}).items():
            if mappings:
                for m in mappings:
                    port_strs.append(f"{m.get('HostIp', '0.0.0.0')}:{m.get('HostPort', '?')}->{c_port}")
        if port_strs:
            table.add_row("Port Mappings", ", ".join(port_strs))

    table.add_row("Restart Policy", host_config.get("RestartPolicy", {}).get("Name", "no"))

    if config.get("Env"):
        envs = "\n".join(config["Env"])
        table.add_row("Environment", envs)

    mounts = []
    for m in attrs.get("Mounts", []):
        src = m.get("Source", "")
        dst = m.get("Destination", "")
        mode = m.get("Mode", "rw")
        mounts.append(f"{src}:{dst} ({mode})")
    if mounts:
        table.add_row("Mounts", "\n".join(mounts))

    cmd_str = " ".join(config.get("Cmd", []))
    if cmd_str:
        table.add_row("Command", cmd_str)

    entrypoint = config.get("Entrypoint")
    if entrypoint:
        table.add_row("Entrypoint", " ".join(entrypoint) if isinstance(entrypoint, list) else entrypoint)

    console.print(table)


def _show_console_header(container):
    status_style = "green" if container.status == "running" else "yellow"
    image_str = container.image.tags[0] if container.image.tags else container.image.short_id[:12]

    header = Panel.fit(
        f"[bold cyan]Container:[/bold cyan] [white]{escape(container.name)}[/white]\n"
        f"[bold cyan]Status:[/bold cyan] [{status_style}]{container.status}[/{status_style}]\n"
        f"[bold cyan]Image:[/bold cyan]  [white]{escape(image_str)}[/white]\n"
        f"[bold cyan]ID:[/bold cyan]     [dim]{container.short_id}[/dim]",
        border_style="cyan",
    )
    console.print(header)
    console.print()


def _show_recent_logs(container, tail=20):
    try:
        logs = container.logs(tail=tail).decode("utf-8", errors="replace").strip()
        if logs:
            lines = logs.split("\n")
            console.print(f"[bold]Recent logs (last {len(lines)} lines):[/bold]")
            log_panel = Panel(
                "\n".join(f"  [dim]{escape(line)}[/dim]" for line in lines[-tail:]),
                border_style="dim",
            )
            console.print(log_panel)
        else:
            console.print("[dim]No recent logs.[/dim]")
    except Exception:
        console.print("[dim]Could not fetch logs.[/dim]")
    console.print()


def _attach_and_stream(container_name, show_logs_first=True):
    if show_logs_first:
        client = get_client()
        try:
            container = client.containers.get(container_name)
            _show_recent_logs(container, 15)
        except Exception:
            pass

    console.print(f"[bold cyan]── Attached to {container_name} ──[/bold cyan]")
    console.print("[dim]Type your commands directly into the container's console[/dim]")
    console.print("[dim]Detach: Ctrl+P Ctrl+Q  |  Exit: Ctrl+C[/dim]\n")
    try:
        subprocess.run(["docker", "attach", container_name])
    except KeyboardInterrupt:
        pass
    console.print(f"\n[bold yellow]── Detached from {container_name} ──[/bold yellow]")
    console.print(f"[dim]dck logs {container_name} -f  |  dck exec {container_name}  |  dck stop {container_name}[/dim]")


def _enter_interactive_shell(container_name):
    shell = _pick_shell(container_name)
    console.print(f"\n[bold cyan]── Opening interactive shell ({shell}) in '{container_name}' ──[/bold cyan]")
    console.print(f"[dim]Type 'exit' or Ctrl+D to return to host[/dim]\n")
    try:
        subprocess.run(["docker", "exec", "-it", container_name, shell])
    except KeyboardInterrupt:
        pass
    console.print(f"\n[bold yellow]── Shell session ended for '{container_name}' ──[/bold yellow]")


def _follow_logs(container_name, tail=30):
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]{t('error')}:[/red] {t('container.notfound', name=container_name)}")
        return

    console.print(f"[bold cyan]── Streaming logs for '{container_name}' (Ctrl+C to stop) ──[/bold cyan]\n")
    try:
        for line in container.logs(stream=True, tail=tail):
            sys.stdout.write(line.decode("utf-8", errors="replace"))
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    console.print(f"\n[bold yellow]── Log streaming stopped ──[/bold yellow]")


def _start_and_shell(container_name):
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]{t('error')}:[/red] {t('container.notfound', name=container_name)}")
        return

    console.print(f"[yellow]Container '{container_name}' is not running.[/yellow]")
    if container.attrs.get("State", {}).get("ExitCode"):
        console.print(f"  Exit code: {container.attrs['State']['ExitCode']}")

    if Confirm.ask("Start container and enter shell?", default=False):
        try:
            container.start()
            time.sleep(1)
            container.reload()
            if container.status == "running":
                _show_console_header(container)
                _enter_interactive_shell(container_name)
            else:
                logs = container.logs(tail=10).decode("utf-8", errors="replace").strip()
                console.print(f"[red]Container exited again ({container.status})[/red]")
                if logs:
                    console.print(f"[dim]{logs}[/dim]")
        except Exception as e:
            console.print(f"[red]{t('error')}:[/red] {e}")


def _live_log_stream(container_name, stop_event, log_queue):
    """Background thread: continuously fetch new logs and add to queue."""
    client = get_client()
    try:
        container = client.containers.get(container_name)
        seen = set()
        for line in container.logs(stream=True, tail=5):
            if stop_event.is_set():
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            log_queue.append(text)
            if len(log_queue) > 200:
                log_queue[:100] = []
    except Exception:
        pass


def _drain_logs(log_queue):
    """Drain all available log lines from the queue."""
    try:
        while log_queue:
            line = log_queue.pop(0)
            console.print(f"  {escape(line)}")
    except Exception:
        pass


def _exec_command(container_name, cmd):
    """Execute a command inside the container via docker exec."""
    import shlex
    try:
        r = subprocess.run(
            ["docker", "exec", container_name] + shlex.split(cmd),
            capture_output=True, text=True, timeout=30,
        )
        if r.stdout:
            print(r.stdout.rstrip())
        if r.stderr:
            sys.stderr.write(r.stderr.rstrip() + "\n")
        if r.returncode != 0 and r.returncode != 127:
            console.print(f"[dim]Exit code: {r.returncode}[/dim]")
        elif r.returncode == 127:
            hint = ("Command not found (exit 127). "
                    "Try [bold]dck console CONTAINER -m ptero -s[/bold] "
                    "for game server stdin mode")
            console.print(f"[dim]{hint}[/dim]")
    except subprocess.TimeoutExpired:
        console.print("[red]Command timed out[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _ptero_console(container, container_name, tail=30, use_stdin=False):
    """Pterodactyl-style real-time console.

    stdin mode: creates a PTY and runs `docker attach` for true
    bidirectional communication with PID 1 — exactly like Pterodactyl.

    exec mode: uses docker exec for apps/scripts.
    """
    import shlex

    if container.status != "running":
        console.print("[yellow]Container must be running for Pterodactyl console.[/yellow]")
        return

    if use_stdin:
        _ptero_console_pty(container, container_name, tail)
        return

    console.print(f"\n[bold cyan]══ Pterodactyl Console: {container_name} (docker exec) ══[/bold cyan]")
    console.print("[dim]Logs stream in real-time. Commands via [bold]docker exec[/bold][/dim]")
    console.print("[dim]Type [bold]exit[/bold]/[bold]quit[/bold] or Ctrl+C to leave[/dim]")

    try:
        logs = container.logs(tail=tail).decode("utf-8", errors="replace").strip()
        if logs:
            console.print()
            for line in logs.split("\n")[-15:]:
                if line.strip():
                    console.print(f"  {escape(line)}")
    except Exception:
        pass

    log_queue = []
    stop_event = threading.Event()
    log_thread = threading.Thread(
        target=_live_log_stream,
        args=(container_name, stop_event, log_queue),
        daemon=True,
        name="log-stream",
    )
    log_thread.start()

    while True:
        _drain_logs(log_queue)
        try:
            cmd = input("\n▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not cmd:
            continue
        if cmd.lower() in ("exit", "quit"):
            break
        _exec_command(container_name, cmd)

    stop_event.set()
    log_thread.join(timeout=2)
    console.print(f"\n[bold yellow]── Console session ended ──[/bold yellow]")


def _ptero_console_pty(container, container_name, tail=30):
    """Pterodactyl console via PTY + docker attach (true bidirectional).
    Auto-reconnects when container restarts.
    """
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Pterodactyl Console[/bold cyan] — real-time server console\n"
        "Logs and command output appear in the same stream.\n"
        "Type [bold]exit[/bold]/[bold]quit[/bold] or Ctrl+C to leave.\n"
        "[dim]Auto-reconnects on container restart.[/dim]",
        border_style="cyan",
    ))

    try:
        logs = container.logs(tail=tail).decode("utf-8", errors="replace").strip()
        if logs:
            console.print()
            for line in logs.split("\n")[-15:]:
                if line.strip():
                    console.print(f"  {escape(line)}")
    except Exception:
        pass

    docker_cmd = ["docker", "attach", container_name]
    sent_cmds = {}
    log_queue = []
    exit_requested = False

    def _reader(mfd):
        buf = b""
        try:
            while not exit_requested:
                r, _, _ = select_module.select([mfd], [], [], 0.1)
                if not r:
                    continue
                chunk = os.read(mfd, 65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="replace").rstrip("\r")
                    text = ANSI_RE.sub("", text)
                    if text:
                        stripped = text.strip()
                        if stripped in sent_cmds and time.time() - sent_cmds[stripped] < 1.0:
                            del sent_cmds[stripped]
                            continue
                        log_queue.append(text)
        except Exception:
            pass
        finally:
            if buf:
                text = buf.decode("utf-8", errors="replace").rstrip("\r")
                text = ANSI_RE.sub("", text)
                if text:
                    log_queue.append(text)

    client = get_client()

    preexec = None
    if os.name != "nt":
        preexec = lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)

    while not exit_requested:
        will_reconnect = False

        try:
            mfd, sfd = pty.openpty()
            proc = subprocess.Popen(
                docker_cmd,
                stdin=sfd,
                stdout=sfd,
                stderr=subprocess.STDOUT,
                close_fds=True,
                preexec_fn=preexec,
            )
            os.close(sfd)
        except Exception as e:
            console.print(f"[red]Failed to attach: {e}[/red]")
            return

        reader = threading.Thread(target=_reader, args=(mfd,), daemon=True, name="pty-reader")
        reader.start()

        _drain_logs(log_queue)

        cmd = None
        while not exit_requested:
            try:
                cmd = input("\n▶ ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                exit_requested = True
                break

            if not cmd:
                continue
            if cmd.lower() in ("exit", "quit"):
                exit_requested = True
                break

            sent_cmds[cmd.strip()] = time.time()

            try:
                os.write(mfd, (cmd + "\n").encode())
                time.sleep(0.3)
                _drain_logs(log_queue)
            except OSError:
                will_reconnect = True
                break

        try:
            os.write(mfd, b"\x03")
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass
        try:
            os.close(mfd)
        except Exception:
            pass
        reader.join(timeout=3)

        if not will_reconnect:
            break

        console.print("\n[yellow]Connection lost, waiting for container to restart...[/yellow]")
        for _ in range(300):
            try:
                c = client.containers.get(container_name)
                if c.status == "running":
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            console.print("[red]Container did not restart[/red]")
            break
        console.print("[green]Reconnected[/green]")
        log_queue.clear()
        sent_cmds.clear()

    console.print(f"\n[bold yellow]── Console session ended ──[/bold yellow]")


def console_container(container_name, mode="auto", tail=20, stdin=False):
    """Pterodactyl-style console for a container.

    Modes:
      auto    - show info, logs, then offer shell/attach/ptero
      shell   - show info then directly enter interactive shell
      attach  - attach to container's main process
      logs    - stream live logs
      ptero   - Pterodactyl-style: real-time logs + commands

    Args:
        stdin: In ptero mode, pipe commands to container's stdin (for game servers).
    """
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]{t('error')}:[/red] {t('container.notfound', name=container_name)}")
        return

    _show_console_header(container)

    if mode == "logs":
        _follow_logs(container_name, tail)
        return

    if mode == "attach":
        if container.status != "running":
            console.print("[yellow]Container not running, cannot attach.[/yellow]")
            return
        _attach_and_stream(container_name, show_logs_first=True)
        return

    if mode == "shell":
        if container.status != "running":
            _start_and_shell(container_name)
            return
        _enter_interactive_shell(container_name)
        return

    if mode == "ptero":
        _ptero_console(container, container_name, tail, use_stdin=stdin)
        return

    # auto mode
    if container.status == "running":
        _show_recent_logs(container, tail)
        console.print("[bold]Console options:[/bold]")
        console.print("  1. Enter interactive shell  [dim](docker exec -it)[/dim]")
        console.print("  2. Attach to main process   [dim](docker attach)[/dim]  [green]← for game servers[/green]")
        console.print("  3. Stream live logs         [dim](docker logs -f)[/dim]")
        console.print("  4. Pterodactyl console mode [dim](real-time logs + cmd)[/dim]")
        console.print("  5. Pterodactyl (stdin mode) [dim]for game servers (Minecraft, etc.)[/dim]")
        choice = Prompt.ask("  Choose", default="1")
        if choice == "1":
            _enter_interactive_shell(container_name)
        elif choice == "2":
            _attach_and_stream(container_name, show_logs_first=True)
        elif choice == "3":
            _follow_logs(container_name, tail)
        elif choice == "4":
            _ptero_console(container, container_name, tail, use_stdin=False)
        elif choice == "5":
            _ptero_console(container, container_name, tail, use_stdin=True)
    else:
        _start_and_shell(container_name)


def attach_container(container_name):
    """Attach to a container's main process with logs shown first."""
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]{t('error')}:[/red] {t('container.notfound', name=container_name)}")
        return

    if container.status != "running":
        console.print(f"[yellow]Container '{container_name}' is not running.[/yellow]")
        return

    _show_console_header(container)
    _attach_and_stream(container_name, show_logs_first=True)
