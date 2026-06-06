import subprocess
import socket

import click
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from dck.client import get_client

console = Console()


def _check_ufw():
    try:
        r = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=5)
        return "active" in r.stdout.lower() if r.returncode == 0 else False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_iptables():
    try:
        r = subprocess.run(["iptables", "-L"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _open_ufw(port, proto="tcp"):
    try:
        r = subprocess.run(
            ["ufw", "allow", f"{port}/{proto}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0, r.stdout.strip() or r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def _close_ufw(port, proto="tcp"):
    try:
        r = subprocess.run(
            ["ufw", "delete", "allow", f"{port}/{proto}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0, r.stdout.strip() or r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def _list_ports_ss():
    try:
        r = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return []
        lines = r.stdout.strip().split("\n")[1:]
        ports = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                proto = parts[0]
                addr = parts[3]
                if ":" in addr:
                    port = addr.rsplit(":", 1)[-1]
                    ports.append({"port": port, "proto": proto.replace("tcp", "tcp").replace("udp", "udp"), "addr": addr})
        return ports
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _list_ufw_rules():
    try:
        r = subprocess.run(
            ["ufw", "status", "numbered"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return []
        lines = r.stdout.strip().split("\n")
        rules = []
        for line in lines:
            if "ALLOW" in line and "/" in line:
                parts = line.strip().split()
                for p in parts:
                    if "/" in p and p.replace("/", "").replace(".", "").isdigit():
                        port, proto = p.split("/")
                        rules.append({"port": port, "proto": proto})
        return rules
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _is_port_open(port):
    """Check if a local port is in use (by any service)"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", int(port))) == 0


@click.command("ports")
@click.argument("action", type=click.Choice(["list", "open", "close", "check"]), default="list")
@click.argument("port", required=False)
@click.option("--proto", default="tcp", help="Protocol (tcp/udp)")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all (including container ports)")
def ports_cmd(action, port, proto, show_all):
    """Manage firewall ports (ufw)"""

    if action == "list":
        container_ports = []
        if show_all:
            try:
                client = get_client()
                for c in client.containers.list():
                    for c_port, mappings in (c.ports or {}).items():
                        for m in (mappings or []):
                            hp = m.get("HostPort", "?")
                            ip = m.get("HostIp", "0.0.0.0")
                            container_ports.append({"port": hp, "proto": c_port.split("/")[1] if "/" in c_port else "tcp", "container": c.name})
            except Exception:
                pass

        table = Table(title="Ports", border_style="cyan")
        table.add_column("Port", style="bold")
        table.add_column("Protocol")
        table.add_column("Status")
        table.add_column("Source")

        listening = _list_ports_ss()
        seen = set()
        for p in listening:
            key = (p["port"], p["proto"])
            if key not in seen:
                seen.add(key)
                status = "[green]LISTEN[/green]"
                src = "system"
                table.add_row(p["port"], p["proto"], status, src)

        for cp in container_ports:
            key = (cp["port"], cp["proto"])
            if key not in seen:
                seen.add(key)
                table.add_row(cp["port"], cp["proto"], "[blue]CONTAINER[/blue]", cp["container"])

        if _check_ufw():
            console.print("\n[bold]UFW rules:[/bold]")
            try:
                r = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=5)
                console.print(r.stdout)
            except Exception:
                pass

        if not seen:
            console.print("[yellow]No ports found.[/yellow]")

        return

    if not port:
        console.print("[red]Error: port number required[/red]")
        return

    if action == "check":
        if _is_port_open(port):
            console.print(f"Port [bold]{port}/{proto}[/bold] is [green]in use[/green]")
        else:
            console.print(f"Port [bold]{port}/{proto}[/bold] is [green]available[/green]")

        if _check_ufw():
            rules = _list_ufw_rules()
            if any(r["port"] == port and r["proto"] == proto for r in rules):
                console.print(f"  UFW: [green]allowed[/green]")
            else:
                console.print(f"  UFW: [yellow]not explicitly allowed[/yellow]")

        return

    if not _check_ufw():
        if not Confirm.ask("UFW is not active. Use iptables instead?", default=False):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    if action == "open":
        ok, msg = _open_ufw(port, proto)
        if ok:
            console.print(f"[green]Opened[/green] port {port}/{proto} in firewall")
        else:
            console.print(f"[red]Error:[/red] {msg}")

    elif action == "close":
        ok, msg = _close_ufw(port, proto)
        if ok:
            console.print(f"[green]Closed[/green] port {port}/{proto} in firewall")
        else:
            console.print(f"[red]Error:[/red] {msg}")


def open_container_ports(container_name, ports, ask_confirm=True):
    """Auto-open firewall ports for a container"""
    if not _check_ufw():
        return
    if ask_confirm and not Confirm.ask(f"  Open these ports in firewall (UFW)?", default=True):
        return
    for c_port, h_port in (ports or {}).items():
        proto = c_port.split("/")[1] if "/" in c_port else "tcp"
        ok, msg = _open_ufw(h_port, proto)
        if ok:
            console.print(f"  [green]Firewall:[/green] opened {h_port}/{proto}")
        else:
            console.print(f"  [yellow]Firewall:[/yellow] {msg}")
