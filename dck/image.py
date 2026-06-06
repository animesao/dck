from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from docker.errors import NotFound, APIError, ImageNotFound

from dck.client import get_client

console = Console()


def list_images():
    client = get_client()
    images = client.images.list()

    if not images:
        console.print("[yellow]No images found.[/yellow]")
        return

    table = Table(title="Images", border_style="cyan")
    table.add_column("Repository", style="bold")
    table.add_column("Tag", style="blue")
    table.add_column("Image ID", style="dim")
    table.add_column("Size")
    table.add_column("Created")

    for img in images:
        repo = ", ".join(img.tags) if img.tags else "<none>:<none>"
        for tag in (img.tags or ["<none>:<none>"]):
            if ":" in tag:
                repo_name, tag_name = tag.rsplit(":", 1)
            else:
                repo_name, tag_name = tag, "latest"
            short_id = img.short_id[7:] if img.short_id.startswith("sha256:") else img.short_id[:12]
            size = _format_size(img.attrs.get("Size", 0))
            created = img.attrs.get("Created", "")[:10] if img.attrs.get("Created") else "-"
            table.add_row(repo_name, tag_name, short_id, size, created)

    console.print(table)


def _format_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size}B"
    elif bytes_size < 1024 ** 2:
        return f"{bytes_size / 1024:.1f}KB"
    elif bytes_size < 1024 ** 3:
        return f"{bytes_size / 1024 ** 2:.1f}MB"
    else:
        return f"{bytes_size / 1024 ** 3:.2f}GB"


def pull_image(image_name):
    client = get_client()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(description=f"Pulling [cyan]{image_name}[/cyan]...", total=None)
        try:
            client.images.pull(image_name)
            console.print(f"[green]Pulled[/green] image '{image_name}'")
        except APIError as e:
            console.print(f"[red]Error:[/red] {e.explanation or e}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")


def remove_image(image_name, force=False):
    client = get_client()
    try:
        client.images.remove(image_name, force=force)
        console.print(f"[red]Removed[/red] image '{image_name}'")
    except ImageNotFound:
        console.print(f"[red]Error:[/red] Image '{image_name}' not found.")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e.explanation or e}")
