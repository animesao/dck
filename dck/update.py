import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

console = Console()
REPO_URL = "https://gitlab.com/animesao/dck.git"


def _find_repo():
    candidates = [
        Path.cwd(),
        Path.home() / "dck",
        Path("/root/dck"),
    ]
    # Check if pip package dir has a .git parent
    try:
        import dck
        pkg_dir = Path(dck.__file__).resolve().parent.parent
        if (pkg_dir / ".git").exists():
            candidates.insert(0, pkg_dir)
    except Exception:
        pass

    for path in candidates:
        git_dir = path / ".git"
        if git_dir.exists():
            try:
                r = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    capture_output=True, text=True, timeout=5,
                    cwd=str(path),
                )
                if r.returncode == 0 and "dck" in r.stdout:
                    return path
            except Exception:
                pass
    return None


def update():
    console.print("[bold cyan]dck Update[/bold cyan]\n")

    repo = _find_repo()
    if not repo:
        console.print("[yellow]dck repository not found on this system.[/yellow]")
        console.print(f"Re-run the installer:\n  [bold]curl -sSL {REPO_URL}/-/raw/main/install.sh | bash[/bold]")
        return

    if not Confirm.ask(f"Update dck in [bold]{repo}[/bold]?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Git pull
    with console.status("Pulling latest source..."):
        try:
            r = subprocess.run(
                ["git", "pull"],
                capture_output=True, text=True, timeout=30,
                cwd=str(repo),
            )
            if r.returncode != 0:
                console.print(f"[red]Git pull failed:[/red] {r.stderr.strip()}")
                return
            console.print(f"[green]✓[/green] {r.stdout.strip().split(chr(10))[0]}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            return

    # Find python (venv first, then system)
    venv_python = repo / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    # Reinstall
    with console.status("Reinstalling dck..."):
        try:
            r = subprocess.run(
                [python, "-m", "pip", "install", "--no-cache-dir", "."],
                capture_output=True, text=True, timeout=120,
                cwd=str(repo),
            )
            if r.returncode != 0:
                # fallback to non-editable
                r = subprocess.run(
                    [python, "-m", "pip", "install", "--no-cache-dir", "--no-build-isolation", "."],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(repo),
                )
            if r.returncode == 0:
                console.print("[green]✓ dck updated successfully![/green]")
            else:
                console.print(f"[red]pip install failed:[/red] {r.stderr.strip()}")
                return
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            return

    # Cleanup
    for d in ["build", "dist"]:
        p = repo / d
        if p.exists():
            subprocess.run(["rm", "-rf", str(p)], capture_output=True, timeout=10)
    for egg in repo.glob("*.egg-info"):
        subprocess.run(["rm", "-rf", str(egg)], capture_output=True, timeout=10)

    console.print("\n[bold green]✓ dck is up to date![/bold green]")
