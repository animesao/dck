import os
import sys
import subprocess
import shutil
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def _check_binary(name):
    return shutil.which(name) is not None


def _check_kernel_ok():
    try:
        r = subprocess.run(["uname", "-r"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _check_overlayfs():
    try:
        with open("/proc/filesystems") as f:
            return "overlay\n" in f.read()
    except Exception:
        r = subprocess.run(["mount", "-t", "overlay"], capture_output=True, text=True, timeout=3)
        return r.returncode == 0 if r.returncode == 0 else False


def _check_cgroup_v2():
    return Path("/sys/fs/cgroup/cgroup.controllers").exists()


def doctor():
    table = Table(border_style="cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    kernel = _check_kernel_ok()
    is_linux = sys.platform == "linux"
    is_root = os.geteuid() == 0
    has_ns = os.path.exists("/proc/self/ns")
    has_mount = _check_binary("mount")
    has_umount = _check_binary("umount")
    has_ip = _check_binary("ip")
    has_iptables = _check_binary("iptables")
    has_nsenter = _check_binary("nsenter")
    overlay = _check_overlayfs()
    cgroup2 = _check_cgroup_v2()

    # Check kernel keyring limits (common cause of ENOMEM on pivot_root)
    key_maxkeys = key_maxbytes = ""
    try:
        with open("/proc/sys/kernel/keys/root_maxkeys") as f:
            v = int(f.read().strip())
            key_maxkeys = str(v)
            if v < 1000000:
                key_maxkeys += " [yellow](low — may cause ENOMEM)[/yellow]"
    except Exception:
        key_maxkeys = "?"
    try:
        with open("/proc/sys/kernel/keys/root_maxbytes") as f:
            v = int(f.read().strip())
            key_maxbytes = str(v)
            if v < 25000000:
                key_maxbytes += " [yellow](low — may cause ENOMEM)[/yellow]"
    except Exception:
        key_maxbytes = "?"

    table.add_row("Platform", Text("✓", style="green") if is_linux else Text("✗", style="red"), kernel)
    table.add_row("Root", Text("✓", style="green") if is_root else Text("✗", style="red"), "required for namespaces")
    table.add_row("Namespaces", Text("✓", style="green") if has_ns else Text("✗", style="red"), "/proc/self/ns")
    table.add_row("mount", Text("✓", style="green") if has_mount else Text("✗", style="red"), "")
    table.add_row("umount", Text("✓", style="green") if has_umount else Text("✗", style="red"), "")
    table.add_row("ip", Text("✓", style="green") if has_ip else Text("✗", style="red"), "networking")
    table.add_row("iptables", Text("✓", style="green") if has_iptables else Text("✗", style="red"), "port forwarding")
    table.add_row("nsenter", Text("✓", style="green") if has_nsenter else Text("✗", style="red"), "exec into container")
    table.add_row("OverlayFS", Text("✓", style="green") if overlay else Text("~", style="yellow"), "container layers")
    table.add_row("cgroups v2", Text("✓", style="green") if cgroup2 else Text("~", style="yellow"), "resource limits")
    table.add_row("keyring maxkeys", Text("✓", style="green") if not "low" in key_maxkeys else Text("~", style="yellow"), key_maxkeys)
    table.add_row("keyring maxbytes", Text("✓", style="green") if not "low" in key_maxbytes else Text("~", style="yellow"), key_maxbytes)

    all_ok = all([is_linux, is_root, has_ns, has_mount, has_umount, has_ip, has_iptables, has_nsenter])

    console.print("[bold cyan]dck Doctor[/bold cyan] - Native Runtime Diagnostics\n")
    console.print(table)
    console.print()

    if all_ok:
        console.print("[green]✓ All checks passed — native runtime ready[/green]")
        if "low" in key_maxkeys or "low" in key_maxbytes:
            console.print("[yellow]  ⚠ Increase keyring limits: sysctl -w kernel.keys.root_maxkeys=1000000 kernel.keys.root_maxbytes=25000000[/yellow]")
    else:
        missing = []
        if not is_linux: missing.append("Linux OS")
        if not is_root: missing.append("root privileges (try: sudo dck ...)")
        if not has_ns: missing.append("namespace support (/proc/self/ns)")
        if not has_mount: missing.append("mount binary")
        if not has_umount: missing.append("umount binary")
        if not has_ip: missing.append("ip binary (iproute2)")
        if not has_iptables: missing.append("iptables binary")
        if not has_nsenter: missing.append("nsenter binary (util-linux)")
        console.print("[yellow]Fix the following:[/yellow]")
        for m in missing:
            console.print(f"  • {m}")
