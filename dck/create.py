import os
import json
import subprocess
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.markup import escape
from docker.errors import APIError

from dck.client import get_client
from dck.templates import list_templates, get_template
from dck.i18n import t
from dck.port import open_container_ports
from dck.startup import (
    startup_prompt,
    save_startup_for_container,
    get_startup_config,
)

console = Console()
DCK_DIR = Path.home() / ".dck"
TEMPLATES_FILE = DCK_DIR / "templates.json"
PAPER_VERSIONS_FILE = Path(__file__).parent / "paper_versions.json"


def _get_server_ip():
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "3", "https://ifconfig.me"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "3", "https://api.ipify.org"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split()[0]
    except Exception:
        pass
    return None


def _load_paper_versions():
    """Load Paper versions from bundled JSON."""
    try:
        data = json.loads(PAPER_VERSIONS_FILE.read_text())
        return data.get("latest"), data.get("versions", {})
    except Exception:
        return None, {}


def _ask_paper_version():
    """Show Paper version picker, return (version_str, download_url) or None."""
    latest, versions = _load_paper_versions()
    if not versions:
        return None

    stable = {k: v for k, v in versions.items() if "-" not in k}
    stable_sorted = sorted(stable.keys(), key=lambda x: [int(p) if p.isdigit() else p for p in x.split(".")], reverse=True)

    console.print(f"\n[bold]Paper versions[/bold]  latest: [cyan]{latest}[/cyan]")
    console.print("[dim]Select version or leave empty for latest[/dim]\n")

    table = Table(border_style="cyan", box=None, show_header=False, padding=(0, 2))
    table.add_column("#", style="bold", width=3)
    table.add_column("Version")
    table.add_column("Build")

    recent = stable_sorted[:16]
    for i, ver in enumerate(recent, 1):
        url = stable[ver]
        build = url.split("-")[-1].replace(".jar", "")
        label = f"[green]{ver}[/green]" if ver == latest else ver
        table.add_row(str(i), label, build)

    console.print(table)

    if len(stable) > 16:
        console.print(f"  [dim]... and {len(stable) - 16} older versions (edit run.sh to use them)[/dim]")

    choice = Prompt.ask("  Paper version", default=str(recent.index(latest) + 1) if latest in recent else "1")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(recent):
            ver = recent[idx]
            return ver, stable[ver]
    except ValueError:
        pass
    if choice in versions:
        return choice, versions[choice]
    if not choice and latest:
        return latest, versions.get(latest)
    return None


def _download_jar(url, dest_path):
    """Download a jar file from URL to destination path."""
    import urllib.request
    console.print(f"  [dim]Downloading Paper...[/dim]")
    try:
        urllib.request.urlretrieve(url, str(dest_path))
        size = dest_path.stat().st_size
        console.print(f"  [green]✓[/green] Downloaded [bold]{size // 1024 // 1024}MB[/bold]")
        return True
    except Exception as e:
        console.print(f"  [red]Download failed: {e}[/red]")
        return False


def load_user_templates():
    DCK_DIR.mkdir(parents=True, exist_ok=True)
    if TEMPLATES_FILE.exists():
        try:
            return json.loads(TEMPLATES_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_user_template(key, data):
    DCK_DIR.mkdir(parents=True, exist_ok=True)
    templates = load_user_templates()
    templates[key] = data
    TEMPLATES_FILE.write_text(json.dumps(templates, indent=2))
    console.print(t("template.saved", name=key))


def get_all_templates(include_custom=True):
    builtin = list_templates()
    user = load_user_templates()
    all_templates = {}

    for k, tpl in builtin.items():
        all_templates[f"builtin:{k}"] = {**tpl, "_type": "builtin", "_key": k}
    for k, tpl in user.items():
        all_templates[f"user:{k}"] = {**tpl, "_type": "user", "_key": k}

    keys = list(all_templates.keys())
    if include_custom:
        keys.append("__custom__")

    return all_templates, keys


def show_templates(include_custom=True):
    all_templates, keys = get_all_templates(include_custom)

    table = Table(title="Templates", border_style="cyan")
    table.add_column("#", style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Image")
    table.add_column("RAM")
    table.add_column("Ports")

    for i, key in enumerate(keys, 1):
        if key == "__custom__":
            break
        tpl = all_templates[key]
        ports = ", ".join(f"{p['host']}:{p['container']}/{p['proto']}" for p in tpl.get("ports", []))
        label = f"{'📦 ' if tpl['_type'] == 'user' else ''}{tpl['name']}"
        table.add_row(str(i), label, tpl.get("desc", ""), tpl.get("image", ""), tpl.get("ram", ""), ports)

    console.print(table)

    if include_custom:
        console.print(f"\n  [bold]{len(keys)}[/bold]. {t('custom.image')}")

    return all_templates, keys


def _resolve_template_name(name, all_templates):
    if name.startswith("builtin:") or name.startswith("user:") or name == "__custom__":
        return name
    for key in all_templates:
        if key.endswith(f":{name}"):
            return key
        tpl = all_templates[key]
        if tpl.get("name", "").lower() == name.lower():
            return key
    console.print(f"[red]{t('error')}:[/red] {t('template.notfound', name=name)}")
    return None


def select_template(entries, keys):
    while True:
        choice = Prompt.ask(t("select.template"), default="1")
        if choice == "__custom__":
            return choice
        if choice in entries:
            return choice
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(keys):
                return keys[idx]
        except ValueError:
            pass
        console.print(f"[red]{t('invalid.choice')}[/red]")


def show_template_details(key, tpl):
    panel = Panel.fit(
        f"[bold cyan]{escape(tpl['name'])}[/bold cyan]\n"
        f"[white]{escape(tpl.get('desc', ''))}[/white]\n\n"
        f"[bold]Image:[/bold] {escape(tpl.get('image', ''))}\n"
        f"[bold]RAM:[/bold] {escape(tpl.get('ram', ''))}\n"
        f"[bold]CPU:[/bold] {escape(tpl.get('cpu', ''))}\n"
        f"[bold]Disk:[/bold] {escape(tpl.get('disk', ''))}\n\n"
        f"[bold]Ports:[/bold]\n"
        + "\n".join(f"  {p['host']}:{p['container']}/{p['proto']}" for p in tpl.get("ports", []))
        + (f"\n\n[bold]{t('tip')}:[/bold] {escape(tpl['note'])}" if tpl.get("note") else ""),
        title=f"Template: {key}",
        border_style="cyan",
    )
    console.print(panel)


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
        console.print(f"[red]{t('error')}: {t('memory.invalid')}[/red]")
        return None


def _parse_port_mapping(mapping):
    """Parse 'host:container/proto' or 'host:container' into (host, container, proto)"""
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
        return host, container, proto.strip().lower()
    except (ValueError, IndexError):
        return None


def ask_ports(template):
    ports = {}
    console.print(f"\n[bold]{t('port.mappings')}[/bold]")
    console.print("[dim]  Format: host:container/proto (e.g. 8080:80/tcp)[/dim]")
    console.print("[dim]  Multiple with commas (e.g. 80:80,443:443)[/dim]")

    port_list = template.get("ports", [{"host": "", "container": "", "proto": "tcp"}])
    defaults_str = ",".join(f"{p['host']}:{p['container']}/{p['proto']}" for p in port_list if p.get("container"))

    answer = Prompt.ask("  Ports", default=defaults_str or "80")
    for mapping in answer.replace(";", ",").split(","):
        mapping = mapping.strip()
        if not mapping:
            continue
        parsed = _parse_port_mapping(mapping)
        if parsed:
            host, container, proto = parsed
            ports[f"{container}/{proto}"] = host
        else:
            console.print(f"  [red]Invalid: {mapping} (use host:container/proto)[/red]")

    while True:
        extra = Prompt.ask(f"  {t('port.extra')}", default="")
        if not extra:
            break
        for mapping in extra.replace(";", ",").split(","):
            mapping = mapping.strip()
            if not mapping:
                continue
            parsed = _parse_port_mapping(mapping)
            if parsed:
                host, container, proto = parsed
                ports[f"{container}/{proto}"] = host
            else:
                console.print(f"  [red]{t('port.invalid')}[/red]")

    return ports


def ask_env(template):
    env_vars = {}
    env_list = template.get("env", [])

    if env_list:
        console.print(f"\n[bold]{t('env.vars')}[/bold]")
        for var in env_list:
            answer = Prompt.ask(f"  {var['key']} ({var.get('desc', '')})", default=var.get("default", ""))
            env_vars[var["key"]] = answer

    while True:
        extra = Prompt.ask(f"  {t('env.extra')}", default="")
        if not extra:
            break
        if "=" in extra:
            k, v = extra.split("=", 1)
            env_vars[k.strip()] = v.strip()
        else:
            console.print(f"[red]{t('env.invalid')}[/red]")

    return env_vars


def _ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        console.print(f"  [dim]Created directory: {path}[/dim]")


def ask_volumes(template, name_hint="container"):
    volumes = {}
    vol_list = template.get("volumes", [])

    if vol_list:
        console.print(f"\n[bold]{t('volume.mounts')}[/bold]")
        for vol in vol_list:
            default = vol["default"].replace("{name}", name_hint)
            answer = Prompt.ask(f"  {vol['label']}", default=default)
            if answer:
                abs_path = os.path.abspath(answer)
                _ensure_dir(abs_path)
                volumes[abs_path] = {"bind": vol["path"], "mode": "rw"}

    while True:
        extra = Prompt.ask(f"  {t('volume.extra')}", default="")
        if not extra:
            break
        if ":" in extra:
            h, c = extra.split(":", 1)
            abs_h = os.path.abspath(h)
            _ensure_dir(abs_h)
            volumes[abs_h] = {"bind": c, "mode": "rw"}
        else:
            console.print(f"[red]{t('volume.invalid')}[/red]")

    return volumes


def ask_resources(template):
    while True:
        ram = Prompt.ask(t("ram.limit"), default=template.get("ram", "512m"))
        validated = _validate_memory(ram)
        if validated:
            ram = validated
            break
    cpu = Prompt.ask(t("cpu.limit"), default=template.get("cpu", "1"))
    return ram, cpu


def _parse_cpu(cpu_str):
    try:
        cpus = float(cpu_str)
        return int(cpus * 1_000_000_000)  # nano_cpus
    except (ValueError, TypeError):
        return 1_000_000_000


def _create_data_launcher(container_name, template_key, template, vol_path, ports, env_vars, ram, cpu):
    """Create editable run.sh launcher in the server data directory.

    The launcher is the PRIMARY way to start the server. Container is created
    with TYPE=CUSTOM and stopped immediately so user can:
    1. Put their own server.jar in the data directory
    2. Edit run.sh to configure Java flags, jar path, etc.
    3. Run ./run.sh to start
    """
    image = template["image"]

    # Force CUSTOM type so user can supply their own jar
    custom_env = dict(env_vars) if env_vars else {}
    custom_env["TYPE"] = "CUSTOM"
    custom_env["CUSTOM_SERVER"] = "/data/server.jar"
    custom_env.pop("VERSION", None)

    port_lines = "\n".join(
        f'  -p "{h_port}:{c_port}" \\'
        for c_port, h_port in (ports or {}).items()
    )

    env_lines = "\n".join(
        f'  -e "{k}={v}" \\'
        for k, v in custom_env.items() if v
    )

    script = f"""#!/usr/bin/env bash
# ──────────────────────────────────────────────
# Minecraft Server Launcher — сгенерировано dck
# ──────────────────────────────────────────────
#
# КАК ИСПОЛЬЗОВАТЬ:
#   1. Положи свой server.jar в эту папку
#   2. Если jar называется иначе — поправь JAR= ниже
#   3. Настрой память в MEMORY=
#   4. Запусти: ./run.sh
#
# Скрипт удаляет старый контейнер и создаёт новый
# с TYPE=CUSTOM и CUSTOM_SERVER=/data/$JAR.
# ──────────────────────────────────────────────

# ====== НАСТРОЙКИ ======
CONTAINER="{container_name}"
MEMORY="{ram}"
CPU="{cpu}"
JAR="server.jar"

# ====== УДАЛИТЬ СТАРЫЙ КОНТЕЙНЕР ======
docker rm -f $CONTAINER 2>/dev/null

# ====== СОЗДАТЬ И ЗАПУСТИТЬ ======
docker run -d \\
  --name "$CONTAINER" \\
  --restart unless-stopped \\
{port_lines}
{env_lines}
  --memory $MEMORY \\
  --cpus="$CPU" \\
  -v "$(pwd):/data" \\
  {image}

# Подождать запуска
sleep 2

# Подключиться к консоли
docker attach $CONTAINER
"""

    vol_dir = Path(vol_path)
    vol_dir.mkdir(parents=True, exist_ok=True)
    script_path = vol_dir / "run.sh"
    script_path.write_text(script)
    script_path.chmod(script_path.stat().st_mode | 0o111)


def _gen_docker_run(template_key, template, name, ports, env_vars, volumes, ram, cpu):
    parts = ["docker run -d"]
    if name:
        parts.append(f'--name "{name}"')
    if ram:
        parts.append(f'--memory="{ram}"')
    if cpu:
        parts.append(f'--cpus="{cpu}"')
    for c_port, h_port in (ports or {}).items():
        parts.append(f'-p "{h_port}:{c_port}"')
    for k, v in (env_vars or {}).items():
        if v:
            parts.append(f'-e "{k}={v}"')
    for h_path, cfg in (volumes or {}).items():
        parts.append(f'-v "{h_path}:{cfg["bind"]}"')
    parts.append(template["image"])
    return " \\\n  ".join(parts)


def _save_launcher_script(container_name, docker_run_cmd):
    if not Confirm.ask(f"  Save launcher script? (recreate this container anytime)", default=False):
        return
    dir_path = Path.cwd() / "launchers"
    dir_path.mkdir(parents=True, exist_ok=True)
    script_path = dir_path / f"{container_name}.sh"
    script_path.write_text(
        "#!/usr/bin/env bash\n"
        "# Launcher for container: " + container_name + "\n"
        "# Generated by dck\n"
        "# Run: bash " + script_path.name + "\n\n"
        + docker_run_cmd + "\n"
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)
    console.print(f"  [green]✓[/green] Launcher saved: [bold]{script_path}[/bold]")


def _show_creation_summary(template_key, name, ports, env_vars, volumes, ram, cpu, paper_version=None):
    """Show a clean summary BEFORE creating the container."""
    ip = _get_server_ip()
    panel_lines = []
    if name:
        panel_lines.append(f"[bold]Name:[/bold] {escape(name)}")
    if ram:
        panel_lines.append(f"[bold]RAM:[/bold] {escape(ram)}")
    if cpu:
        panel_lines.append(f"[bold]CPU:[/bold] {escape(cpu)} cores")
    if paper_version:
        panel_lines.append(f"[bold]Paper:[/bold] [cyan]{escape(paper_version)}[/cyan]")
    for c_port, h_port in (ports or {}).items():
        proto = c_port.split("/")[1] if "/" in c_port else "tcp"
        c_num = c_port.split("/")[0]
        port_str = f"  [cyan]{h_port}:{c_num}/{proto}[/cyan]"
        if ip and proto == "tcp":
            port_str += f"  [dim]→ http://{ip}:{h_port}[/dim]"
        panel_lines.append(f"[bold]Port:[/bold]{port_str}")
    for h_path, cfg in (volumes or {}).items():
        panel_lines.append(f"[bold]Volume:[/bold] {escape(h_path)} [dim]→ {cfg['bind']}[/dim]")
    for k, v in (env_vars or {}).items():
        if v:
            panel_lines.append(f"[bold]Env:[/bold] {k}={escape(v)}")
    console.print()
    console.print(Panel.fit(
        "\n".join(panel_lines),
        title=f"[bold cyan]Summary: {escape(template_key)}[/bold cyan]",
        border_style="cyan",
    ))


def _show_container_summary(container, container_name, image, ports, volumes, env_vars, ram, cpu):
    ip = _get_server_ip()
    status = container.status if container else "unknown"
    status_style = "green" if status == "running" else "yellow"
    table = Table(title=f"Container: {container_name}", border_style="cyan", title_justify="left")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Image", image)
    table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")
    if ram:
        table.add_row("RAM", ram)
    if cpu:
        table.add_row("CPU", f"{cpu} cores")
    for c_port, h_port in (ports or {}).items():
        proto = c_port.split("/")[1] if "/" in c_port else "tcp"
        c_num = c_port.split("/")[0]
        port_str = f"{h_port}:{c_num}/{proto}"
        if ip:
            url = f"http://{ip}:{h_port}" if proto == "tcp" else f"{ip}:{h_port}/{proto}"
            port_str += f"  [cyan]{url}[/cyan]"
        table.add_row("Port", port_str)
    for h_path, cfg in (volumes or {}).items():
        table.add_row("Volume", f"{h_path} → {cfg['bind']}")
    for k, v in (env_vars or {}).items():
        if v:
            table.add_row("Env", f"{k}={v}")
    table.add_row("Manage", f"dck logs {container_name} | dck stop {container_name} | dck console {container_name}")
    table.add_row("Launcher", f"./launchers/{container_name}.sh")
    table.add_row("Delete", f"docker rm -f {container_name}")
    console.print()
    console.print(table)


def build_and_start(template_key, template, name, ports, env_vars, volumes, ram, cpu, start_now=True, startup_cfg=None, paper_info=None):
    client = get_client()

    is_game_server = template.get("tty", False)

    host_cfg = {}
    if ram:
        validated = _validate_memory(ram)
        if validated:
            host_cfg["mem_limit"] = validated
    if cpu:
        host_cfg["nano_cpus"] = _parse_cpu(cpu)

    image = template["image"]

    create_kwargs = {}
    if startup_cfg:
        stype = startup_cfg.get("type", "")
        svalue = startup_cfg.get("value", "")
        if stype == "command":
            create_kwargs["command"] = svalue
        elif stype == "entrypoint":
            create_kwargs["entrypoint"] = svalue

    # Allocate TTY for game servers so console stdin works
    if is_game_server:
        create_kwargs["tty"] = True
        create_kwargs["stdin_open"] = True

    # Auto-restart unless manually stopped
    create_kwargs["restart_policy"] = {"Name": "unless-stopped"}

    with console.status(f"{t('pulling')} [cyan]{escape(image)}[/cyan]..."):
        try:
            client.images.pull(image)
        except APIError as e:
            console.print(f"[red]{t('error')}:[/red] {e}")
            return None

    # Download Paper jar if user selected a version
    if paper_info and volumes:
        paper_version, paper_url = paper_info
        vol_path = list(volumes.keys())[0]
        jar_dest = Path(vol_path) / "server.jar"
        _download_jar(paper_url, jar_dest)

    container_name = name or f"{template_key}-{os.urandom(4).hex()}"

    # For game servers: force CUSTOM type so it works with run.sh
    container_env = dict(env_vars) if env_vars else {}
    if is_game_server:
        container_env["TYPE"] = "CUSTOM"
        container_env["CUSTOM_SERVER"] = "/data/server.jar"
        container_env.pop("VERSION", None)

    with console.status(t("creating")):
        try:
            container = client.containers.create(
                image=image,
                name=container_name,
                ports=ports or None,
                environment=container_env or None,
                volumes=volumes or None,
                detach=True,
                **create_kwargs,
                **host_cfg,
            )
        except APIError as e:
            console.print(f"[red]{t('error')}:[/red] {e}")
            return None

    if startup_cfg:
        save_startup_for_container(container_name, startup_cfg)

    console.print(f"\n[green]{t('created')}![/green]")
    console.print(f"  Name: [bold]{container_name}[/bold]")
    console.print(f"  Image: {escape(image)}")

    # For game servers: don't start, just create launcher
    if is_game_server and volumes:
        vol_path = list(volumes.keys())[0]
        _create_data_launcher(container_name, template_key, template, vol_path, ports, env_vars, ram, cpu)
        container.stop()
        container.reload()
        console.print(f"  [green]✓[/green] Launcher: [bold]{vol_path}/run.sh[/bold]")
        console.print(f"  [dim]Server folder: [bold]{vol_path}[/bold][/dim]")
        if paper_info:
            console.print(f"  [green]✓[/green] Paper jar downloaded: [bold]{vol_path}/server.jar[/bold]")
        else:
            console.print(f"  [dim]1. Put your [bold]server.jar[/bold] in that folder[/dim]")
        console.print(f"  [dim]2. Edit [bold]run.sh[/bold] if needed[/dim]")
        console.print(f"  [dim]3. Run: [bold]{vol_path}/run.sh[/bold][/dim]")
        open_container_ports(container_name, ports)
    else:
        # Non-game servers: normal start flow
        if start_now and Confirm.ask(f"  {t('start.now')}", default=True):
            with console.status("Starting..."):
                try:
                    container.start()
                    time.sleep(1)
                    container.reload()
                except APIError as e:
                    console.print(f"[red]{t('error')}:[/red] {e}")
                    return container_name

            if container.status == "running":
                console.print(f"  {t('status.running')}: [green]{t('container.running')}[/green]")
                for c_port, h_port in (ports or {}).items():
                    c_num = c_port.split("/")[0]
                    proto = c_port.split("/")[1] if "/" in c_port else "tcp"
                    console.print(f"  {t('port.info')}: [bold]{h_port}:{c_num}/{proto}[/bold]")
            else:
                logs = container.logs(tail=30).decode("utf-8", errors="replace").strip()
                console.print(f"  [red]{t('container.exited')}[/red] (status: {container.status})")
                if logs:
                    console.print(f"  [dim]{logs.split(chr(10))[-1]}[/dim]")
                if not Confirm.ask(f"  {t('start.anyway')}", default=False):
                    return container_name

        # Ask to open ports in firewall
        open_container_ports(container_name, ports)

        # Offer to save launcher script
        docker_run = _gen_docker_run(template_key, template, name, ports, env_vars, volumes, ram, cpu)
        _save_launcher_script(container_name, docker_run)

    # Show comprehensive summary
    _show_container_summary(container, container_name, image, ports, volumes, container_env, ram, cpu)

    console.print(f"\n[dim]{t('manage.hint')}: dck ps | dck logs {container_name} | dck stop {container_name}[/dim]")
    if template.get("note"):
        console.print(f"\n[cyan]{t('tip')}:[/cyan] {escape(template['note'])}")

    # Offer to enter console (only for non-game or if running)
    if container.status == "running" and not is_game_server:
        if Confirm.ask(f"\n  Enter console?", default=True):
            from dck.exec import _ptero_console_direct
            _ptero_console_direct(container_name)

    return container_name


def create_interactive(template_name, name, ram, cpu, port, env, volume, list_only):
    if list_only:
        show_templates()
        return

    if template_name:
        all_templates, keys = get_all_templates()
        template_name = _resolve_template_name(template_name, all_templates)
        if not template_name:
            return
    else:
        all_templates, keys = show_templates()
        template_name = select_template(all_templates, keys)

    if template_name == "__custom__":
        template_key = "custom"
        image = Prompt.ask(t("custom.image.prompt"), default="nginx:alpine")
        tpl = {
            "name": image,
            "desc": f"Custom container from {image}",
            "image": image,
            "ports": [],
            "ram": "512m",
            "cpu": "1",
            "disk": "varies",
            "volumes": [],
            "env": [],
            "note": "",
        }
        ports = ask_ports(tpl)
        env_vars = ask_env(tpl)
        volumes = ask_volumes(tpl, "custom")
        ram_cfg, cpu_cfg = ask_resources(tpl) if not (ram and cpu) else (ram or "512m", cpu or "1")

        startup_cfg = startup_prompt()

        if Confirm.ask(f"  {t('save.template')}", default=False):
            save_key = Prompt.ask(f"  {t('template.name')}", default=image.split("/")[-1].split(":")[0])
            save_tpl = {
                "name": tpl["name"],
                "desc": Prompt.ask(f"  {t('template.desc')}", default=f"Custom {image} container"),
                "image": image,
                "ports": ports,
                "ram": ram_cfg,
                "cpu": cpu_cfg,
                "volumes": [],
                "env": env_vars,
                "note": "",
            }
            save_user_template(save_key, save_tpl)

        suggested_name = name or template_key + "-" + os.urandom(4).hex()
        name = Prompt.ask("  Container name", default=suggested_name)

        _show_creation_summary(template_key, name, ports, env_vars, volumes, ram_cfg, cpu_cfg)

        if not Confirm.ask("\n[bold]Build this container?[/bold]", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return

        build_and_start(template_key, tpl, name, ports, env_vars, volumes, ram_cfg, cpu_cfg, startup_cfg=startup_cfg)
        return

    if template_name.startswith("builtin:"):
        template_key = template_name.replace("builtin:", "")
        tpl = get_template(template_key)
    elif template_name.startswith("user:"):
        template_key = template_name.replace("user:", "")
        user_templates = load_user_templates()
        tpl = user_templates.get(template_key, {})
    else:
        console.print(f"[red]{t('error')}:[/red] {t('template.notfound', name=template_name)}")
        return

    if not tpl:
        console.print(f"[red]{t('error')}:[/red] {t('template.notfound', name=template_name)}")
        return

    show_template_details(template_key, tpl)

    if not Confirm.ask(f"\n{t('create.this')}", default=True):
        console.print(f"[yellow]{t('cancelled')}[/yellow]")
        return

    ports = ask_ports(tpl)
    env_vars = ask_env(tpl)
    volumes = ask_volumes(tpl, template_key)
    ram_cfg, cpu_cfg = ask_resources(tpl)

    # Paper version picker for Minecraft
    paper_info = None
    if template_key == "minecraft":
        result = _ask_paper_version()
        if result:
            paper_info = result

    startup_cfg = startup_prompt()

    is_user_template = template_name.startswith("user:")
    if is_user_template and Confirm.ask(f"  {t('update.template')}", default=False):
        user_templates = load_user_templates()
        if template_key in user_templates:
            user_templates[template_key].update({
                "ports": ports,
                "ram": ram_cfg,
                "cpu": cpu_cfg,
                "env": env_vars,
            })
            TEMPLATES_FILE.write_text(json.dumps(user_templates, indent=2))
            console.print(t("template.updated", name=template_key))

    # Smart name suggestion
    suggested_name = name or template_key + "-" + os.urandom(4).hex()
    name = Prompt.ask("  Container name", default=suggested_name)

    # Pre-creation summary
    _show_creation_summary(template_key, name, ports, env_vars, volumes, ram_cfg, cpu_cfg, paper_version=paper_info[0] if paper_info else None)

    if not Confirm.ask("\n[bold]Build this container?[/bold]", default=True):
        console.print("[yellow]Cancelled[/yellow]")
        return

    build_and_start(template_key, tpl, name, ports, env_vars, volumes, ram_cfg, cpu_cfg, startup_cfg=startup_cfg, paper_info=paper_info)


def run_custom(image, name, ram, cpu):
    tpl = {
        "name": image,
        "desc": f"Custom container from {image}",
        "image": image,
        "ports": [],
        "ram": ram or "512m",
        "cpu": cpu or "1",
        "disk": "varies",
        "volumes": [],
        "env": [],
        "note": "",
    }

    console.print(Panel.fit(
        f"[bold cyan]{t('custom.container')}[/bold cyan]\n"
        f"[white]Image: {escape(image)}[/white]",
        border_style="cyan",
    ))

    ports = ask_ports(tpl)
    env_vars = ask_env(tpl)
    key = image.split("/")[-1].split(":")[0]
    volumes = ask_volumes(tpl, key)
    ram_cfg, cpu_cfg = (ram or "512m", cpu or "1")
    if not (ram and cpu):
        ram_cfg, cpu_cfg = ask_resources(tpl)

    startup_cfg = startup_prompt()

    suggested_name = name or key + "-" + os.urandom(4).hex()
    name = Prompt.ask("  Container name", default=suggested_name)

    _show_creation_summary(key, name, ports, env_vars, volumes, ram_cfg, cpu_cfg)

    if not Confirm.ask("\n[bold]Build this container?[/bold]", default=True):
        console.print("[yellow]Cancelled[/yellow]")
        return

    build_and_start(key, tpl, name, ports, env_vars, volumes, ram_cfg, cpu_cfg, startup_cfg=startup_cfg)
