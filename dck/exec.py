import subprocess
import sys
import os

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.markup import escape
from docker.errors import NotFound

from dck.client import get_client
from dck.i18n import t
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


def _container_info(container_name):
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        return None
    return container


def _get_shell_cmd(container_name):
    shell = _pick_shell(container_name)
    if os.name == "nt":
        return ["docker", "exec", "-it", container_name, shell]
    return ["docker", "exec", "-it", container_name, shell]


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
                "\n".join(f"  [dim]{escape(line)}[/dim]" for line in lines[-20:]),
                border_style="dim",
            )
            console.print(log_panel)
        else:
            console.print("[dim]No recent logs.[/dim]")
    except Exception:
        console.print("[dim]Could not fetch logs.[/dim]")
    console.print()


def _attach_and_stream(container_name):
    console.print(f"\n[bold cyan]── Attached to {container_name} (Ctrl+P Ctrl+Q to detach) ──[/bold cyan]")
    console.print("[dim]You are now attached to the container's main process.[/dim]\n")
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
    console.print(f"[dim]dck logs {container_name} -f  |  dck exec {container_name}  |  dck stop {container_name}[/dim]")


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
            import time
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


def console_container(container_name, mode="auto", tail=20):
    """Pterodactyl-style console for a container.

    Modes:
      auto    - show info, logs, then offer shell/attach
      shell   - show info then directly enter interactive shell
      attach  - attach to container's main process
      logs    - stream live logs
      ptero   - Pterodactyl-style: REPL with log streaming + command input
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
        _attach_and_stream(container_name)
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
        console.print("  2. Attach to main process   [dim](docker attach)[/dim]")
        console.print("  3. Stream live logs         [dim](docker logs -f)[/dim]")
        console.print("  4. Pterodactyl console mode [dim](logs + commands)[/dim]")
        choice = Prompt.ask("  Choose", default="1")
        if choice == "1":
            _enter_interactive_shell(container_name)
        elif choice == "2":
            _attach_and_stream(container_name)
        elif choice == "3":
            _follow_logs(container_name, tail)
        elif choice == "4":
            _ptero_console(container, container_name, tail)
    else:
        _start_and_shell(container_name)


def _ptero_console(container, container_name, tail=30):
    """Pterodactyl-style console: live log streaming + command input."""
    import shlex

    if container.status != "running":
        console.print("[yellow]Container must be running for Pterodactyl console.[/yellow]")
        return

    console.print(f"\n[bold cyan]══ Pterodactyl Console: {container_name} ══[/bold cyan]")
    console.print("[dim]Type commands and press Enter to execute them in the container[/dim]")
    console.print("[dim]Type [bold]exit[/bold], [bold]quit[/bold], or press Ctrl+C to leave[/dim]")

    log_buffer = []
    try:
        logs = container.logs(tail=tail).decode("utf-8", errors="replace").strip()
        if logs:
            log_buffer = logs.split("\n")[-15:]
    except Exception:
        pass

    print()
    for line in log_buffer[-10:]:
        print(f"  [dim]{line}[/dim]")
    print()

    while True:
        try:
            cmd = input("▶ ").strip()
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
                print(f"[red]{r.stderr.rstrip()}[/red]")
            if r.returncode != 0:
                print(f"[dim]Exit code: {r.returncode}[/dim]")
        except subprocess.TimeoutExpired:
            print("[red]Command timed out[/red]")
        except Exception as e:
            print(f"[red]Error: {e}[/red]")

    console.print(f"\n[bold yellow]── Pterodactyl console session ended ──[/bold yellow]")
    console.print(f"[dim]dck logs {container_name} -f  |  dck exec {container_name}[/dim]")


def attach_container(container_name):
    """Attach to a container's main process."""
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]{t('error')}:[/red] {t('container.notfound', name=container_name)}")
        return

    if container.status != "running":
        console.print(f"[yellow]Container '{container_name}' is not running.[/yellow]")
        return

    _attach_and_stream(container_name)
