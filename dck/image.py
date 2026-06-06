from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import os
from docker.errors import ImageNotFound


from dck.client import get_client

console = Console()


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
