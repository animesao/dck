"""Container networking: bridge, veth pairs, iptables port forwarding, UFW management."""

import fcntl
import json
import os
import subprocess
import time
from pathlib import Path

DCK_BRIDGE = "dck0"
DCK_SUBNET = "10.0.0.0/24"
DCK_GATEWAY = "10.0.0.1"
DCK_IP_START = 2
DCK_IP_END = 254


def _ip(cmd, check=True, timeout=10):
    """Run ip command."""
    full_cmd = ["ip"] + cmd
    try:
        return subprocess.run(full_cmd, check=check, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e


def _iptables(cmd, check=True, timeout=10):
    """Run iptables command."""
    full_cmd = ["iptables"] + cmd
    try:
        return subprocess.run(full_cmd, check=check, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e


def _rule_exists(cmd):
    """Check if an iptables rule exists."""
    r = _iptables(cmd + ["-C"], check=False)
    return r.returncode == 0


def ensure_bridge():
    """Create dck0 bridge if not exists. Idempotent — won't duplicate iptables rules."""
    r = _ip(["link", "show", DCK_BRIDGE], check=False)
    if r.returncode != 0:
        _ip(["link", "add", DCK_BRIDGE, "type", "bridge"])
        _ip(["addr", "add", f"{DCK_GATEWAY}/24", "dev", DCK_BRIDGE])
        _ip(["link", "set", DCK_BRIDGE, "up"])

    rules = [
        ["-t", "nat", "-A", "POSTROUTING", "-s", DCK_SUBNET, "!", "-o", DCK_BRIDGE, "-j", "MASQUERADE"],
        ["-A", "FORWARD", "-i", DCK_BRIDGE, "-j", "ACCEPT"],
        ["-A", "FORWARD", "-o", DCK_BRIDGE, "-j", "ACCEPT"],
    ]
    for rule in rules:
        if not _rule_exists(rule):
            _iptables(rule)


def _lock_ip_file(ip_file):
    ip_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(ip_file), os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _unlock_ip_file(fd):
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def _read_ips(fd):
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        data = os.read(fd, 65536)
        return set(json.loads(data)) if data else set()
    except Exception:
        return set()


def _write_ips(fd, ips):
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, json.dumps(list(ips)).encode())


def allocate_ip():
    """Allocate next available IP on the bridge."""
    ip_file = Path.home() / ".dck" / "network_ips.json"
    fd = _lock_ip_file(ip_file)
    try:
        used = _read_ips(fd)
        for i in range(DCK_IP_START, DCK_IP_END + 1):
            ip = f"10.0.0.{i}"
            if ip not in used:
                used.add(ip)
                _write_ips(fd, used)
                return ip
        raise RuntimeError("No available IP addresses")
    finally:
        _unlock_ip_file(fd)


def release_ip(ip):
    """Release an IP address back to the pool."""
    import os
    ip_file = Path.home() / ".dck" / "network_ips.json"
    if not ip_file.exists():
        return
    fd = _lock_ip_file(ip_file)
    try:
        used = _read_ips(fd)
        used.discard(ip)
        _write_ips(fd, used)
    except Exception:
        pass
    finally:
        _unlock_ip_file(fd)


def setup_veth(pid, container_ip, bridge=DCK_BRIDGE):
    """Create veth pair and attach to bridge. `pid` is the container's init process PID."""
    import os
    veth_host = f"v{pid:x}"[:12]
    veth_container = "eth0"

    _ip(["link", "add", veth_host, "type", "veth", "peer", "name", veth_container])
    _ip(["link", "set", veth_host, "master", bridge])
    _ip(["link", "set", veth_host, "up"])

    _ip(["link", "set", veth_container, "netns", str(pid)])
    _ip(["nsenter", "-t", str(pid), "-n", "ip", "addr", "add", f"{container_ip}/24", "dev", veth_container], timeout=5)
    _ip(["nsenter", "-t", str(pid), "-n", "ip", "link", "set", veth_container, "up"], timeout=5)
    _ip(["nsenter", "-t", str(pid), "-n", "ip", "link", "set", "lo", "up"], timeout=5)
    _ip(["nsenter", "-t", str(pid), "-n", "ip", "route", "add", "default", "via", DCK_GATEWAY], timeout=5)

    return veth_host


def teardown_veth(veth_host):
    """Remove veth interface."""
    _ip(["link", "delete", veth_host], check=False, timeout=5)


def forward_port(host_port, container_ip, container_port, proto="tcp", check_exists=False):
    """Add iptables DNAT rule for port forwarding."""
    dnat_rule = [
        "-t", "nat", "-A", "PREROUTING",
        "-p", proto, "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}",
    ]
    fwd_rule = [
        "-A", "FORWARD",
        "-p", proto, "--dport", str(container_port),
        "-d", container_ip,
        "-j", "ACCEPT",
    ]
    if check_exists:
        if _rule_exists(dnat_rule):
            return
        if _rule_exists(fwd_rule):
            return
    _iptables(dnat_rule)
    _iptables(fwd_rule)


def remove_port_forward(host_port, container_ip, container_port, proto="tcp"):
    """Remove iptables DNAT rule."""
    _iptables([
        "-t", "nat", "-D", "PREROUTING",
        "-p", proto, "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}",
    ], check=False)
    _iptables([
        "-D", "FORWARD",
        "-p", proto, "--dport", str(container_port),
        "-d", container_ip,
        "-j", "ACCEPT",
    ], check=False)


# ── UFW firewall helpers ────────────────────────────────────────────


def _ufw_installed():
    try:
        r = subprocess.run(["ufw", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _install_ufw():
    try:
        r = subprocess.run(["apt-get", "install", "-y", "ufw"], capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _check_ufw_active():
    try:
        r = subprocess.run(["ufw", "status"], capture_output=True, text=True, timeout=5)
        return "active" in r.stdout.lower() if r.returncode == 0 else False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ufw_allow(port, proto="tcp"):
    try:
        r = subprocess.run(["ufw", "allow", f"{port}/{proto}"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ensure_ufw():
    if not _ufw_installed():
        if not _install_ufw():
            return False
    if not _check_ufw_active():
        return False
    _ufw_allow(22, "tcp")
    return True


def open_ufw_ports(ports):
    opened = []
    for c_port, h_port in (ports or {}).items():
        proto = c_port.split("/")[1] if "/" in c_port else "tcp"
        if str(h_port) == "22":
            continue
        if _ufw_allow(h_port, proto):
            opened.append((h_port, proto))
    return opened
