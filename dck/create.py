import os

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from docker.errors import APIError

from dck.client import get_client
from dck.templates import list_templates, get_template

console = Console()


def show_templates():
    templates = list_templates()
    table = Table(title="Available Templates", border_style="cyan")
    table.add_column("#", style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Image")
    table.add_column("Default RAM")
    table.add_column("Default Ports")

    for i, (key, t) in enumerate(templates.items(), 1):
        ports = ", ".join(f"{p['host']}:{p['container']}/{p['proto']}" for p in t["ports"])
        table.add_row(str(i), t["name"], t["desc"], t["image"], t["ram"], ports)

    console.print(table)
    return list(templates.keys())


def select_template(keys):
    while True:
        choice = Prompt.ask("Select template number or name", default="1")
        if choice in keys:
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
        f"[bold cyan]{t['name']}[/bold cyan]\n"
        f"[white]{t['desc']}[/white]\n\n"
        f"[bold]Image:[/bold] {t['image']}\n"
        f"[bold]Default RAM:[/bold] {t['ram']}\n"
        f"[bold]Default CPU:[/bold] {t['cpu']}\n"
        f"[bold]Disk space:[/bold] {t['disk']}\n\n"
        f"[bold]Ports:[/bold]\n"
        + "\n".join(f"  {p['host']}:{p['container']}/{p['proto']}" for p in t["ports"])
        + f"\n\n[bold]Note:[/bold] {t['note']}",
        title=f"Template: {key}",
        border_style="cyan",
    )
    console.print(panel)


def ask_ports(template):
    ports = {}
    console.print("\n[bold]Port mappings (host:container/proto)[/bold]")
    for p in template["ports"]:
        default = f"{p['host']}:{p['container']}/{p['proto']}"
        answer = Prompt.ask(f"  {p['container']}/{p['proto']}", default=default)
        if answer:
            try:
                parts = answer.split(":")
                h = int(parts[0])
                rest = parts[1].split("/")
                c = int(rest[0])
                proto = rest[1] if len(rest) > 1 else "tcp"
                ports[f"{c}/{proto}"] = h
            except (IndexError, ValueError):
                ports[f"{p['container']}/{p['proto']}"] = p["host"]
    return ports


def ask_env(template):
    env_vars = {}
    if not template.get("env"):
        return env_vars
    console.print("\n[bold]Environment variables[/bold]")
    for var in template["env"]:
        answer = Prompt.ask(f"  {var['key']} ({var['desc']})", default=var["default"])
        env_vars[var["key"]] = answer
    return env_vars


def ask_volumes(template):
    volumes = {}
    if not template.get("volumes"):
        return volumes
    console.print("\n[bold]Volume mounts (host:container)[/bold]")
    for vol in template["volumes"]:
        answer = Prompt.ask(f"  {vol['label']} [{vol['path']}]", default=vol["default"])
        if answer:
            abs_path = os.path.abspath(answer)
            volumes[abs_path] = {"bind": vol["path"], "mode": "rw"}
    return volumes


def build_container(template_key, name, ports, env_vars, volumes, ram, cpu):
    client = get_client()
    template = get_template(template_key)

    resource_kwargs = {}
    if ram:
        resource_kwargs["mem_limit"] = ram
    if cpu:
        resource_kwargs["cpu_limit"] = float(cpu)

    with console.status(f"Pulling image [cyan]{template['image']}[/cyan]..."):
        try:
            client.images.pull(template["image"])
        except APIError as e:
            console.print(f"[red]Error pulling image:[/red] {e}")
            return None

    container_name = name or f"{template_key}-{os.urandom(4).hex()}"

    with console.status("Creating container..."):
        try:
            container = client.containers.create(
                image=template["image"],
                name=container_name,
                ports=ports,
                environment=env_vars if env_vars else None,
                volumes=volumes if volumes else None,
                detach=True,
                **resource_kwargs,
            )
        except APIError as e:
            console.print(f"[red]Error creating container:[/red] {e}")
            return None

    return container, container_name, template


def create_interactive(template_name, name, ram, cpu, port, env, volume, list_only):
    keys = list(list_templates().keys())

    if list_only:
        show_templates()
        return

    if not template_name:
        show_templates()
        template_name = select_template(keys)

    t = get_template(template_name)
    if not t:
        console.print(f"[red]Template '{template_name}' not found.[/red]")
        console.print(f"Available: {', '.join(keys)}")
        return

    show_template_details(template_name, t)

    if not Confirm.ask("\nCreate this container?", default=True):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    ports = ask_ports(t)
    env_vars = ask_env(t)
    volumes = ask_volumes(t)

    if not ram:
        ram = Prompt.ask("RAM limit", default=t["ram"])
    if not cpu:
        cpu = Prompt.ask("CPU limit (cores)", default=t["cpu"])

    result = build_container(template_name, name, ports, env_vars, volumes, ram, cpu)
    if not result:
        return

    container, container_name, t = result

    console.print(f"\n[green]Container created![/green]")
    console.print(f"  Name: [bold]{container_name}[/bold]")
    console.print(f"  Image: {t['image']}")

    started = Confirm.ask("  Start container now?", default=True)
    if started:
        with console.status("Starting..."):
            try:
                container.start()
                console.print(f"  Status: [green]Running[/green]")
                for p in t["ports"]:
                    console.print(f"  Port: [bold]{p['host']}:{p['container']}/{p['proto']}[/bold]")
            except APIError as e:
                console.print(f"[red]Error starting:[/red] {e}")

    console.print(f"\n[dim]Manage: dck ps | dck logs {container_name} | dck stop {container_name}[/dim]")
    if t.get("note"):
        console.print(f"\n[cyan]Tip:[/cyan] {t['note']}")
