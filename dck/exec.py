import subprocess

from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from docker.errors import NotFound

from dck.client import get_client

console = Console()


def _pick_shell(container_name):
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
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
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
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
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


def console_container(container_name):
    """Open a debug console for a container: show logs, then enter shell"""
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
        return

    console.print(f"[bold cyan]Console:[/bold cyan] [white]{container_name}[/white]")
    console.print(f"  Status: [{'green' if container.status == 'running' else 'yellow'}]{container.status}[/]")
    console.print(f"  Image: {container.image.tags[0] if container.image.tags else container.image.short_id[:12]}")
    console.print()

    # Show recent logs
    try:
        logs = container.logs(tail=30).decode("utf-8", errors="replace").strip()
        if logs:
            console.print("[bold]Recent logs:[/bold]")
            for line in logs.split("\n")[-10:]:
                console.print(f"  [dim]{line}[/dim]")
        else:
            console.print("[dim]No recent logs.[/dim]")
    except Exception:
        pass
    console.print()

    if container.status == "running":
        shell = _pick_shell(container_name)
        if Confirm.ask(f"Enter interactive shell ([bold]{shell}[/bold])?", default=True):
            subprocess.run(["docker", "exec", "-it", container_name, shell])
    else:
        exit_code = container.attrs.get("State", {}).get("ExitCode", "?")
        console.print(f"  Exit code: [bold]{exit_code}[/bold]")
        if Confirm.ask("Start container and enter shell?", default=False):
            try:
                container.start()
                import time
                time.sleep(1)
                container.reload()
                if container.status == "running":
                    shell = _pick_shell(container_name)
                    subprocess.run(["docker", "exec", "-it", container_name, shell])
                else:
                    logs = container.logs(tail=10).decode("utf-8", errors="replace").strip()
                    console.print(f"[red]Container exited again ({container.status})[/red]")
                    if logs:
                        console.print(f"[dim]{logs}[/dim]")
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
