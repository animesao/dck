import json
import os
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.markup import escape

from dck.container import (
    list_containers as docker_list,
    view_logs as docker_logs,
    start_container as docker_start,
    stop_container as docker_stop,
    restart_container as docker_restart,
    remove_container as docker_rm,
)
from dck.image import (
    list_images as docker_images,
    pull_image as docker_pull,
    remove_image as docker_rmi,
    export_image,
    import_image,
)
from dck.compose import compose_up, compose_down, compose_ps, compose_logs
from dck.stats import stats
from dck.doctor import doctor
from dck.create import create_interactive, run_custom
from dck.uninstall import uninstall
from dck.lang import lang_cmd
from dck.port import ports_cmd
from dck.exec import exec_container, inspect_container, console_container
from dck.update import update as update_dck
from dck.startup import show_startup_config, set_startup_command, set_startup_entrypoint, set_startup_file, clear_startup_config
from dck.manifest import deploy_manifest, destroy_manifest, show_manifest
from dck.i18n import t

console = Console()

_has_native = os.name == "posix" and os.path.exists("/proc/self/ns")


@click.group()
@click.version_option(package_name="dck")
def cli():
    """dck - container manager"""
    pass


def _native_ok():
    if not _has_native:
        console.print("[yellow]Native runtime requires Linux[/yellow]")
    return _has_native


# ── native-aware commands ──────────────────────────────────────────

@cli.command("ps")
@click.option("--running", "-r", "running_only", is_flag=True)
def ps_cmd(running_only):
    """List containers"""
    if not _native_ok():
        docker_list(not running_only)
        return

    from dck.runtime import list_containers as rt_list
    containers = rt_list(all_containers=not running_only)
    if not containers:
        console.print("[dim]No containers[/dim]")
        return

    table = Table(border_style="cyan")
    table.add_column("ID", style="bold", width=12)
    table.add_column("Name")
    table.add_column("Image")
    table.add_column("Status")
    table.add_column("Ports")

    for c in containers:
        sid = c.get("id", "")[:12]
        sports = ", ".join(f"{h}:{cpt}" for cpt, h in c.get("ports", {}).items())
        sstatus = c.get("live_status", c.get("status", "?"))
        style = "green" if sstatus == "running" else "yellow"
        table.add_row(sid, c.get("name", ""), c.get("image", ""), f"[{style}]{sstatus}[/{style}]", sports)

    console.print(table)


@cli.command("pull")
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def pull_cmd(image, tag):
    """Pull an OCI image from Docker Hub"""
    if not _native_ok():
        docker_pull(f"{image}:{tag}")
        return

    from dck.oci import pull_image as oci_pull
    try:
        with console.status(f"Pulling {image}:{tag}..."):
            result = oci_pull(image, tag, progress_callback=lambda m: console.log(f"  {m}"))
        console.print(f"[green]✓[/green] Pulled {image}:{tag}")
    except Exception as e:
        console.print(f"[red]Pull failed:[/red] {e}")


@cli.command("images")
def images_cmd():
    """List pulled images"""
    if not _native_ok():
        docker_images()
        return

    from dck.oci import list_images as oci_list
    imgs = oci_list()
    if not imgs:
        console.print("[dim]No images pulled[/dim]")
        return

    table = Table(border_style="cyan")
    table.add_column("Repository", style="bold")
    table.add_column("Tag")
    table.add_column("CMD")
    for img in imgs:
        table.add_row(img["name"], img["tag"], img["cmd"])
    console.print(table)


@cli.command("rmi")
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def rmi_cmd(image, tag):
    """Remove a pulled image"""
    if not _native_ok():
        docker_rmi(image)
        return

    from dck.oci import remove_image as oci_rm
    if oci_rm(image, tag):
        console.print(f"[green]✓[/green] Removed {image}:{tag}")
    else:
        console.print(f"[yellow]Image {image}:{tag} not found[/yellow]")


@cli.command("run")
@click.argument("image")
@click.option("--name", "-n")
@click.option("--port", "-p", multiple=True)
@click.option("--volume", "-v", multiple=True)
@click.option("--env", "-e", multiple=True)
@click.option("--ram")
@click.option("--cpu")
@click.option("--cmd", help="Command to run")
@click.option("--tag", "-t", default="latest")
def run_cmd_native(image, name, port, volume, env, ram, cpu, cmd, tag):
    """Run a container with native Linux runtime"""
    if not _native_ok():
        run_custom(image, name, ram, cpu)
        return

    from dck.oci import pull_image as oci_pull, list_images as oci_list
    from dck.runtime import Container

    existing = [i for i in oci_list() if i["name"] == image and i["tag"] == tag]
    if not existing:
        console.print(f"Pulling {image}:{tag}...")
        try:
            oci_pull(image, tag)
            existing = [i for i in oci_list() if i["name"] == image and i["tag"] == tag]
        except Exception as e:
            console.print(f"[red]Pull failed:[/red] {e}")
            return

    if not existing:
        console.print(f"[red]Image {image}:{tag} not found[/red]")
        return

    img_info = existing[0]
    rootfs = img_info["rootfs"]

    cfg_file = Path.home() / ".dck" / "images" / image.replace("/", "_") / tag / "config.json"
    image_cmd = []
    image_env = {}
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text())
            image_env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in cfg.get("config", {}).get("Env", []) if "=" in e}
            entrypoint = cfg.get("config", {}).get("Entrypoint", [])
            default_cmd = cfg.get("config", {}).get("Cmd", [])
            image_cmd = (entrypoint + default_cmd) if entrypoint else default_cmd
        except Exception:
            pass

    final_cmd = cmd.split() if cmd else image_cmd
    if not final_cmd:
        final_cmd = ["/bin/sh"]

    ports = {}
    for p in (port or []):
        parts = p.split(":")
        if len(parts) == 2:
            try:
                host_port = int(parts[0])
                rest = parts[1]
                if "/" in rest:
                    c_port, proto = rest.split("/", 1)
                else:
                    c_port = rest
                    proto = "tcp"
                ports[f"{c_port}/{proto}"] = host_port
            except ValueError:
                console.print(f"[red]Invalid port: {p}[/red]")

    volumes = {}
    for v in (volume or []):
        if ":" in v:
            h, c = v.split(":", 1)
            volumes[h] = c

    env_vars = {}
    for e in (env or []):
        if "=" in e:
            k, v = e.split("=", 1)
            env_vars[k] = v

    full_env = {**image_env, **env_vars}

    container = Container(name=name, config={
        "image": f"{image}:{tag}",
        "command": final_cmd,
        "rootfs": rootfs,
        "ports": ports,
        "volumes": volumes,
        "env": full_env,
        "ram": ram,
        "cpu": cpu,
    })

    try:
        container.create()
        console.print(f"[green]✓[/green] Created: [bold]{container.name}[/bold]")

        if ports:
            from dck.network import ensure_bridge, allocate_ip, setup_veth
            ensure_bridge()
            container_ip = allocate_ip()
            container.config["network"] = {"ip": container_ip}
            container.save_state()

        container.start()
        console.print(f"  PID: {container.config.get('pid')}")
        console.print(f"  Status: [green]running[/green]")
        console.print(f"\n  [dim]dck exec {container.name}  |  dck logs {container.name}[/dim]")

        if ports:
            from dck.network import forward_port
            ip = container.config.get("network", {}).get("ip")
            if ip:
                for c_port, h_port in ports.items():
                    c_num = c_port.split("/")[0]
                    proto = c_port.split("/")[1] if "/" in c_port else "tcp"
                    try:
                        forward_port(h_port, ip, c_num, proto)
                        console.print(f"  Port: [cyan]{h_port}:{c_num}/{proto}[/cyan]")
                    except Exception as e:
                        console.print(f"  [red]Port forward failed: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        try:
            container.remove()
        except Exception:
            pass


@cli.command("stop")
@click.argument("container")
def stop_cmd(container):
    """Stop a container"""
    if not _native_ok():
        docker_stop(container)
        return

    from dck.runtime import get_container
    r = get_container(container)
    if not r:
        console.print(f"[red]Container '{container}' not found[/red]")
        return
    c, _ = r
    try:
        c.stop()
        console.print(f"[green]✓[/green] Stopped {c.name}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


@cli.command("rm")
@click.argument("container")
@click.option("--force", "-f", is_flag=True)
def rm_cmd(container, force):
    """Remove a container"""
    if not _native_ok():
        docker_rm(container, force)
        return

    from dck.runtime import get_container
    r = get_container(container)
    if not r:
        console.print(f"[red]Container '{container}' not found[/red]")
        return
    c, _ = r
    try:
        if force:
            c.stop()
        c.remove()
        console.print(f"[green]✓[/green] Removed {c.name}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


@cli.command("exec")
@click.argument("container")
@click.argument("cmd", nargs=-1, required=True)
def exec_cmd_native(container, cmd):
    """Execute command in a running container"""
    if not _native_ok():
        exec_container(container, list(cmd))
        return

    from dck.runtime import get_container
    r = get_container(container)
    if not r:
        console.print(f"[red]Container '{container}' not found[/red]")
        return
    c, _ = r
    try:
        c.exec_run(list(cmd))
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


@cli.command("logs")
@click.argument("container")
@click.option("--tail", "-t", type=int, default=50)
@click.option("--follow", "-f", is_flag=True)
def logs_cmd(container, tail, follow):
    """View container logs"""
    if not _native_ok():
        docker_logs(container, follow, tail)
        return

    from dck.runtime import get_container
    r = get_container(container)
    if not r:
        console.print(f"[red]Container '{container}' not found[/red]")
        return
    c, _ = r
    output = c.logs(tail=tail, follow=follow)
    if output:
        console.print(output)


@cli.command("inspect")
@click.argument("container")
def inspect_cmd_native(container):
    """Show container details"""
    if not _native_ok():
        inspect_container(container)
        return

    from dck.runtime import get_container
    r = get_container(container)
    if not r:
        console.print(f"[red]Container '{container}' not found[/red]")
        return
    c, data = r

    table = Table(border_style="cyan")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        table.add_row(k, str(v))
    console.print(table)


# ── Docker SDK commands (fallback) ──────────────────────────────────

@cli.command("start")
@click.argument("container")
@click.option("--restart", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def start_cmd(container, restart):
    """Start a container"""
    docker_start(container, restart)


@cli.command("restart")
@click.argument("container")
def restart_cmd(container):
    """Restart a container"""
    docker_restart(container)


@cli.command("restart-policy")
@click.argument("container")
@click.argument("policy", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def restart_policy_cmd(container, policy):
    """Set container restart policy"""
    from dck.container import set_restart_policy
    set_restart_policy(container, policy)


@cli.command("export-image")
@click.argument("image")
@click.argument("output_path", required=False)
def export_image_cmd(image, output_path):
    """Export image to tar archive"""
    export_image(image, output_path)


@cli.command("import-image")
@click.argument("tar_path")
def import_image_cmd(tar_path):
    """Import image from tar archive"""
    import_image(tar_path)


@cli.command("resources")
@click.argument("container")
@click.option("--ram")
@click.option("--cpu")
@click.option("--restart", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def resources_cmd(container, ram, cpu, restart):
    """Update RAM/CPU limits"""
    from dck.container import update_resources
    update_resources(container, ram, cpu, restart)


@cli.command("console")
@click.argument("container")
@click.option("--logs", "-l", "mode_flag", flag_value="logs")
@click.option("--shell", "-s", "mode_flag", flag_value="shell")
@click.option("--tail", "-t", type=int, default=20)
def console_cmd(container, mode_flag, tail):
    """Attach to a container's console"""
    console_container(container, mode=mode_flag or "attach", tail=tail)


# ── aliases ─────────────────────────────────────────────────────────

@cli.command("l")
@click.argument("container")
@click.option("--follow", "-f", is_flag=True)
@click.option("--tail", "-t", type=int, default=50)
def l_alias(container, follow, tail):
    """Alias: view container logs"""
    docker_logs(container, follow, tail)


@cli.command("s")
@click.argument("container")
@click.option("--restart", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def s_alias(container, restart):
    """Alias: start a container"""
    docker_start(container, restart)


@cli.command("st")
@click.argument("container")
def st_alias(container):
    """Alias: stop a container"""
    docker_stop(container)


@cli.command("r")
@click.argument("container")
def r_alias(container):
    """Alias: restart a container"""
    docker_restart(container)


@cli.command("i")
def i_alias():
    """Alias: list Docker images"""
    docker_images()


@cli.command("e")
@click.argument("container")
@click.argument("cmd", nargs=-1)
def e_alias(container, cmd):
    """Alias: exec in container"""
    exec_container(container, list(cmd) if cmd else None)


# ── system commands ─────────────────────────────────────────────────

@cli.command("create")
@click.option("--image", "-i")
@click.option("--name", "-n")
@click.option("--ram")
@click.option("--cpu")
@click.option("--port", "-p", multiple=True)
@click.option("--env", "-e", multiple=True)
@click.option("--volume", "-v", multiple=True)
@click.option("--paper", is_flag=True)
def create_cmd(image, name, ram, cpu, port, env, volume, paper):
    """Create a container with interactive setup"""
    create_interactive(image, name, ram, cpu, port, env, volume, paper)


@cli.command("stats")
def stats_cmd():
    """Live resource monitoring"""
    stats()


@cli.command("doctor")
def doctor_cmd():
    """Check Docker installation"""
    doctor()


@cli.command("update")
def update_cmd():
    """Update dck to latest version"""
    update_dck()


@cli.command("uninstall")
def uninstall_cmd():
    """Remove dck completely"""
    uninstall()


@cli.command("startup")
@click.argument("container")
@click.option("--command", "-c", "cmd_val")
@click.option("--entrypoint", "-e", "entry_val")
@click.option("--file", "-f", "file_val")
@click.option("--clear", "-C", "clear_flag", is_flag=True)
def startup_cmd(container, cmd_val, entry_val, file_val, clear_flag):
    """Manage container startup settings"""
    if clear_flag:
        clear_startup_config(container)
    elif cmd_val:
        set_startup_command(container, cmd_val)
    elif entry_val:
        set_startup_entrypoint(container, entry_val)
    elif file_val:
        set_startup_file(container, file_val)
    else:
        show_startup_config(container)


# ── compose ─────────────────────────────────────────────────────────

@cli.group()
def compose():
    """Manage Docker Compose projects"""
    pass


@compose.command("up")
@click.option("--detach", "-d", is_flag=True)
@click.option("--build", is_flag=True)
def compose_up_cmd(detach, build):
    compose_up(detach, build)


@compose.command("down")
@click.option("--volumes", "-v", is_flag=True)
def compose_down_cmd(volumes):
    compose_down(volumes)


@compose.command("ps")
def compose_ps_cmd():
    compose_ps()


@compose.command("logs")
@click.option("--follow", "-f", is_flag=True)
@click.option("--tail", "-t", type=int, default=50)
@click.argument("service", required=False)
def compose_logs_cmd(follow, tail, service):
    compose_logs(follow, tail, service)


# ── manifest ────────────────────────────────────────────────────────

@cli.command("up")
@click.option("--force", "-f", is_flag=True)
def up_cmd(force):
    deploy_manifest()


@cli.command("down")
def down_cmd():
    destroy_manifest()


@cli.command("manifest")
def manifest_cmd():
    show_manifest()


# ── external commands ──────────────────────────────────────────────

cli.add_command(ports_cmd)
cli.add_command(lang_cmd)
