import json
import os
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from docker.errors import APIError, NotFound

from dck.client import get_client
from dck.i18n import t
from dck.startup import save_startup_for_container

console = Console()

MANIFEST_NAMES = ["dck.yml", "dck.yaml", "dck.json"]


def find_manifest():
    for name in MANIFEST_NAMES:
        path = Path.cwd() / name
        if path.exists():
            return path
    return None


def _parse_port_mapping(mapping):
    mapping = mapping.strip()
    if not mapping:
        return None
    try:
        proto = "tcp"
        if "/" in mapping:
            mapping, proto = mapping.rsplit("/", 1)
        if ":" in mapping:
            h_str, c_str = mapping.split(":", 1)
            host = int(h_str.strip())
            container = int(c_str.strip())
        else:
            host = int(mapping)
            container = host
        return {f"{container}/{proto.strip().lower()}": host}
    except (ValueError, IndexError):
        return None


def _validate_memory(mem_str):
    if not mem_str:
        return None
    mem_str = str(mem_str).strip().lower()
    if mem_str[-1] in "bkmgt":
        return mem_str
    try:
        int(mem_str)
        return mem_str + "m"
    except ValueError:
        return None


def _parse_cpu(cpu_str):
    try:
        cpus = float(cpu_str)
        return int(cpus * 1_000_000_000)
    except (ValueError, TypeError):
        return None


def load_manifest():
    path = find_manifest()
    if not path:
        return None, None
    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(content)
    elif suffix in (".yml", ".yaml"):
        try:
            import yaml
            data = yaml.safe_load(content)
        except ImportError:
            data = _parse_yaml_simple(content)
    else:
        return None, None
    containers = data.get("containers", [])
    if not containers and isinstance(data, list):
        containers = data
    return containers, path


def _parse_yaml_simple(content):
    lines = content.split("\n")
    result = {"containers": []}
    current = None
    in_containers = False
    key_map = {
        "name": "name", "image": "image", "ram": "ram", "cpu": "cpu",
        "restart": "restart", "command": "command", "entrypoint": "entrypoint",
    }
    list_keys = {"ports", "volumes"}
    dict_keys = {"env"}

    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        content = stripped.strip()

        if content == "containers:":
            in_containers = True
            continue

        if in_containers and indent == 2 and content.endswith(":"):
            if current:
                result["containers"].append(current)
            current = {"name": content[:-1]}
            continue

        if current and indent == 4 and ":" in content:
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip()
            if key in list_keys:
                current[key] = [v.strip().lstrip("- ") for v in [val] if v]
            elif key in dict_keys:
                current[key] = {}
                if val:
                    current[key] = val
            elif key in key_map:
                current[key_map[key]] = val
            continue

        if current and indent == 6 and content.startswith("- "):
            item = content[2:].strip()
            for k in list_keys:
                if k in current:
                    if isinstance(current[k], list):
                        current[k].append(item)
                    break
            continue

        if current and indent == 6 and ":" in content:
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip()
            if "env" in current and isinstance(current.get("env"), dict):
                current["env"][key] = val

    if current:
        result["containers"].append(current)
    return result


def _parse_port_list(port_list):
    ports = {}
    for p in port_list:
        parsed = _parse_port_mapping(p)
        if parsed:
            ports.update(parsed)
    return ports


def _parse_volume_list(vol_list):
    volumes = {}
    for v in vol_list:
        v = v.strip()
        if ":" in v:
            h, c = v.split(":", 1)
            abs_h = os.path.abspath(h)
            os.makedirs(abs_h, exist_ok=True)
            volumes[abs_h] = {"bind": c, "mode": "rw"}
    return volumes


def deploy_manifest():
    containers_data, path = load_manifest()
    if not containers_data:
        console.print(f"[red]{t('error')}: {t('manifest.notfound')}[/red]")
        return

    client = get_client()
    console.print(f"\n[bold cyan]{t('manifest.title')}[/bold cyan]")
    console.print(f"  {t('manifest.file')}: [bold]{path}[/bold]")
    console.print(f"  {t('manifest.found', n=len(containers_data))}")
    console.print(f"  {t('manifest.up', n=len(containers_data))}")

    for entry in containers_data:
        name = entry.get("name")
        if not name:
            console.print(f"[red]{t('error')}: {t('manifest.name_required')}[/red]")
            continue

        image = entry.get("image", "nginx:alpine")
        ports = _parse_port_list(entry.get("ports", []))
        env_vars = entry.get("env", {})
        volumes = _parse_volume_list(entry.get("volumes", []))
        ram = _validate_memory(entry.get("ram"))
        cpu = _parse_cpu(entry.get("cpu"))
        command = entry.get("command")
        entrypoint = entry.get("entrypoint")
        restart = entry.get("restart")

        with console.status(f"Pulling [cyan]{image}[/cyan]..."):
            try:
                client.images.pull(image)
            except APIError as e:
                console.print(f"  [red]{t('up.error', name=name, error=str(e))}[/red]")
                continue

        host_cfg = {}
        if ram:
            host_cfg["mem_limit"] = ram
        if cpu:
            host_cfg["nano_cpus"] = cpu

        try:
            container = client.containers.create(
                image=image,
                name=name,
                ports=ports or None,
                environment=env_vars or None,
                volumes=volumes or None,
                command=command or None,
                entrypoint=entrypoint or None,
                detach=True,
                **host_cfg,
            )
            container.start()
            time.sleep(1)
            container.reload()

            if restart:
                client.api.update_container(container.id, restart_policy={"Name": restart})

            startup_cfg = {}
            if command:
                startup_cfg = {"type": "command", "value": command}
            elif entrypoint:
                startup_cfg = {"type": "entrypoint", "value": entrypoint}
            if startup_cfg:
                save_startup_for_container(name, startup_cfg)

            console.print(f"  [green]✓[/green] {t('up.started', name=name)}")
        except APIError as e:
            console.print(f"  [red]✗[/red] {t('up.error', name=name, error=str(e))}")

    console.print("[green]✓[/green] Deployment complete")


def destroy_manifest():
    containers_data, path = load_manifest()
    if not containers_data:
        console.print(f"[red]{t('error')}: {t('manifest.notfound')}[/red]")
        return

    client = get_client()
    console.print(f"\n[bold cyan]{t('manifest.title')}[/bold cyan]")
    console.print(f"  {t('manifest.file')}: [bold]{path}[/bold]")
    console.print(f"  {t('manifest.down', n=len(containers_data))}")

    for entry in containers_data:
        name = entry.get("name")
        if not name:
            continue

        try:
            container = client.containers.get(name)
            container.stop()
            container.remove()
            console.print(f"  [green]✓[/green] {t('down.stopped', name=name)}")
        except NotFound:
            console.print(f"  [dim]Container '{name}' not found, skipping[/dim]")
        except APIError as e:
            console.print(f"  [red]✗[/red] {t('down.error', name=name, error=str(e))}")


def show_manifest():
    containers_data, path = load_manifest()
    if not containers_data:
        console.print(f"[red]{t('error')}: {t('manifest.notfound')}[/red]")
        return

    client = get_client()
    console.print(f"\n[bold cyan]{t('manifest.title')}[/bold cyan]")
    console.print(f"  {t('manifest.file')}: [bold]{path}[/bold]")

    table = Table(border_style="cyan")
    table.add_column("#", style="bold")
    table.add_column(t("manifest.service"), style="bold")
    table.add_column(t("manifest.image"))
    table.add_column(t("manifest.ports"))
    table.add_column(t("manifest.status"))

    for i, entry in enumerate(containers_data, 1):
        name = entry.get("name", "?")
        image = entry.get("image", "?")
        ports = ", ".join(entry.get("ports", []))
        status = "[dim]?[/dim]"
        try:
            container = client.containers.get(name)
            if container.status == "running":
                status = f"[green]{t('manifest.running')}[/green]"
            else:
                status = f"[yellow]{t('manifest.stopped')}[/yellow]"
        except NotFound:
            status = "[red]not found[/red]"
        table.add_row(str(i), name, image, ports, status)

    console.print(table)
