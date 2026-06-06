from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from dck.client import get_client

console = Console()


def stats():
    client = get_client()
    containers = client.containers.list()

    if not containers:
        console.print("[yellow]No running containers to monitor.[/yellow]")
        return

    container_stats = {}

    try:
        with Live(auto_refresh=False, console=console) as live:
            for s in client.containers.stats(containers, stream=True, decode=True):
                cid = s.get("id", "")
                container_stats[cid] = s

                table = Table(title="Container Stats (Ctrl+C to exit)")
                table.add_column("Name", style="bold")
                table.add_column("CPU %")
                table.add_column("Memory")
                table.add_column("Mem %")
                table.add_column("Net RX")
                table.add_column("Net TX")

                for c in containers:
                    if c.id not in container_stats:
                        continue
                    s = container_stats[c.id]
                    name = c.name

                    cpu_delta = s["cpu_stats"]["cpu_usage"]["total_usage"] - s["precpu_stats"]["cpu_usage"]["total_usage"]
                    system_delta = s["cpu_stats"]["system_cpu_usage"] - s["precpu_stats"]["system_cpu_usage"]
                    num_cpus = s["cpu_stats"].get("online_cpus", 1)
                    cpu_percent = 0.0
                    if system_delta > 0 and cpu_delta > 0:
                        cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0

                    mem_stats = s["memory_stats"]
                    mem_usage = mem_stats.get("usage", 0)
                    mem_limit = mem_stats.get("limit", 1)
                    mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0

                    net = s.get("networks", {})
                    net_rx = sum(n.get("rx_bytes", 0) for n in net.values())
                    net_tx = sum(n.get("tx_bytes", 0) for n in net.values())

                    cpu_style = "green" if cpu_percent < 50 else "yellow" if cpu_percent < 80 else "red"

                    table.add_row(
                        name,
                        Text(f"{cpu_percent:.1f}%", style=cpu_style),
                        f"{_format_bytes(mem_usage)} / {_format_bytes(mem_limit)}",
                        f"{mem_percent:.1f}%",
                        _format_bytes(net_rx),
                        _format_bytes(net_tx),
                    )

                live.update(table, refresh=True)
    except KeyboardInterrupt:
        pass


def _format_bytes(bytes_val):
    if bytes_val < 1024:
        return f"{bytes_val}B"
    elif bytes_val < 1024 ** 2:
        return f"{bytes_val / 1024:.1f}KB"
    elif bytes_val < 1024 ** 3:
        return f"{bytes_val / 1024 ** 2:.1f}MB"
    elif bytes_val < 1024 ** 4:
        return f"{bytes_val / 1024 ** 3:.1f}GB"
    else:
        return f"{bytes_val / 1024 ** 4:.1f}TB"
