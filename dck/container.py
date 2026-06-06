import time

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.text import Text
from docker.errors import NotFound, APIError

from dck.client import get_client

console = Console()


def _status_style(status):
    if "running" in status.lower() or "up" in status.lower():
        return "green"
    elif "exited" in status.lower() or "stopped" in status.lower():
        return "yellow"
    elif "dead" in status.lower() or "crash" in status.lower():
        return "red"
    return "white"


def _port_str(ports):
    if not ports:
        return ""
    parts = []
    for container_port, mappings in ports.items():
        if mappings:
            for m in mappings:
                if m.get("HostPort"):
                    parts.append(f"{m['HostIp'] or '0.0.0.0'}:{m['HostPort']}->{container_port}")
                else:
                    parts.append(str(container_port))
        else:
            parts.append(str(container_port))
    return ", ".join(parts)


def list_containers(show_all=False):
    client = get_client()
    containers = client.containers.list(all=show_all)

    if not containers:
        console.print("[yellow]No containers found.[/yellow]")
        return

    table = Table(title="Containers", border_style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Image", style="blue")
    table.add_column("Status")
    table.add_column("Ports", overflow="fold")
    table.add_column("Uptime")
    table.add_column("Restart Policy")

    for c in containers:
        name = c.name
        image = c.image.tags[0] if c.image.tags else c.image.short_id[:12]
        status = Text(c.status, style=_status_style(c.status))
        ports = _port_str(c.ports)

        created = c.attrs.get("Created", "")
        if created:
            created_ts = time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S"))
            uptime_secs = time.time() - created_ts
            if uptime_secs < 60:
                uptime = f"{int(uptime_secs)}s"
            elif uptime_secs < 3600:
                uptime = f"{int(uptime_secs // 60)}m"
            elif uptime_secs < 86400:
                uptime = f"{int(uptime_secs // 3600)}h"
            else:
                uptime = f"{int(uptime_secs // 86400)}d"
        else:
            uptime = "-"

        restart_policy = c.attrs.get("HostConfig", {}).get("RestartPolicy", {}).get("Name", "no")

        table.add_row(name, image, status, ports, uptime, restart_policy)

    console.print(table)


def view_logs(container_name, follow=False, tail=50):
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
        return

    if follow:
        try:
            for line in container.logs(stream=True, tail=tail):
                console.print(line.decode("utf-8").rstrip())
        except KeyboardInterrupt:
            pass
    else:
        logs = container.logs(tail=tail)
        console.print(logs.decode("utf-8"))


def start_container(container_name, restart=None):
    client = get_client()
    try:
        container = client.containers.get(container_name)
        container.start()
        if restart:
            set_restart_policy(container_name, restart, _silent=True)
        console.print(f"[green]Started[/green] container '{container_name}'")
    except NotFound:
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e.explanation or e}")


def stop_container(container_name):
    client = get_client()
    try:
        container = client.containers.get(container_name)
        container.stop()
        console.print(f"[yellow]Stopped[/yellow] container '{container_name}'")
    except NotFound:
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e.explanation or e}")


def restart_container(container_name):
    client = get_client()
    try:
        container = client.containers.get(container_name)
        container.restart()
        console.print(f"[green]Restarted[/green] container '{container_name}'")
    except NotFound:
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e.explanation or e}")


def remove_container(container_name, force=False, volumes=False):
    client = get_client()
    try:
        container = client.containers.get(container_name)
        container.remove(force=force, v=volumes)
        console.print(f"[red]Removed[/red] container '{container_name}'")
    except NotFound:
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e.explanation or e}")


def set_restart_policy(container_name, policy, _silent=False):
    client = get_client()
    try:
        container = client.containers.get(container_name)
        client.api.update_container(container.id, restart_policy={"Name": policy})
        if not _silent:
            console.print(f"[green]Restart policy[/green] set to '{policy}' for '{container_name}'")
    except NotFound:
        if not _silent:
            console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
    except APIError as e:
        if not _silent:
            console.print(f"[red]Error:[/red] {e.explanation or e}")
