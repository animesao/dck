import json
import os
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from dck.doctor import doctor
from dck.create import create_interactive
from dck.uninstall import uninstall
from dck.update import update as update_dck

console = Console()


def _check_native():
    ok = os.name == "posix" and os.path.exists("/proc/self/ns") and os.geteuid() == 0
    if not ok:
        console.print("[red]Native runtime requires Linux with root (or CAP_SYS_ADMIN)[/red]")
        raise SystemExit(1)
    return ok


# ── helpers ─────────────────────────────────────────────────────────

def _parse_env_file(env_file):
    result = {}
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    result[k.strip()] = v.strip()
    except Exception as e:
        console.print(f"[red]Error reading env file:[/red] {e}")
    return result


def _pull_image(image, tag):
    from dck.oci import pull_image as oci_pull, list_images as oci_list

    existing = [i for i in oci_list() if i["name"] == image and i["tag"] == tag]
    if not existing:
        console.print(f"Pulling [cyan]{image}:{tag}[/cyan]...")
        try:
            oci_pull(image, tag, progress_callback=lambda m: console.log(f"  {m}"))
            existing = [i for i in oci_list() if i["name"] == image and i["tag"] == tag]
        except Exception as e:
            raise RuntimeError(f"Pull failed: {e}")
    if not existing:
        raise RuntimeError(f"Image {image}:{tag} not found")
    return existing[0]


def _load_image_config(image, tag):
    cfg_file = Path.home() / ".dck" / "images" / image.replace("/", "_") / tag / "config.json"
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text()).get("config", {})
        except Exception:
            pass
    return {}


# ── CLI group ───────────────────────────────────────────────────────

@click.group()
@click.version_option(package_name="dck")
def cli():
    """dck - контейнерный рантайм (чистый Linux, без Docker)"""


# ── run ─────────────────────────────────────────────────────────────

@cli.command("run")
@click.argument("image")
@click.argument("cmd", nargs=-1)
@click.option("--name", "-n", help="Container name")
@click.option("--tag", default="latest", help="Image tag")
@click.option("--port", "-p", multiple=True, help="Port mapping (host:container[/proto])")
@click.option("--volume", "-v", multiple=True, help="Volume mount (host:container)")
@click.option("--env", "-e", multiple=True, help="Environment variable (KEY=value)")
@click.option("--env-file", help="Read environment from file")
@click.option("--label", "-l", "labels", multiple=True, help="Add metadata (KEY=value)")
@click.option("--interactive", "-i", is_flag=True, help="Keep STDIN open")
@click.option("--tty", "-t", is_flag=True, help="Allocate pseudo-TTY")
@click.option("--detach", "-d", is_flag=True, help="Run in background")
@click.option("--rm", is_flag=True, help="Auto-remove on exit")
@click.option("--ram", help="Memory limit (512m, 2g)")
@click.option("--cpu", help="CPU limit (0.5, 2)")
@click.option("--pids-limit", type=int, default=1000, help="PID limit")
@click.option("--workdir", "-w", help="Working directory")
@click.option("--user", "-u", help="Username or UID")
@click.option("--read-only", is_flag=True, help="Read-only rootfs")
@click.option("--hostname", "-h", help="Container hostname")
@click.option("--entrypoint", help="Override entrypoint")
@click.option("--restart", type=click.Choice(["no", "always", "on-failure", "unless-stopped"]),
              default="no", help="Restart policy")
@click.option("--cap-add", multiple=True, help="Add Linux capability")
@click.option("--cap-drop", multiple=True, help="Drop Linux capability")
@click.option("--privileged", is_flag=True, help="Extended privileges")
def run_cmd(image, cmd, name, tag, port, volume, env, env_file,
            labels, interactive, tty, detach, rm, ram, cpu, pids_limit,
            workdir, user, read_only, hostname, entrypoint,
            restart, cap_add, cap_drop, privileged):
    """Run a container using native Linux runtime"""
    _check_native()

    if ":" in image:
        image, tag = image.split(":", 1)

    if env_file:
        file_env = _parse_env_file(env_file)
        env = list(env or []) + [f"{k}={v}" for k, v in file_env.items()]

    env_dict = {}
    for e in (env or []):
        if "=" in e:
            k, v = e.split("=", 1)
            env_dict[k] = v

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

    command = list(cmd) if cmd else None

    try:
        img_info = _pull_image(image, tag)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    rootfs = img_info["rootfs"]
    img_config = _load_image_config(image, tag)

    if command:
        image_cmd = command
    else:
        entry = entrypoint.split() if entrypoint else img_config.get("Entrypoint", [])
        default_cmd = img_config.get("Cmd", [])
        image_cmd = (entry + default_cmd) if entry else default_cmd

    if not image_cmd:
        image_cmd = ["/bin/sh"]

    img_env = {}
    for e in img_config.get("Env", []):
        if "=" in e:
            k, v = e.split("=", 1)
            img_env[k] = v
    full_env = {**img_env, **env_dict}

    final_workdir = workdir or img_config.get("WorkingDir", "")

    container_config = {
        "image": f"{image}:{tag}",
        "command": image_cmd,
        "rootfs": rootfs,
        "ports": ports,
        "volumes": volumes,
        "env": full_env,
        "ram": ram,
        "cpu": cpu,
        "hostname": hostname,
        "user": user,
        "workdir": final_workdir,
        "entrypoint": entrypoint,
        "tty": tty or interactive,
        "interactive": interactive,
        "detach": detach,
        "rm": rm,
        "read_only": read_only,
        "pids_limit": pids_limit,
        "restart": restart,
        "labels": dict(l.split("=", 1) for l in (labels or []) if "=" in l),
        "cap_add": list(cap_add),
        "cap_drop": list(cap_drop),
        "privileged": privileged,
    }

    from dck.runtime import Container
    container = Container(name=name, config=container_config)
    container.create()
    console.print(f"[green]✓[/green] Created [bold]{container.name}[/bold]")
    try:
        container.start()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        log_file = container.config.get("log_file", "")
        if log_file and Path(log_file).exists():
            try:
                logs = Path(log_file).read_text()
                for line in logs.strip().split("\n")[-3:]:
                    console.print(f"  [dim]{line}[/dim]")
            except Exception:
                pass
        container.remove()
        raise SystemExit(1)

    if container.config.get("status") == "running":
        pid = container.config.get("pid")
        console.print(f"  PID: {pid}")
        if ports:
            ip = container.config.get("network", {}).get("ip")
            if ip:
                console.print(f"  IP: {ip}")
            for c_port, h_port in ports.items():
                console.print(f"  Port: [cyan]{h_port}:{c_port}[/cyan]")
        console.print(f"\n  [dim]dck exec {container.name}[/dim]")
        console.print(f"  [dim]dck logs {container.name}[/dim]")
        console.print(f"  [dim]dck stop {container.name}[/dim]")


# ── ps ──────────────────────────────────────────────────────────────

@cli.command("ps")
@click.option("--all", "-a", "all_flag", is_flag=True)
def ps_cmd(all_flag):
    """List containers"""
    _check_native()

    from dck.runtime import list_containers as rt_list
    containers = rt_list(all_containers=all_flag)
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
        table.add_row(sid, c.get("name", ""), c.get("image", ""),
                      f"[{style}]{sstatus}[/{style}]", sports)

    console.print(table)


# ── pull ────────────────────────────────────────────────────────────

@cli.command("pull")
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def pull_cmd(image, tag):
    """Pull an OCI image from Docker Hub"""
    _check_native()

    if ":" in image:
        image, tag = image.split(":", 1)

    from dck.oci import pull_image as oci_pull
    try:
        with console.status(f"Pulling {image}:{tag}..."):
            oci_pull(image, tag, progress_callback=lambda m: console.log(f"  {m}"))
        console.print(f"[green]✓[/green] Pulled {image}:{tag}")
    except Exception as e:
        console.print(f"[red]Pull failed:[/red] {e}")
        raise SystemExit(1)


# ── images ──────────────────────────────────────────────────────────

@cli.command("images")
def images_cmd():
    """List pulled images"""
    _check_native()

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


# ── rmi ─────────────────────────────────────────────────────────────

@cli.command("rmi")
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def rmi_cmd(image, tag):
    """Remove a pulled image"""
    _check_native()

    from dck.oci import remove_image as oci_rm
    if oci_rm(image, tag):
        console.print(f"[green]✓[/green] Removed {image}:{tag}")
    else:
        console.print(f"[yellow]Image {image}:{tag} not found[/yellow]")


# ── start ───────────────────────────────────────────────────────────

@cli.command("start")
@click.argument("container_id")
def start_cmd(container_id):
    """Start a stopped container"""
    _check_native()

    from dck.runtime import get_container
    r = get_container(container_id)
    if not r:
        console.print(f"[red]Container '{container_id}' not found[/red]")
        raise SystemExit(1)

    c, _ = r
    try:
        c.start_existing()
        console.print(f"[green]✓[/green] Started {c.name} (PID: {c.config.get('pid')})")
    except Exception as e:
        console.print(f"[red]Failed to start:[/red] {e}")
        raise SystemExit(1)


# ── stop ────────────────────────────────────────────────────────────

@cli.command("stop")
@click.argument("container_id")
@click.option("--time", "-t", "timeout", type=int, default=10, help="Seconds to wait before SIGKILL")
def stop_cmd(container_id, timeout):
    """Stop a running container"""
    _check_native()

    from dck.runtime import get_container
    r = get_container(container_id)
    if not r:
        console.print(f"[red]Container '{container_id}' not found[/red]")
        raise SystemExit(1)

    c, _ = r
    try:
        c.stop(timeout=timeout)
        console.print(f"[green]✓[/green] Stopped {c.name}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


# ── restart ─────────────────────────────────────────────────────────

@cli.command("restart")
@click.argument("container_id")
@click.option("--time", "-t", "timeout", type=int, default=10)
def restart_cmd(container_id, timeout):
    """Restart a container"""
    _check_native()

    from dck.runtime import get_container
    r = get_container(container_id)
    if not r:
        console.print(f"[red]Container '{container_id}' not found[/red]")
        raise SystemExit(1)

    c, _ = r
    try:
        c.restart(timeout=timeout)
        console.print(f"[green]✓[/green] Restarted {c.name} (PID: {c.config.get('pid')})")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


# ── rm ──────────────────────────────────────────────────────────────

@cli.command("rm")
@click.argument("container_id")
@click.option("--force", "-f", is_flag=True)
def rm_cmd(container_id, force):
    """Remove a container"""
    _check_native()

    from dck.runtime import get_container
    r = get_container(container_id)
    if not r:
        console.print(f"[red]Container '{container_id}' not found[/red]")
        raise SystemExit(1)

    c, _ = r
    try:
        if force:
            c.stop()
        c.remove()
        console.print(f"[green]✓[/green] Removed {c.name}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


# ── exec ────────────────────────────────────────────────────────────

@cli.command("exec")
@click.argument("container_id")
@click.argument("cmd", nargs=-1, required=True)
@click.option("--interactive", "-i", is_flag=True)
@click.option("--tty", "-t", is_flag=True)
@click.option("--detach", "-d", is_flag=True)
def exec_cmd(container_id, cmd, interactive, tty, detach):
    """Execute a command in a running container"""
    _check_native()

    from dck.runtime import get_container
    r = get_container(container_id)
    if not r:
        console.print(f"[red]Container '{container_id}' not found[/red]")
        raise SystemExit(1)

    c, _ = r
    if c.get_status() != "running":
        console.print(f"[red]Container '{container_id}' is not running[/red]")
        raise SystemExit(1)

    try:
        c.exec_run(list(cmd), interactive=interactive or tty, tty=tty)
    except Exception as e:
        console.print(f"[red]Exec error:[/red] {e}")
        raise SystemExit(1)


@cli.command("ssh")
@click.argument("container_id")
@click.argument("shell", nargs=-1)
@click.option("--user", "-u", default="root")
def ssh_cmd(container_id, shell, user):
    """SSH into a container (alias for exec -it)"""
    cmd = list(shell) if shell else ["/bin/sh", "-c", f"exec su - {user} 2>/dev/null || exec /bin/sh"]
    ctx = click.get_current_context()
    ctx.invoke(exec_cmd, container_id=container_id, cmd=tuple(cmd), interactive=True, tty=True, detach=False)


# ── logs ────────────────────────────────────────────────────────────

@cli.command("logs")
@click.argument("container_id")
@click.option("--tail", "-t", type=int, default=50)
@click.option("--follow", "-f", is_flag=True)
def logs_cmd(container_id, tail, follow):
    """View container logs"""
    _check_native()

    from dck.runtime import get_container
    r = get_container(container_id)
    if not r:
        console.print(f"[red]Container '{container_id}' not found[/red]")
        raise SystemExit(1)

    c, _ = r
    output = c.logs(tail=tail, follow=follow)
    if output:
        console.print(output)


# ── inspect ─────────────────────────────────────────────────────────

@cli.command("inspect")
@click.argument("container_id")
def inspect_cmd(container_id):
    """Show container details"""
    _check_native()

    from dck.runtime import get_container
    r = get_container(container_id)
    if not r:
        console.print(f"[red]Container '{container_id}' not found[/red]")
        raise SystemExit(1)

    c, data = r
    table = Table(border_style="cyan")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        table.add_row(k, str(v))
    console.print(table)


# ── create (interactive, with Paper) ────────────────────────────────

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


# ── system commands ─────────────────────────────────────────────────

@cli.command("doctor")
def doctor_cmd():
    """Check system for native runtime compatibility"""
    doctor()


@cli.command("update")
def update_cmd():
    """Update dck to latest version"""
    update_dck()


@cli.command("uninstall")
def uninstall_cmd():
    """Remove dck completely"""
    uninstall()



