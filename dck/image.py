from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import os
from docker.errors import ImageNotFound, APIError


from dck.client import get_client

console = Console()


def list_images():
    """List Docker images."""
    client = get_client()
    images = client.images.list()

    if not images:
        console.print("[yellow]No images found.[/yellow]")
        return

    table = Table(title="Images")
    table.add_column("Repository", style="bold")
    table.add_column("Tag")
    table.add_column("Image ID", style="dim")
    table.add_column("Created")
    table.add_column("Size")

    for img in images:
        tags = img.tags
        if tags:
            for tag in tags:
                if ':' in tag:
                    repo, tag_name = tag.rsplit(':', 1)
                else:
                    repo, tag_name = tag, 'latest'
                created = img.attrs.get('Created', '')[:19].replace('T', ' ')
                size = _format_size(img.attrs.get('Size', 0))
                table.add_row(repo, tag_name, img.short_id, created, size)
        else:
            created = img.attrs.get('Created', '')[:19].replace('T', ' ')
            size = _format_size(img.attrs.get('Size', 0))
            table.add_row("<none>", "<none>", img.short_id, created, size)

    console.print(table)


def _format_size(size_bytes):
    """Format size in bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}PB"


def pull_image(image_name):
    """Pull an image from registry."""
    client = get_client()
    try:
        console.print(f"[blue]Pulling[/blue] image '{image_name}'...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Pulling {image_name}", total=None)
            image = client.images.pull(image_name)
            progress.update(task, completed=True)
        console.print(f"[green]Pulled[/green] image '{image_name}' ({image.short_id})")
    except ImageNotFound:
        console.print(f"[red]Error:[/red] Image '{image_name}' not found in registry.")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e.explanation or e}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


def remove_image(image_name, force=False):
    """Remove an image."""
    client = get_client()
    try:
        client.images.remove(image_name, force=force)
        console.print(f"[red]Removed[/red] image '{image_name}'")
    except ImageNotFound:
        console.print(f"[red]Error:[/red] Image '{image_name}' not found.")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e.explanation or e}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


def export_image(image_name, output_path=None):
    """Export a Docker image to a tar archive.

    If ``output_path`` is omitted, the image name (with ':' replaced by '_')
    and a ``.tar`` suffix are used in the current working directory.
    """
    client = get_client()
    try:
        image = client.images.get(image_name)
    except ImageNotFound:
        console.print(f"[red]Error:[/red] Image '{image_name}' not found.")
        return
    if not output_path:
        safe_name = image_name.replace(':', '_')
        output_path = f"{safe_name}.tar"
    # Ensure directory exists
    dir_name = os.path.dirname(os.path.abspath(output_path))
    if dir_name and not os.path.isdir(dir_name):
        os.makedirs(dir_name, exist_ok=True)
    try:
        with open(output_path, "wb") as f:
            for chunk in image.save(named=True):
                f.write(chunk)
        console.print(f"[green]Exported[/green] image '{image_name}' to '{output_path}'")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


def import_image(tar_path):
    """Import a Docker image from a tar archive created by ``export_image``.
    """
    client = get_client()
    if not os.path.isfile(tar_path):
        console.print(f"[red]Error:[/red] File '{tar_path}' does not exist.")
        return
    try:
        with open(tar_path, "rb") as f:
            data = f.read()
        result = client.images.load(data)
        # ``load`` returns a list of dicts with a ``stream`` key containing messages
        if isinstance(result, list):
            msgs = []
            for entry in result:
                stream = entry.get('stream')
                if stream:
                    msgs.append(stream.strip())
            console.print(f"[green]Imported[/green] image(s): {', '.join(msgs)}")
        else:
            console.print(f"[green]Imported[/green] image from '{tar_path}'")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
