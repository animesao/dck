import os
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.markup import escape
from docker.errors import APIError

from dck.client import get_client
from dck.templates import list_templates, get_template

console = Console()
DCK_DIR = Path.home() / ".dck"
TEMPLATES_FILE = DCK_DIR / "templates.json"


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
    console.print(f"[green]✓[/green] Template '[bold]{key}[/bold]' saved")


def get_all_templates(include_custom=True):
    builtin = list_templates()
    user = load_user_templates()
    all_templates = {}

    for k, t in builtin.items():
        all_templates[f"builtin:{k}"] = {**t, "_type": "builtin", "_key": k}
    for k, t in user.items():
        all_templates[f"user:{k}"] = {**t, "_type": "user", "_key": k}

    keys = list(all_templates.keys())
    if include_custom:
        keys.append("__custom__")

    return all_templates, keys


def show_templates(include_custom=True):
    all_templates, keys = get_all_templates(include_custom)

    table = Table(title="Available Templates", border_style="cyan")
    table.add_column("#", style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Image")
    table.add_column("RAM")
    table.add_column("Ports")

    for i, key in enumerate(keys, 1):
        if key == "__custom__":
            break
        t = all_templates[key]
        ports = ", ".join(f"{p['host']}:{p['container']}/{p['proto']}" for p in t.get("ports", []))
        label = f"{'📦 ' if t['_type'] == 'user' else ''}{t['name']}"
        table.add_row(str(i), label, t.get("desc", ""), t.get("image", ""), t.get("ram", ""), ports)

    console.print(table)

    if include_custom:
        console.print(f"\n  [bold]{len(keys)}[/bold]. Custom image (any Docker image)")

    return all_templates, keys


def _resolve_template_name(name, all_templates):
    """Resolve short name (minecraft) to full key (builtin:minecraft)"""
    if name.startswith("builtin:") or name.startswith("user:") or name == "__custom__":
        return name
    for key in all_templates:
        if key.endswith(f":{name}"):
            return key
        t = all_templates[key]
        if t.get("name", "").lower() == name.lower():
            return key
    console.print(f"[red]Template '{name}' not found. Use 'dck templates' to list available.[/red]")
    return None


def select_template(entries, keys):
    while True:
        choice = Prompt.ask("Select number or name", default="1")
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
        console.print("[red]Invalid choice. Try again.[/red]")


def show_template_details(key, t):
    panel = Panel.fit(
        f"[bold cyan]{escape(t['name'])}[/bold cyan]\n"
        f"[white]{escape(t.get('desc', ''))}[/white]\n\n"
        f"[bold]Image:[/bold] {escape(t.get('image', ''))}\n"
        f"[bold]Default RAM:[/bold] {escape(t.get('ram', ''))}\n"
        f"[bold]Default CPU:[/bold] {escape(t.get('cpu', ''))}\n"
        f"[bold]Disk space:[/bold] {escape(t.get('disk', ''))}\n\n"
        f"[bold]Ports:[/bold]\n"
        + "\n".join(f"  {p['host']}:{p['container']}/{p['proto']}" for p in t.get("ports", []))
        + (f"\n\n[bold]Note:[/bold] {escape(t['note'])}" if t.get("note") else ""),
        title=f"Template: {key}",
        border_style="cyan",
    )
    console.print(panel)


def ask_ports(template):
    ports = {}
    console.print("\n[bold]Port mappings (host:container/proto)[/bold]")
    port_list = template.get("ports", [{"host": "", "container": "", "proto": "tcp"}])

    for p in port_list:
        if p.get("container"):
            default = f"{p['host']}:{p['container']}/{p['proto']}"
            answer = Prompt.ask(f"  {p['container']}/{p['proto']}", default=default)
        else:
            answer = Prompt.ask(f"  Port (host:container/proto)", default="")

        if answer:
            try:
                parts = answer.split(":")
                h = int(parts[0])
                rest = parts[1].split("/")
                c = int(rest[0])
                proto = rest[1] if len(rest) > 1 else "tcp"
                ports[f"{c}/{proto}"] = h
            except (IndexError, ValueError):
                if "container" in p:
                    ports[f"{p['container']}/{p.get('proto', 'tcp')}"] = p["host"]

    # Ask for additional ports
    while True:
        extra = Prompt.ask("  Add extra port (host:container/proto) or leave empty", default="")
        if not extra:
            break
        try:
            parts = extra.split(":")
            h = int(parts[0])
            rest = parts[1].split("/")
            c = int(rest[0])
            proto = rest[1] if len(rest) > 1 else "tcp"
            ports[f"{c}/{proto}"] = h
        except (IndexError, ValueError):
            console.print("[red]Invalid format. Use host:container/proto (e.g. 8080:80/tcp)[/red]")

    return ports


def ask_env(template):
    env_vars = {}
    env_list = template.get("env", [])

    if env_list:
        console.print("\n[bold]Environment variables[/bold]")
        for var in env_list:
            answer = Prompt.ask(f"  {var['key']} ({var.get('desc', '')})", default=var.get("default", ""))
            env_vars[var["key"]] = answer

    # Ask for extra env vars
    while True:
        extra = Prompt.ask("  Add extra env var (KEY=value) or leave empty", default="")
        if not extra:
            break
        if "=" in extra:
            k, v = extra.split("=", 1)
            env_vars[k.strip()] = v.strip()
        else:
            console.print("[red]Invalid format. Use KEY=value[/red]")

    return env_vars


def ask_volumes(template):
    volumes = {}
    vol_list = template.get("volumes", [])

    if vol_list:
        console.print("\n[bold]Volume mounts (host path : container path)[/bold]")
        for vol in vol_list:
            answer = Prompt.ask(
                f"  {vol['label']}",
                default=vol["default"],
            )
            if answer:
                abs_path = os.path.abspath(answer)
                volumes[abs_path] = {"bind": vol["path"], "mode": "rw"}

    # Ask for extra volumes
    while True:
        extra = Prompt.ask("  Add extra volume (host:container) or leave empty", default="")
        if not extra:
            break
        if ":" in extra:
            h, c = extra.split(":", 1)
            volumes[os.path.abspath(h)] = {"bind": c, "mode": "rw"}
        else:
            console.print("[red]Invalid format. Use host:container (e.g. ./data:/app/data)[/red]")

    return volumes


def ask_resources(template):
    ram = Prompt.ask("RAM limit", default=template.get("ram", "512m"))
    cpu = Prompt.ask("CPU limit (cores)", default=template.get("cpu", "1"))
    return ram, cpu


def build_and_start(template_key, template, name, ports, env_vars, volumes, ram, cpu, start_now=True):
    client = get_client()

    resource_kwargs = {}
    if ram:
        resource_kwargs["mem_limit"] = ram
    if cpu:
        resource_kwargs["cpu_limit"] = float(cpu)

    image = template["image"]

    with console.status(f"Pulling image [cyan]{escape(image)}[/cyan]..."):
        try:
            client.images.pull(image)
        except APIError as e:
            console.print(f"[red]Error pulling image:[/red] {e}")
            return None

    container_name = name or f"{template_key}-{os.urandom(4).hex()}"

    with console.status("Creating container..."):
        try:
            container = client.containers.create(
                image=image,
                name=container_name,
                ports=ports or None,
                environment=env_vars or None,
                volumes=volumes or None,
                detach=True,
                **resource_kwargs,
            )
        except APIError as e:
            console.print(f"[red]Error creating container:[/red] {e}")
            return None

    console.print(f"\n[green]Container created![/green]")
    console.print(f"  Name: [bold]{container_name}[/bold]")
    console.print(f"  Image: {escape(image)}")

    if start_now and Confirm.ask("  Start container now?", default=True):
        with console.status("Starting..."):
            try:
                container.start()
                console.print(f"  Status: [green]Running[/green]")
                for c_port, h_port in (ports or {}).items():
                    c_num = c_port.split("/")[0]
                    proto = c_port.split("/")[1] if "/" in c_port else "tcp"
                    console.print(f"  Port: [bold]{h_port}:{c_num}/{proto}[/bold]")
            except APIError as e:
                console.print(f"[red]Error starting:[/red] {e}")

    console.print(f"\n[dim]Manage: dck ps | dck logs {container_name} | dck stop {container_name}[/dim]")
    if template.get("note"):
        console.print(f"\n[cyan]Tip:[/cyan] {escape(template['note'])}")

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
        image = Prompt.ask("Docker image", default="nginx:alpine")
        template = {
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
        ports = ask_ports(template)
        env_vars = ask_env(template)
        volumes = ask_volumes(template)
        ram, cpu = ask_resources(template)

        save_choice = Confirm.ask("  Save as template for later use?", default=False)
        if save_choice:
            save_key = Prompt.ask("  Template name", default=image.split("/")[-1].split(":")[0])
            save_template = {
                "name": template["name"],
                "desc": Prompt.ask("  Description", default=f"Custom {image} container"),
                "image": image,
                "ports": ports,
                "ram": ram,
                "cpu": cpu,
                "volumes": [],
                "env": env_vars,
                "note": "",
            }
            save_user_template(save_key, save_template)

        build_and_start(template_key, template, name, ports, env_vars, volumes, ram, cpu)
        return

    # Extract the actual template info
    if template_name.startswith("builtin:"):
        template_key = template_name.replace("builtin:", "")
        t = get_template(template_key)
    elif template_name.startswith("user:"):
        template_key = template_name.replace("user:", "")
        user_templates = load_user_templates()
        t = user_templates.get(template_key, {})
    else:
        console.print(f"[red]Template '{template_name}' not found.[/red]")
        return

    if not t:
        console.print(f"[red]Template '{template_name}' not found.[/red]")
        return

    show_template_details(template_key, t)

    if not Confirm.ask("\nCreate this container?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    ports = ask_ports(t)
    env_vars = ask_env(t)
    volumes = ask_volumes(t)
    ram, cpu = ask_resources(t)

    # Save modified template if user wants
    is_user_template = template_name.startswith("user:")
    if is_user_template and Confirm.ask("  Update saved template with these settings?", default=False):
        user_templates = load_user_templates()
        if template_key in user_templates:
            user_templates[template_key].update({
                "ports": ports,
                "ram": ram,
                "cpu": cpu,
                "env": env_vars,
            })
            TEMPLATES_FILE.write_text(json.dumps(user_templates, indent=2))
            console.print(f"[green]✓[/green] Template '[bold]{template_key}[/bold]' updated")

    build_and_start(template_key, t, name, ports, env_vars, volumes, ram, cpu)


def run_custom(image, name, ram, cpu):
    """Run a container from any Docker image interactively"""
    template = {
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
        f"[bold cyan]Custom container[/bold cyan]\n"
        f"[white]Image: {escape(image)}[/white]",
        border_style="cyan",
    ))

    ports = ask_ports(template)
    env_vars = ask_env(template)
    volumes = ask_volumes(template)
    ram, cpu = ask_resources(template) if not (ram and cpu) else (ram, cpu)

    key = image.split("/")[-1].split(":")[0]
    build_and_start(key, template, name, ports, env_vars, volumes, ram, cpu)
