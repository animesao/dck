"""Container networking: bridge, veth pairs, iptables port forwarding."""

import subprocess
import time

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


def ensure_bridge():
    """Create docker bridge if not exists."""
    r = _ip(["link", "show", DCK_BRIDGE], check=False)
    if r.returncode != 0:
        _ip(["link", "add", DCK_BRIDGE, "type", "bridge"])
        _ip(["addr", "add", f"{DCK_GATEWAY}/24", "dev", DCK_BRIDGE])
        _ip(["link", "set", DCK_BRIDGE, "up"])
        _iptables(["-t", "nat", "-A", "POSTROUTING", "-s", DCK_SUBNET, "!", "-o", DCK_BRIDGE, "-j", "MASQUERADE"])
        _iptables(["-A", "FORWARD", "-i", DCK_BRIDGE, "-j", "ACCEPT"])
        _iptables(["-A", "FORWARD", "-o", DCK_BRIDGE, "-j", "ACCEPT"])


def allocate_ip():
    """Allocate next available IP on the bridge."""
    import json
    from pathlib import Path

    DCK_DIR = Path.home() / ".dck"
    ip_file = DCK_DIR / "network_ips.json"
    used = set()

    if ip_file.exists():
        try:
            used = set(json.loads(ip_file.read_text()))
        except Exception:
            pass

    for i in range(DCK_IP_START, DCK_IP_END + 1):
        ip = f"10.0.0.{i}"
        if ip not in used:
            used.add(ip)
            ip_file.parent.mkdir(parents=True, exist_ok=True)
            ip_file.write_text(json.dumps(list(used)))
            return ip

    raise RuntimeError("No available IP addresses")


def release_ip(ip):
    """Release an IP address back to the pool."""
    import json
    from pathlib import Path

    DCK_DIR = Path.home() / ".dck"
    ip_file = DCK_DIR / "network_ips.json"
    if not ip_file.exists():
        return

    try:
        used = set(json.loads(ip_file.read_text()))
        used.discard(ip)
        ip_file.write_text(json.dumps(list(used)))
    except Exception:
        pass


def setup_veth(container_id, container_ip, bridge=DCK_BRIDGE):
    """Create veth pair and attach to bridge."""
    veth_host = f"v{container_id[:8]}"
    veth_container = "eth0"

    _ip(["link", "add", veth_host, "type", "veth", "peer", "name", veth_container])
    _ip(["link", "set", veth_host, "master", bridge])
    _ip(["link", "set", veth_host, "up"])

    _ip(["link", "set", veth_container, "netns", container_id])
    _ip(["netns", "exec", container_id, "ip", "addr", "add", f"{container_ip}/24", "dev", veth_container], timeout=5)
    _ip(["netns", "exec", container_id, "ip", "link", "set", veth_container, "up"], timeout=5)
    _ip(["netns", "exec", container_id, "ip", "link", "set", "lo", "up"], timeout=5)
    _ip(["netns", "exec", container_id, "ip", "route", "add", "default", "via", DCK_GATEWAY], timeout=5)

    return veth_host


def teardown_veth(veth_host):
    """Remove veth interface."""
    _ip(["link", "delete", veth_host], check=False, timeout=5)


def forward_port(host_port, container_ip, container_port, proto="tcp"):
    """Add iptables DNAT rule for port forwarding."""
    _iptables([
        "-t", "nat", "-A", "PREROUTING",
        "-p", proto, "--dport", str(host_port),
        "-j", "DNAT", "--to-destination", f"{container_ip}:{container_port}",
    ])
    _iptables([
        "-A", "FORWARD",
        "-p", proto, "--dport", str(container_port),
        "-d", container_ip,
        "-j", "ACCEPT",
    ])


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
