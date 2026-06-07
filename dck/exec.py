import subprocess
import sys
import os
import threading
import time

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.markup import escape
from docker.errors import NotFound

from dck.client import get_client
from dck.i18n import t

console = Console()


def _pick_shell(container_name):
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        return "sh"
    for shell in ["bash", "sh", "ash", "powershell"]:
        r = subprocess.run(
            ["docker", "exec", container_name, "which", shell],
            capture_output=True, timeout=5,
        )
        if r.returncode == 0:
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
        for line in container.logs(stream=True, tail=5):
            if stop_event.is_set():
                break
            log_queue.append(line.decode("utf-8", errors="replace").rstrip())
            if len(log_queue) > 200:
                log_queue[:100] = []
    except Exception:
        pass


def _ptero_console(container, container_name, tail=30):
    """Pterodactyl-style real-time console with log streaming + command input."""
    import shlex

    if container.status != "running":
        console.print("[yellow]Container must be running for Pterodactyl console.[/yellow]")
        return

    console.print(f"\n[bold cyan]══ Pterodactyl Console: {container_name} ══[/bold cyan]")
    console.print("[dim]Commands are executed in the container via docker exec[/dim]")
    console.print("[dim]Logs stream in real-time. Type [bold]exit[/bold]/[bold]quit[/bold] or Ctrl+C to leave[/dim]")

    log_queue = []
    stop_event = threading.Event()
    log_thread = threading.Thread(
        target=_live_log_stream,
        args=(container_name, stop_event, log_queue),
        daemon=True,
    )
    log_thread.start()

    try:
        logs = container.logs(tail=tail).decode("utf-8", errors="replace").strip()
        if logs:
            recent = logs.split("\n")[-10:]
            console.print()
            for line in recent:
                console.print(f"  [dim]{escape(line)}[/dim]")
    except Exception:
        pass

    while True:
        try:
            while log_queue:
                line = log_queue.pop(0)
                console.print(f"  [dim]{escape(line)}[/dim]")
        except Exception:
            pass

        try:
            cmd = input("\n▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not cmd:
            continue
        if cmd.lower() in ("exit", "quit"):
            break

        try:
            r = subprocess.run(
                ["docker", "exec", container_name] + shlex.split(cmd),
                capture_output=True, text=True, timeout=30,
            )
            if r.stdout:
                print(r.stdout.rstrip())
            if r.stderr:
                sys.stderr.write(r.stderr.rstrip() + "\n")
            if r.returncode != 0:
                console.print(f"[dim]Exit code: {r.returncode}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[red]Command timed out[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    stop_event.set()
    log_thread.join(timeout=2)
    console.print(f"\n[bold yellow]── Pterodactyl console session ended ──[/bold yellow]")


def console_container(container_name, mode="auto", tail=20):
    """Pterodactyl-style console for a container.

    Modes:
      auto    - show info, logs, then offer shell/attach/ptero
      shell   - show info then directly enter interactive shell
      attach  - attach to container's main process
      logs    - stream live logs
      ptero   - Pterodactyl-style: real-time logs + commands
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
        _ptero_console(container, container_name, tail)
        return

    # auto mode
    if container.status == "running":
        _show_recent_logs(container, tail)
        console.print("[bold]Console options:[/bold]")
        console.print("  1. Enter interactive shell  [dim](docker exec -it)[/dim]")
        console.print("  2. Attach to main process   [dim](docker attach)[/dim]  [green]← for game servers[/green]")
        console.print("  3. Stream live logs         [dim](docker logs -f)[/dim]")
        console.print("  4. Pterodactyl console mode [dim](real-time logs + cmd)[/dim]")
        choice = Prompt.ask("  Choose", default="1")
        if choice == "1":
            _enter_interactive_shell(container_name)
        elif choice == "2":
            _attach_and_stream(container_name, show_logs_first=True)
        elif choice == "3":
            _follow_logs(container_name, tail)
        elif choice == "4":
            _ptero_console(container, container_name, tail)
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
