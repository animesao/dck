import os
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()


def uninstall():
    """Remove dck completely (package, files, symlinks)"""
    console.print("[bold red]dck Uninstall[/bold red]")
    console.print("This will remove:")
    console.print("  - pip package dck")
    console.print("  - dck binary/symlink from PATH")
    console.print("  - cloned repository directory (optional)")
    console.print()

    if not Confirm.ask("Proceed with uninstall?", default=False):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # 1. Pip uninstall
    console.print("\n[bold]1. Removing pip package...[/bold]")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "dck", "-y"],
            capture_output=True, text=True,
        )
        if "not installed" in result.stdout.lower():
            console.print("  [dim]dck not found in pip[/dim]")
        else:
            console.print("  [green]✓[/green] pip package removed")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] pip uninstall error: {e}")

    # 2. Remove symlinks/binaries from PATH
    console.print("\n[bold]2. Removing dck from PATH...[/bold]")
    found = False
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for path_dir in path_dirs:
        candidate = os.path.join(path_dir, "dck")
        if os.path.isfile(candidate) or os.path.islink(candidate):
            try:
                os.remove(candidate)
                console.print(f"  [green]✓[/green] Removed {candidate}")
                found = True
            except Exception as e:
                console.print(f"  [yellow]⚠[/yellow] Cannot remove {candidate}: {e}")
    if not found:
        console.print("  [dim]No dck binary found in PATH[/dim]")

    # 3. Also check /usr/local/bin and common locations
    for common in ["/usr/local/bin/dck", "/usr/bin/dck"]:
        if os.path.exists(common):
            try:
                os.remove(common)
                console.print(f"  [green]✓[/green] Removed {common}")
            except Exception:
                pass

    # 4. Remove repo directory
    console.print("\n[bold]3. Removing source directory...[/bold]")
    console.print("  Where was dck cloned? Common locations:")
    console.print("    [1] ~/dck")
    console.print("    [2] Current directory")
    console.print("    [3] Specify another path")
    console.print("    [4] Skip (keep files)")

    choice = Prompt.ask("  Choose", default="4")

    repo_path = None
    if choice == "1":
        repo_path = os.path.expanduser("~/dck")
    elif choice == "2":
        repo_path = os.getcwd()
    elif choice == "3":
        repo_path = Prompt.ask("  Enter full path")
    else:
        console.print("  [dim]Skipped[/dim]")

    if repo_path and os.path.isdir(repo_path):
        git_dir = os.path.join(repo_path, ".git")
        if os.path.isdir(git_dir) or Confirm.ask(f"  Remove {repo_path}?", default=True):
            try:
                shutil.rmtree(repo_path)
                console.print(f"  [green]✓[/green] Removed {repo_path}")
            except Exception as e:
                console.print(f"  [red]✗[/red] Cannot remove {repo_path}: {e}")
                console.print(f"  [dim]Try: rm -rf {repo_path}[/dim]")
        else:
            console.print("  [dim]Skipped[/dim]")
    elif repo_path:
        console.print("  [dim]Directory not found[/dim]")

    # 5. Remove venv separately if not in repo
    for venv_path in ["./venv", os.path.expanduser("~/dck/venv")]:
        if os.path.isdir(venv_path):
            try:
                shutil.rmtree(venv_path)
                console.print(f"  [green]✓[/green] Removed venv: {venv_path}")
            except Exception:
                pass

    console.print("\n[bold green]✓ dck uninstalled![/bold green]")
