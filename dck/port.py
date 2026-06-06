import subprocess
import socket

import click
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from dck.client import get_client

console = Console()


def _ufw_installed():
    try:
        r = subprocess.run(["ufw", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _install_ufw():
    console.print("[yellow]UFW not found. Installing...[/yellow]")
    try:
        r = subprocess.run(
            ["apt-get", "install", "-y", "ufw"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0:
            console.print("[green]✓[/green] UFW installed")
            return True
        else:
            console.print(f"[red]Error installing UFW:[/red] {r.stderr.strip()}")
            return False
    except FileNotFoundError:
        console.print("[red]Error:[/red] apt-get not found. Install UFW manually.")
        return False
    except subprocess.TimeoutExpired:
        console.print("[red]Error:[/red] Installation timed out.")
        return False


def _ensure_ufw():
    """Ensure UFW is installed and active; offer to install/activate if needed"""
    if not _ufw_installed():
        if Confirm.ask("  UFW is not installed. Install it now?", default=True):
            if not _install_ufw():
                return False
            # Enable after install
            try:
                subprocess.run(
                    ["ufw", "--force", "enable"],
                    capture_output=True, text=True, timeout=10,
                )
            except Exception:
                pass
        else:
            return False

    if not _check_ufw():
        if Confirm.ask("  UFW is inactive. Enable it now?", default=True):
            try:
                r = subprocess.run(
                    ["ufw", "--force", "enable"],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode != 0:
                    console.print(f"[red]Error enabling UFW:[/red] {r.stderr.strip()}")
                    return False
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
                return False
    return True


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

    if not _ensure_ufw():
        console.print("[yellow]Operation cancelled.[/yellow]")
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
    if ask_confirm and Confirm.ask(f"  Open these ports in firewall (UFW)?", default=True):
        if not _ensure_ufw():
            return
    else:
        return
    for c_port, h_port in (ports or {}).items():
        proto = c_port.split("/")[1] if "/" in c_port else "tcp"
        ok, msg = _open_ufw(h_port, proto)
        if ok:
            console.print(f"  [green]Firewall:[/green] opened {h_port}/{proto}")
        else:
            console.print(f"  [yellow]Firewall:[/yellow] {msg}")
