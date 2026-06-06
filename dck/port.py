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
            _ufw_allow_ssh()
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
            _ufw_allow_ssh()
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


def _ufw_allow_ssh():
    """Ensure SSH port 22 is allowed before enabling UFW (prevents lockout)"""
    rules = _list_ufw_rules()
    if not any(r["port"] == "22" and r["proto"] == "tcp" for r in rules) and not any(r["port"] == "22" and r["proto"] == "any" for r in rules):
        console.print("  [yellow]SSH port 22 will be opened automatically to prevent lockout[/yellow]")
        subprocess.run(["ufw", "allow", "22/tcp"], capture_output=True, text=True, timeout=10)


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
                proc = " ".join(parts[5:]) if len(parts) > 5 else ""
                if ":" in addr:
                    port = addr.rsplit(":", 1)[-1]
                    ports.append({"port": port, "proto": proto.replace("tcp6", "tcp").replace("tcp", "tcp"), "addr": addr, "proc": proc})
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
@click.argument("action", type=click.Choice(["list", "status", "open", "close", "check", "enable", "disable", "default"]), default="list")
@click.argument("port", required=False)
@click.option("--proto", default="tcp", help="Protocol (tcp/udp)")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all (including container ports)")
def ports_cmd(action, port, proto, show_all):
    """Manage firewall ports (ufw)"""

    # ── status ─────────────────────────────────────────────────
    if action == "status":
        if not _ufw_installed():
            console.print("[yellow]UFW is not installed.[/yellow]")
            if Confirm.ask("Install UFW now?", default=True):
                _install_ufw()
                _ufw_allow_ssh()
                subprocess.run(["ufw", "--force", "enable"], capture_output=True, text=True, timeout=10)
            return

        active = _check_ufw()
        status_str = "[green]active[/green]" if active else "[red]inactive[/red]"
        console.print(f"UFW status: {status_str}")

        try:
            r = subprocess.run(["ufw", "status", "verbose"], capture_output=True, text=True, timeout=5)
            console.print(r.stdout)
        except Exception:
            pass
        return

    # ── enable / disable ────────────────────────────────────────
    if action == "enable":
        if not _ufw_installed():
            _install_ufw()
        _ufw_allow_ssh()
        try:
            r = subprocess.run(["ufw", "--force", "enable"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                console.print("[green]UFW enabled[/green] (SSH port 22 auto-allowed)")
            else:
                console.print(f"[red]Error:[/red] {r.stderr.strip()}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
        return

    if action == "disable":
        try:
            r = subprocess.run(["ufw", "--force", "disable"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                console.print("[yellow]UFW disabled[/yellow]")
            else:
                console.print(f"[red]Error:[/red] {r.stderr.strip()}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
        return

    # ── default ─────────────────────────────────────────────────
    if action == "default":
        if not port:
            console.print("[red]Usage: dck ports default allow|deny[/red]")
            return
        if port not in ("allow", "deny"):
            console.print("[red]Use: dck ports default allow[/red] or [red]dck ports default deny[/red]")
            return
        try:
            r = subprocess.run(["ufw", "default", port, "incoming"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                console.print(f"[green]Default incoming policy set to {port}[/green]")
            else:
                console.print(f"[red]Error:[/red] {r.stderr.strip()}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
        return

    # ── list ────────────────────────────────────────────────────
    if action == "list":
        # UFW status header
        if _ufw_installed():
            active = _check_ufw()
            status_str = "[green]active[/green]" if active else "[red]inactive[/red]"
            console.print(f"UFW: {status_str}")
            if active:
                rules = _list_ufw_rules()
                if rules:
                    ufw_table = Table(border_style="cyan", box=None, show_header=False)
                    ufw_table.add_column("Rule")
                    ufw_table.add_column("Action", style="bold")
                    ufw_table.add_column("Proto")
                    for r in rules:
                        ufw_table.add_row(f"  {r['port']}", "[green]ALLOW[/green]", r['proto'])
                    console.print(ufw_table)
                else:
                    console.print("  [dim]No UFW rules[/dim]")
            console.print()

        # Listening ports
        listening = _list_ports_ss()
        seen = set()

        if not listening and not show_all:
            console.print("[yellow]No listening ports found.[/yellow]")
            return

        table = Table(title="Listening Ports", border_style="cyan")
        table.add_column("Port", style="bold")
        table.add_column("Protocol")
        table.add_column("Process")
        table.add_column("Status")
        table.add_column("UFW")

        for p in listening:
            ufw_allowed = any(r["port"] == p["port"] and r["proto"] == p["proto"] for r in _list_ufw_rules()) if _ufw_installed() else "—"
            ufw_str = "[green]ALLOW[/green]" if ufw_allowed else "[yellow]—[/yellow]"
            proc = p.get("proc", p.get("addr", ""))
            table.add_row(p["port"], p["proto"], proc, "[green]LISTEN[/green]", ufw_str)

        console.print(table)

        if show_all:
            try:
                client = get_client()
                container_ports = []
                for c in client.containers.list():
                    for c_port, mappings in (c.ports or {}).items():
                        for m in (mappings or []):
                            hp = m.get("HostPort", "?")
                            proto = c_port.split("/")[1] if "/" in c_port else "tcp"
                            container_ports.append({"port": hp, "proto": proto, "container": c.name})
                if container_ports:
                    ct = Table(title="Container Ports", border_style="blue")
                    ct.add_column("Port", style="bold")
                    ct.add_column("Protocol")
                    ct.add_column("Container")
                    for cp in container_ports:
                        ct.add_row(cp["port"], cp["proto"], cp["container"])
                    console.print(ct)
            except Exception:
                pass
        return

    # ── check ───────────────────────────────────────────────────
    if action == "check":
        if not port:
            console.print("[red]Usage: dck ports check <port>[/red]")
            return
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

    # ── open / close ────────────────────────────────────────────
    if not port:
        console.print(f"[red]Usage: dck ports {action} <port>[/red]")
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
