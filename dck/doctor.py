import sys
import subprocess
import shutil

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

console = Console()


def doctor():
    console.print("[bold cyan]dck Doctor[/bold cyan] - Docker Diagnostics\n")

    docker_found = shutil.which("docker")
    compose_found = shutil.which("docker") and _check_compose()

    table = Table(border_style="cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    if docker_found:
        version = _get_docker_version()
        table.add_row("Docker CLI", Text("✓", style="green"), version or "installed")
    else:
        table.add_row("Docker CLI", Text("✗", style="red"), "not found")

    if compose_found:
        table.add_row("Docker Compose", Text("✓", style="green"), "available")
    elif docker_found:
        table.add_row("Docker Compose", Text("✗", style="red"), "not available (try 'docker compose plugin')")
    else:
        table.add_row("Docker Compose", Text("✗", style="red"), "Docker not found")

    if docker_found:
        daemon_ok = _check_daemon()
        if daemon_ok:
            table.add_row("Docker Daemon", Text("✓", style="green"), "running")
        else:
            table.add_row("Docker Daemon", Text("✗", style="red"), "not running or not accessible")

    console.print(table)
    console.print()

    if not docker_found:
        _show_install_instructions()


def _check_compose():
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _get_docker_version():
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Client.Version}}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return f"version {result.stdout.strip()}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _check_daemon():
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _show_install_instructions():
    console.print(Panel.fit(
        "[bold]Docker is not installed.[/bold]\n\n"
        "Install Docker to use dck:\n\n"
        "[cyan]Windows:[/cyan]\n"
        "  1. Download Docker Desktop from https://www.docker.com/products/docker-desktop/\n"
        "  2. Or use winget: [bold]winget install Docker.DockerDesktop[/bold]\n\n"
        "[cyan]macOS:[/cyan]\n"
        "  1. Download Docker Desktop from https://www.docker.com/products/docker-desktop/\n"
        "  2. Or use Homebrew: [bold]brew install --cask docker[/bold]\n\n"
        "[cyan]Linux (Ubuntu/Debian):[/cyan]\n"
        "  curl -fsSL https://get.docker.com | sh\n\n"
        "[cyan]Linux (Arch):[/cyan]\n"
        "  sudo pacman -S docker\n\n"
        "After installation, restart your terminal and run [bold]dck doctor[/bold] again.",
        title="Installation Instructions",
        border_style="cyan"
    ))
