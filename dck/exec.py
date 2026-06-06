import subprocess
import sys

from rich.console import Console
from rich.table import Table
from docker.errors import NotFound

from dck.client import get_client

console = Console()


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
