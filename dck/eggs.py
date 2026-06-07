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
from dck.i18n import t
from dck.startup import startup_prompt, save_startup_for_container
from dck.port import open_container_ports

console = Console()

EGGS = {
    "python-slim": {
        "name": "Python 3.12 (slim)",
        "desc": "Lightweight Python environment with pip",
        "image": "python:3.12-slim",
        "category": "python",
        "ports": [{"host": 8000, "container": 8000, "proto": "tcp"}],
        "ram": "256m",
        "cpu": "1",
        "disk": "~200MB",
        "volumes": [
            {"path": "/app", "label": "Python app code", "default": "./app"},
        ],
        "env": [
            {"key": "PYTHONUNBUFFERED", "default": "1", "desc": "Disable Python buffering"},
            {"key": "PYTHONDONTWRITEBYTECODE", "default": "1", "desc": "Don't write .pyc files"},
        ],
        "command": "python -m http.server 8000",
        "note": "Place your Python files in ./app and they'll be available at /app",
    },
    "python-full": {
        "name": "Python 3.12 (full)",
        "desc": "Full Python with dev tools, git, build essentials",
        "image": "python:3.12",
        "category": "python",
        "ports": [{"host": 8000, "container": 8000, "proto": "tcp"}],
        "ram": "512m",
        "cpu": "1",
        "disk": "~1GB",
        "volumes": [
            {"path": "/app", "label": "Python app code", "default": "./app"},
        ],
        "env": [
            {"key": "PYTHONUNBUFFERED", "default": "1", "desc": "Disable Python buffering"},
        ],
        "command": "python -m http.server 8000",
        "note": "Full Python with gcc, git, and development headers",
    },
    "node": {
        "name": "Node.js 22 (LTS)",
        "desc": "Node.js LTS with npm for web apps and APIs",
        "image": "node:22-alpine",
        "category": "node",
        "ports": [{"host": 3000, "container": 3000, "proto": "tcp"}],
        "ram": "256m",
        "cpu": "1",
        "disk": "~200MB",
        "volumes": [
            {"path": "/app", "label": "Node.js app code", "default": "./app"},
        ],
        "env": [
            {"key": "NODE_ENV", "default": "production", "desc": "Node environment"},
        ],
        "command": "node index.js",
        "note": "Place your package.json and code in ./app, then run: dck exec <name> npm install",
    },
    "node-dev": {
        "name": "Node.js 22 (dev)",
        "desc": "Node.js with nodemon for development",
        "image": "node:22-alpine",
        "category": "node",
        "ports": [{"host": 3000, "container": 3000, "proto": "tcp"}],
        "ram": "256m",
        "cpu": "1",
        "disk": "~300MB",
        "volumes": [
            {"path": "/app", "label": "Node.js app code", "default": "./app"},
        ],
        "env": [
            {"key": "NODE_ENV", "default": "development", "desc": "Node environment"},
        ],
        "command": "npx nodemon index.js",
        "note": "Auto-restarts on file changes via nodemon",
    },
    "golang": {
        "name": "Golang 1.22",
        "desc": "Go development environment for building and running apps",
        "image": "golang:1.22-alpine",
        "category": "go",
        "ports": [{"host": 8080, "container": 8080, "proto": "tcp"}],
        "ram": "256m",
        "cpu": "1",
        "disk": "~400MB",
        "volumes": [
            {"path": "/app", "label": "Go app code", "default": "./app"},
        ],
        "env": [
            {"key": "GOPATH", "default": "/go", "desc": "Go path"},
        ],
        "command": "go run .",
        "note": "Place your Go module in ./app with go.mod",
    },
    "rust": {
        "name": "Rust",
        "desc": "Rust development environment with cargo",
        "image": "rust:latest",
        "category": "rust",
        "ports": [{"host": 8080, "container": 8080, "proto": "tcp"}],
        "ram": "1g",
        "cpu": "2",
        "disk": "~2GB",
        "volumes": [
            {"path": "/app", "label": "Rust app code", "default": "./app"},
        ],
        "env": [],
        "command": "cargo run",
        "note": "Place your Cargo.toml and src/ in ./app",
    },
    "java": {
        "name": "Java 21 (Maven)",
        "desc": "Java 21 JDK with Maven for building JVM apps",
        "image": "maven:3.9-eclipse-temurin-21",
        "category": "java",
        "ports": [{"host": 8080, "container": 8080, "proto": "tcp"}],
        "ram": "1g",
        "cpu": "2",
        "disk": "~1GB",
        "volumes": [
            {"path": "/app", "label": "Java app code", "default": "./app"},
        ],
        "env": [],
        "command": "mvn spring-boot:run",
        "note": "Place your Maven project (pom.xml) in ./app",
    },
    "postgres": {
        "name": "PostgreSQL 16",
        "desc": "PostgreSQL database server",
        "image": "postgres:16-alpine",
        "category": "database",
        "ports": [{"host": 5432, "container": 5432, "proto": "tcp"}],
        "ram": "512m",
        "cpu": "1",
        "disk": "~500MB",
        "volumes": [
            {"path": "/var/lib/postgresql/data", "label": "Database data", "default": "./pgdata"},
        ],
        "env": [
            {"key": "POSTGRES_PASSWORD", "default": "changeme", "desc": "Database password"},
            {"key": "POSTGRES_USER", "default": "app", "desc": "Database user"},
            {"key": "POSTGRES_DB", "default": "appdb", "desc": "Database name"},
        ],
        "command": "",
        "note": "Connect via: docker exec -it <name> psql -U app appdb",
    },
    "mysql": {
        "name": "MySQL 8",
        "desc": "MySQL database server",
        "image": "mysql:8",
        "category": "database",
        "ports": [{"host": 3306, "container": 3306, "proto": "tcp"}],
        "ram": "512m",
        "cpu": "1",
        "disk": "~500MB",
        "volumes": [
            {"path": "/var/lib/mysql", "label": "Database data", "default": "./mysqldata"},
        ],
        "env": [
            {"key": "MYSQL_ROOT_PASSWORD", "default": "changeme", "desc": "Root password"},
            {"key": "MYSQL_DATABASE", "default": "appdb", "desc": "Database name"},
            {"key": "MYSQL_USER", "default": "app", "desc": "Database user"},
            {"key": "MYSQL_PASSWORD", "default": "changeme", "desc": "User password"},
        ],
        "command": "",
        "note": "Connect via: docker exec -it <name> mysql -u root -p",
    },
    "redis": {
        "name": "Redis 7",
        "desc": "Redis in-memory cache and message broker",
        "image": "redis:7-alpine",
        "category": "database",
        "ports": [{"host": 6379, "container": 6379, "proto": "tcp"}],
        "ram": "128m",
        "cpu": "0.5",
        "disk": "~50MB",
        "volumes": [
            {"path": "/data", "label": "Redis data", "default": "./redisdata"},
        ],
        "env": [
            {"key": "REDIS_PASSWORD", "default": "", "desc": "Redis password (leave empty for none)"},
        ],
        "command": "redis-server --appendonly yes",
        "note": "Connect via: docker exec -it <name> redis-cli",
    },
    "nginx-proxy": {
        "name": "Nginx Reverse Proxy",
        "desc": "Nginx configured as a reverse proxy",
        "image": "nginx:alpine",
        "category": "web",
        "ports": [{"host": 80, "container": 80, "proto": "tcp"}],
        "ram": "64m",
        "cpu": "0.5",
        "disk": "~50MB",
        "volumes": [
            {"path": "/etc/nginx/conf.d", "label": "Nginx configs", "default": "./nginx-config"},
            {"path": "/usr/share/nginx/html", "label": "Static files", "default": "./html"},
        ],
        "env": [],
        "command": "nginx -g 'daemon off;'",
        "note": "Place .conf files in ./nginx-config and static files in ./html",
    },
}


def list_eggs():
    return dict(EGGS)


def get_egg(name):
    return EGGS.get(name)


def show_eggs():
    categories = {}
    for key, egg in EGGS.items():
        cat = egg.get("category", "other")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((key, egg))

    console.print(f"\n[bold cyan]dck Eggs[/bold cyan] — Pterodactyl-style container configurations\n")

    for cat in sorted(categories.keys()):
        table = Table(title=f"🐣 {cat.title()} Eggs", border_style="cyan")
        table.add_column("#", style="bold")
        table.add_column("Name", style="bold")
        table.add_column("Description")
        table.add_column("Image")
        table.add_column("Ports")

        for i, (key, egg) in enumerate(categories[cat], 1):
            ports = ", ".join(f"{p['container']}/{p['proto']}" for p in egg.get("ports", []))
            table.add_row(str(i), egg["name"], egg["desc"], egg["image"], ports)

        console.print(table)

    console.print(f"\n  [bold]Usage:[/bold] dck create --egg <name>")
    console.print(f"  [bold]List:[/bold]  dck eggs\n")


def prompt_egg_selection():
    flat = []
    for key, egg in EGGS.items():
        flat.append((key, egg))

    console.print(f"\n[bold cyan]Available Eggs:[/bold cyan]\n")
    table = Table(border_style="cyan")
    table.add_column("#", style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Category")
    table.add_column("Image")

    for i, (key, egg) in enumerate(flat, 1):
        table.add_row(str(i), egg["name"], egg.get("category", ""), egg["image"])
    console.print(table)

    while True:
        choice = Prompt.ask("\nSelect egg number or name", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(flat):
                return flat[idx][0], flat[idx][1]
        except ValueError:
            pass
        if choice in EGGS:
            return choice, EGGS[choice]
        console.print("[red]Invalid choice[/red]")


def create_from_egg(egg_name):
    egg = get_egg(egg_name)
    if not egg:
        console.print(f"[red]Egg '{egg_name}' not found[/red]")
        return

    egg_key = egg_name
    name = Prompt.ask("Container name", default=egg_name)

    panel = Panel.fit(
        f"[bold cyan]{escape(egg['name'])}[/bold cyan]\n"
        f"[white]{escape(egg['desc'])}[/white]\n\n"
        f"[bold]Image:[/bold] {escape(egg['image'])}\n"
        f"[bold]RAM:[/bold] {escape(egg.get('ram', '256m'))}\n"
        f"[bold]CPU:[/bold] {escape(egg.get('cpu', '1'))}\n"
        f"[bold]Ports:[/bold]\n"
        + "\n".join(f"  {p['host']}:{p['container']}/{p['proto']}" for p in egg.get("ports", []))
        + (f"\n\n[bold]{t('tip')}:[/bold] {escape(egg['note'])}" if egg.get("note") else ""),
        title=f"Egg: {egg_key}",
        border_style="cyan",
    )
    console.print(panel)

    if not Confirm.ask("\nCreate this container?", default=True):
        console.print(f"[yellow]{t('cancelled')}[/yellow]")
        return

    client = get_client()

    ports = {}
    console.print(f"\n[bold]{t('port.mappings')}[/bold]")
    defaults = ",".join(f"{p['host']}:{p['container']}/{p['proto']}" for p in egg.get("ports", []) if p.get("container"))
    answer = Prompt.ask("  Ports", default=defaults)
    for mapping in answer.replace(";", ",").split(","):
        mapping = mapping.strip()
        if not mapping:
            continue
        parsed = _parse_port_mapping(mapping)
        if parsed:
            ports.update(parsed)

    env_vars = {}
    env_list = egg.get("env", [])
    if env_list:
        console.print(f"\n[bold]{t('env.vars')}[/bold]")
        for var in env_list:
            answer = Prompt.ask(f"  {var['key']} ({var.get('desc', '')})", default=var.get("default", ""))
            env_vars[var["key"]] = answer

    volumes = {}
    vol_list = egg.get("volumes", [])
    if vol_list:
        console.print(f"\n[bold]{t('volume.mounts')}[/bold]")
        for vol in vol_list:
            answer = Prompt.ask(f"  {vol['label']}", default=vol["default"])
            if answer:
                abs_path = os.path.abspath(answer)
                os.makedirs(abs_path, exist_ok=True)
                volumes[abs_path] = {"bind": vol["path"], "mode": "rw"}

    ram = egg.get("ram", "256m")
    cpu = egg.get("cpu", "1")
    ram = Prompt.ask(f"  {t('ram.limit')}", default=ram)
    cpu = Prompt.ask(f"  {t('cpu.limit')}", default=cpu)

    startup_cfg = startup_prompt()
    if not startup_cfg and egg.get("command"):
        if Confirm.ask(f"  Use egg default command: '{egg['command']}'?", default=True):
            startup_cfg = {"type": "command", "value": egg["command"]}

    host_cfg = {}
    if ram:
        validated = _validate_memory(ram)
        if validated:
            host_cfg["mem_limit"] = validated
    if cpu:
        host_cfg["nano_cpus"] = _parse_cpu(cpu)

    create_kwargs = {}
    if startup_cfg:
        stype = startup_cfg.get("type", "")
        svalue = startup_cfg.get("value", "")
        if stype == "command":
            create_kwargs["command"] = svalue
        elif stype == "entrypoint":
            create_kwargs["entrypoint"] = svalue

    image = egg["image"]
    with console.status(f"{t('pulling')} [cyan]{escape(image)}[/cyan]..."):
        try:
            client.images.pull(image)
        except APIError as e:
            console.print(f"[red]{t('error')}:[/red] {e}")
            return

    container_name = name or f"{egg_key}-{os.urandom(4).hex()}"

    with console.status(t("creating")):
        try:
            container = client.containers.create(
                image=image,
                name=container_name,
                ports=ports or None,
                environment=env_vars or None,
                volumes=volumes or None,
                detach=True,
                **create_kwargs,
                **host_cfg,
            )
        except APIError as e:
            console.print(f"[red]{t('error')}:[/red] {e}")
            return

    if startup_cfg:
        save_startup_for_container(container_name, startup_cfg)

    console.print(f"\n[green]{t('created')}![/green]")
    console.print(f"  Name: [bold]{container_name}[/bold]")
    console.print(f"  Image: {escape(image)}")

    if Confirm.ask(f"  {t('start.now')}", default=True):
        try:
            container.start()
        except APIError as e:
            console.print(f"[red]{t('error')}:[/red] {e}")
            return

    console.print(f"  {t('status.running')}: [green]{t('container.running')}[/green]")
    for c_port, h_port in (ports or {}).items():
        c_num = c_port.split("/")[0]
        proto = c_port.split("/")[1] if "/" in c_port else "tcp"
        console.print(f"  {t('port.info')}: [bold]{h_port}:{c_num}/{proto}[/bold]")

    open_container_ports(container_name, ports)

    tip = egg.get("note", "")
    if tip:
        console.print(f"\n[cyan]{t('tip')}:[/cyan] {escape(tip)}")
    console.print(f"\n[dim]{t('manage.hint')}: dck console {container_name} | dck logs {container_name} -f[/dim]")


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
        return 1_000_000_000
