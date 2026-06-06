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


def update_resources(container_name, ram=None, cpu=None, restart=None):
    """Update container resource limits (RAM, CPU) and optionally restart policy.

    ``ram`` – string like ``512m`` or ``2g``
    ``cpu`` – string/float representing CPU cores (e.g. ``0.5``, ``2``)
    ``restart`` – one of ``no, always, unless-stopped, on-failure``
    """
    client = get_client()
    try:
        container = client.containers.get(container_name)
    except NotFound:
        console.print(f"[red]Error:[/red] Container '{container_name}' not found.")
        return
    update_kwargs = {}
    if ram:
        update_kwargs["mem_limit"] = ram
    if cpu:
        # Convert CPU cores to nano_cpus (Docker expects integer nanoseconds of CPU time)
        try:
            nano = int(float(cpu) * 1_000_000_000)
            update_kwargs["nano_cpus"] = nano
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid CPU value '{cpu}'.")
            return
    if update_kwargs:
        try:
            client.api.update_container(container.id, **update_kwargs)
            console.print(f"[green]Updated[/green] resources for '{container_name}': {', '.join(update_kwargs.keys())}")
        except Exception as e:
            console.print(f"[red]Error updating resources:[/red] {e}")
    if restart:
        set_restart_policy(container_name, restart)



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
