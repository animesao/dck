import subprocess
import sys
import time

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
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
    for shell in ["bash", "sh", "ash"]:
        r = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             f"command -v {shell} >/dev/null 2>&1 && echo {shell}"],
            capture_output=True, timeout=5,
        )
        out = r.stdout.decode().strip()
        if out:
            return out
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


def _attach_and_reconnect(container_name):
    """Attach to container with auto-reconnect on restart and clean signal handling."""
    console.print(f"[bold cyan]── Attached to {container_name} ──[/bold cyan]")
    console.print("[dim]Type your commands directly into the container's console[/dim]")
    console.print("[dim]Detach: Ctrl+P Ctrl+Q  |  Exit: Ctrl+C[/dim]\n")

    client = get_client()

    while True:
        proc = subprocess.Popen(
            ["docker", "attach", "--sig-proxy=false", container_name],
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
        )

        try:
            proc.wait()
        except KeyboardInterrupt:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

            console.print(f"\n[yellow]Exit console? (y/n): [/yellow]", end="", flush=True)
            try:
                response = sys.stdin.readline().strip().lower()
            except Exception:
                response = "y"
            if response == "y":
                break
            continue

        console.print(f"\n[yellow]Disconnected, waiting for container to restart...[/yellow]")

        reconnected = False
        for _ in range(300):
            try:
                container = client.containers.get(container_name)
                container.reload()
                if container.status == "running":
                    reconnected = True
                    break
            except Exception:
                pass
            time.sleep(1)

        if not reconnected:
            console.print(f"[red]Container did not restart[/red]")
            break

        console.print(f"[green]Reconnecting...[/green]")

    console.print(f"\n[bold yellow]── Console session ended ──[/bold yellow]")


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


def console_container(container_name, mode="attach", tail=20):
    """Game console for a container.

    Default mode: real-time docker attach with auto-reconnect.
    Also: mode="logs" → stream logs, mode="shell" → interactive shell.
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

    if mode == "shell":
        if container.status != "running":
            console.print("[yellow]Container is not running.[/yellow]")
            if Confirm.ask("  Start it and enter shell?", default=False):
                try:
                    container.start()
                    time.sleep(1)
                    container.reload()
                except Exception as e:
                    console.print(f"[red]{t('error')}:[/red] {e}")
                    return
                _show_console_header(container)
                _enter_interactive_shell(container_name)
            return
        _enter_interactive_shell(container_name)
        return

    if mode == "attach":
        _show_recent_logs(container, 10)
        if container.status != "running":
            console.print("[yellow]Container is not running.[/yellow]")
            if Confirm.ask("  Start it and enter console?", default=False):
                try:
                    container.start()
                    time.sleep(1)
                    container.reload()
                except Exception as e:
                    console.print(f"[red]{t('error')}:[/red] {e}")
                    return
                _show_console_header(container)
            else:
                return
        _attach_and_reconnect(container_name)
