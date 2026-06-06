import subprocess
import sys
import os

from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def _find_compose_file():
    candidates = ["compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"]
    for f in candidates:
        if os.path.isfile(f):
            return f
    return None


def _run_compose(args, capture=False):
    compose_file = _find_compose_file()
    cmd = ["docker", "compose"]
    if compose_file:
        cmd.extend(["-f", compose_file])
    cmd.extend(args)

    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout
        else:
            result = subprocess.run(cmd, check=True)
            return ""
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except FileNotFoundError:
        console.print("[red]Error:[/red] 'docker compose' not found. Is Docker installed?")
        sys.exit(1)


def compose_up(detach=False, build=False):
    args = ["up"]
    if detach:
        args.append("-d")
    if build:
        args.append("--build")
    console.print("[cyan]Starting compose project...[/cyan]")
    _run_compose(args)
    console.print("[green]Compose project is up.[/green]")


def compose_down(volumes=False):
    args = ["down"]
    if volumes:
        args.append("-v")
    console.print("[yellow]Stopping compose project...[/yellow]")
    _run_compose(args)
    console.print("[green]Compose project stopped.[/green]")


def compose_ps():
    output = _run_compose(["ps", "-a"], capture=True)
    if output.strip():
        console.print(output)
    else:
        compose_file = _find_compose_file()
        if compose_file:
            console.print(f"[yellow]No running services in '{compose_file}'.[/yellow]")
        else:
            console.print("[yellow]No compose file found in the current directory.[/yellow]")


def compose_logs(follow=False, tail=50, service=None):
    args = ["logs"]
    if follow:
        args.append("-f")
    if tail is not None:
        args.extend(["--tail", str(tail)])
    if service:
        args.append(service)
    _run_compose(args)
