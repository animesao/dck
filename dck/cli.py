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
from dck.create import create_interactive
from dck.uninstall import uninstall
from dck.lang import lang_cmd
from dck.port import ports_cmd
from dck.exec import exec_container, inspect_container, console_container
from dck.update import update as update_dck
from dck.startup import show_startup_config, set_startup_command, set_startup_entrypoint, set_startup_file, clear_startup_config
from dck.manifest import deploy_manifest, destroy_manifest, show_manifest

console = Console()

_has_native = os.name == "posix" and os.path.exists("/proc/self/ns") and os.geteuid() == 0


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


def _try_docker_fallback():
    if _has_native:
        return False
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False


def _run_via_docker(image, tag, name, ports, volumes, env, ram, cpu,
                     hostname, user, workdir, entrypoint, restart,
                     labels, cap_add, cap_drop, privileged,
                     interactive, tty, detach, rm, read_only,
                     network, dns, pids_limit, tmpfs, cmd):
    try:
        import docker
        client = docker.from_env()
    except Exception as e:
        console.print(f"[red]Docker not available:[/red] {e}")
        return

    full_image = f"{image}:{tag}" if tag else image
    kwargs = {}

    if name:
        kwargs["name"] = name
    if ports:
        kwargs["ports"] = {c_port: int(h_port) if isinstance(h_port, str) else h_port
                          for c_port, h_port in ports.items()}
    if volumes:
        kwargs["volumes"] = {hp: {"bind": cp, "mode": "rw"}
                            for hp, cp in volumes.items()}
    if env:
        kwargs["environment"] = dict(env)
    if ram:
        kwargs["mem_limit"] = ram
    if cpu:
        kwargs["cpu_quota"] = int(float(cpu) * 100000)
        kwargs["cpu_period"] = 100000
    if hostname:
        kwargs["hostname"] = hostname
    if user:
        kwargs["user"] = user
    if workdir:
        kwargs["working_dir"] = workdir
    if entrypoint:
        kwargs["entrypoint"] = entrypoint.split() if isinstance(entrypoint, str) else entrypoint
    if restart:
        kwargs["restart_policy"] = {"Name": restart}
    if labels:
        kwargs["labels"] = {l.split("=", 1)[0]: l.split("=", 1)[1] if "=" in l else "" for l in labels}
    if cap_add:
        kwargs["cap_add"] = list(cap_add)
    if cap_drop:
        kwargs["cap_drop"] = list(cap_drop)
    if privileged:
        kwargs["privileged"] = True
    if read_only:
        kwargs["read_only"] = True
    if network:
        kwargs["network_mode"] = network
    if dns:
        kwargs["dns"] = [dns] if isinstance(dns, str) else list(dns)
    if pids_limit:
        kwargs["pids_limit"] = int(pids_limit)
    if tmpfs:
        kwargs["tmpfs"] = {t: "" for t in tmpfs}
    if rm:
        kwargs["auto_remove"] = True

    if detach:
        kwargs["detach"] = True
        container = client.containers.run(full_image, cmd, **kwargs)
        console.print(f"[green]✓[/green] Started [bold]{container.name}[/bold] ({container.short_id})")
        if ports:
            console.print(f"  Ports: {', '.join(p for p in ports)}")
    elif interactive or tty:
        kwargs["stdin_open"] = True
        kwargs["tty"] = True
        container = client.containers.run(full_image, cmd, **kwargs)
    else:
        kwargs["stdin_open"] = False
        kwargs["tty"] = False
        container = client.containers.run(full_image, cmd, **kwargs)


@click.group()
@click.version_option(package_name="dck")
def cli():
    """dck - container manager"""
    pass


# ── run (unified: native + Docker fallback) ─────────────────────────

@cli.command("run")
@click.argument("image")
@click.argument("cmd", nargs=-1)
@click.option("--name", "-n")
@click.option("--tag", default="latest", help="Image tag")
@click.option("--port", "-p", multiple=True, help="Port mapping (host:container)")
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
@click.option("--pids-limit", type=int, help="PID limit")
@click.option("--workdir", "-w", help="Working directory")
@click.option("--user", "-u", help="Username or UID")
@click.option("--read-only", is_flag=True, help="Read-only rootfs")
@click.option("--hostname", "-h", help="Container hostname")
@click.option("--network", default="bridge", help="Network mode (bridge, host, none)")
@click.option("--dns", help="DNS server")
@click.option("--entrypoint", help="Override entrypoint")
@click.option("--restart", type=click.Choice(["no", "always", "on-failure", "unless-stopped"]), help="Restart policy")
@click.option("--cap-add", multiple=True, help="Add Linux capability")
@click.option("--cap-drop", multiple=True, help="Drop Linux capability")
@click.option("--privileged", is_flag=True, help="Extended privileges")
@click.option("--tmpfs", multiple=True, help="Mount tmpfs directory")
def run_cmd(image, cmd, name, tag, port, volume, env, env_file,
            labels, interactive, tty, detach, rm, ram, cpu, pids_limit,
            workdir, user, read_only, hostname, network, dns, entrypoint,
            restart, cap_add, cap_drop, privileged, tmpfs):
    """Run a container (native Linux runtime, falls back to Docker SDK)"""

    if env_file:
        file_env = _parse_env_file(env_file)
        env = list(env or []) + [f"{k}={v}" for k, v in file_env.items()]

    # Parse env into dict
    env_dict = {}
    for e in (env or []):
        if "=" in e:
            k, v = e.split("=", 1)
            env_dict[k] = v

    # Parse ports into dict
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

    # Parse volumes into dict
    volumes = {}
    for v in (volume or []):
        if ":" in v:
            h, c = v.split(":", 1)
            volumes[h] = c

    command = list(cmd) if cmd else None

    # Try native runtime first
    if _has_native:
        try:
            _run_native(image, tag, name, ports, volumes, env_dict,
                        ram, cpu, hostname, user, workdir, entrypoint,
                        interactive, tty, detach, rm, read_only, network,
                        pids_limit, labels, cap_add, cap_drop, privileged,
                        command)
            return
        except Exception as e:
            console.print(f"[yellow]Native runtime failed, trying Docker...[/yellow] ({e})")

    # Fallback to Docker
    _run_via_docker(image, tag, name, ports, volumes, env_dict,
                    ram, cpu, hostname, user, workdir, entrypoint,
                    restart, labels, cap_add, cap_drop, privileged,
                    interactive, tty, detach, rm, read_only,
                    network, dns, pids_limit, tmpfs, command)


def _run_native(image, tag, name, ports, volumes, env_dict,
                ram, cpu, hostname, user, workdir, entrypoint,
                interactive, tty, detach, rm, read_only, network,
                pids_limit, labels, cap_add, cap_drop, privileged,
                command):
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

    img_info = existing[0]
    rootfs = img_info["rootfs"]

    img_config = {}
    cfg_file = Path.home() / ".dck" / "images" / image.replace("/", "_") / tag / "config.json"
    if cfg_file.exists():
        try:
            img_config = json.loads(cfg_file.read_text()).get("config", {})
        except Exception:
            pass

    # Build final command
    image_cmd = []
    if command:
        image_cmd = command
    else:
        entry = entrypoint.split() if entrypoint else img_config.get("Entrypoint", [])
        default_cmd = img_config.get("Cmd", [])
        image_cmd = (entry + default_cmd) if entry else default_cmd

    if not image_cmd:
        image_cmd = ["/bin/sh"]

    # Merge env (image defaults + user overrides)
    img_env = {}
    for e in img_config.get("Env", []):
        if "=" in e:
            k, v = e.split("=", 1)
            img_env[k] = v
    full_env = {**img_env, **env_dict}

    # Workdir from image or user
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
        "labels": dict(labels) if labels else {},
        "cap_add": list(cap_add) if cap_add else [],
        "cap_drop": list(cap_drop) if cap_drop else [],
        "privileged": privileged,
    }

    from dck.runtime import Container
    container = Container(name=name, config=container_config)
    container.create()
    console.print(f"[green]✓[/green] Created [bold]{container.name}[/bold]")
    container.start()

    if container.config.get("status") == "running":
        pid = container.config.get("pid")
        console.print(f"  PID: {pid}")
        console.print(f"  Status: [green]running[/green]")

        if ports:
            ip = container.config.get("network", {}).get("ip")
            console.print(f"  IP: {ip}")
            for c_port, h_port in ports.items():
                console.print(f"  Port: [cyan]{h_port}:{c_port}[/cyan]")

        console.print(f"\n  [dim]dck exec {container.name} | dck logs {container.name} | dck stop {container.name}[/dim]")

    if interactive or tty:
        # In PTY/interactive mode, _start_pty blocks until exit
        pass


# ── native-aware commands ───────────────────────────────────────────

@cli.command("ps")
@click.option("--all", "-a", "all_flag", is_flag=True, help="Show all containers")
def ps_cmd(all_flag):
    """List containers"""
    native_ok = _has_native
    if native_ok:
        try:
            from dck.runtime import list_containers as rt_list
            containers = rt_list(all_containers=all_flag)
            if containers:
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
            else:
                console.print("[dim]No native containers[/dim]")
        except Exception as e:
            console.print(f"[yellow]Native ps error: {e}[/yellow]")
            native_ok = False

    if not native_ok and _try_docker_fallback():
        docker_list(not all_flag)


@cli.command("pull")
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def pull_cmd(image, tag):
    """Pull an image from Docker Hub"""
    if ":" in image and not tag:
        image, tag_part = image.split(":", 1)
        tag = tag_part

    if _has_native:
        try:
            from dck.oci import pull_image as oci_pull
            with console.status(f"Pulling {image}:{tag}..."):
                result = oci_pull(image, tag, progress_callback=lambda m: console.log(f"  {m}"))
            console.print(f"[green]✓[/green] Pulled {image}:{tag}")
            return
        except Exception as e:
            console.print(f"[yellow]Native pull failed: {e}[/yellow]")

    docker_pull(f"{image}:{tag}")


@cli.command("images")
def images_cmd():
    """List pulled images"""
    native_ok = _has_native

    if native_ok:
        try:
            from dck.oci import list_images as oci_list
            imgs = oci_list()
            if imgs:
                table = Table(border_style="cyan")
                table.add_column("Repository", style="bold")
                table.add_column("Tag")
                table.add_column("CMD")
                for img in imgs:
                    table.add_row(img["name"], img["tag"], img["cmd"])
                console.print(table)
            else:
                console.print("[dim]No native images[/dim]")
        except Exception:
            native_ok = False

    if not native_ok:
        docker_images()


@cli.command("rmi")
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def rmi_cmd(image, tag):
    """Remove a pulled image"""
    if _has_native:
        try:
            from dck.oci import remove_image as oci_rm
            if oci_rm(image, tag):
                console.print(f"[green]✓[/green] Removed {image}:{tag}")
                return
            else:
                console.print(f"[yellow]Image not found in native store[/yellow]")
        except Exception:
            pass

    try:
        docker_rmi(image)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


@cli.command("stop")
@click.argument("container_id")
def stop_cmd(container_id):
    """Stop a container"""
    if _has_native:
        try:
            from dck.runtime import get_container
            r = get_container(container_id)
            if r:
                c, _ = r
                c.stop()
                console.print(f"[green]✓[/green] Stopped {c.name}")
                return
        except Exception:
            pass

    docker_stop(container_id)


@cli.command("rm")
@click.argument("container_id")
@click.option("--force", "-f", is_flag=True)
def rm_cmd(container_id, force):
    """Remove a container"""
    if _has_native:
        try:
            from dck.runtime import get_container
            r = get_container(container_id)
            if r:
                c, _ = r
                if force:
                    c.stop()
                c.remove()
                console.print(f"[green]✓[/green] Removed {c.name}")
                return
        except Exception:
            pass

    docker_rm(container_id, force)


@cli.command("exec")
@click.argument("container_id")
@click.argument("cmd", nargs=-1, required=True)
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode")
@click.option("--tty", "-t", is_flag=True, help="Allocate pseudo-TTY")
def exec_cmd(container_id, cmd, interactive, tty):
    """Execute command in a running container"""
    if _has_native:
        try:
            from dck.runtime import get_container
            r = get_container(container_id)
            if r:
                c, _ = r
                c.exec_run(list(cmd), interactive=interactive or tty, tty=tty)
                return
        except Exception as e:
            console.print(f"[yellow]Native exec failed: {e}[/yellow]")

    exec_container(container_id, list(cmd))


@cli.command("logs")
@click.argument("container_id")
@click.option("--tail", "-t", type=int, default=50)
@click.option("--follow", "-f", is_flag=True)
def logs_cmd(container_id, tail, follow):
    """View container logs"""
    if _has_native:
        try:
            from dck.runtime import get_container
            r = get_container(container_id)
            if r:
                c, _ = r
                output = c.logs(tail=tail, follow=follow)
                if output:
                    console.print(output)
                return
        except Exception:
            pass

    docker_logs(container_id, follow, tail)


@cli.command("inspect")
@click.argument("container_id")
def inspect_cmd(container_id):
    """Show container details"""
    if _has_native:
        try:
            from dck.runtime import get_container
            r = get_container(container_id)
            if r:
                c, data = r
                table = Table(border_style="cyan")
                table.add_column("Key", style="bold")
                table.add_column("Value")
                for k, v in data.items():
                    if isinstance(v, (dict, list)):
                        v = json.dumps(v)
                    table.add_row(k, str(v))
                console.print(table)
                return
        except Exception:
            pass

    inspect_container(container_id)


@cli.command("start")
@click.argument("container_id")
@click.option("--restart", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def start_cmd(container_id, restart):
    """Start a container (Docker only)"""
    docker_start(container_id, restart)


@cli.command("restart")
@click.argument("container_id")
def restart_cmd(container_id):
    """Restart a container (Docker only)"""
    docker_restart(container_id)


@cli.command("restart-policy")
@click.argument("container_id")
@click.argument("policy", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def restart_policy_cmd(container_id, policy):
    """Set container restart policy (Docker only)"""
    from dck.container import set_restart_policy
    set_restart_policy(container_id, policy)


@cli.command("export-image")
@click.argument("image")
@click.argument("output_path", required=False)
def export_image_cmd(image, output_path):
    """Export image to tar archive (Docker only)"""
    export_image(image, output_path)


@cli.command("import-image")
@click.argument("tar_path")
def import_image_cmd(tar_path):
    """Import image from tar archive (Docker only)"""
    import_image(tar_path)


@cli.command("resources")
@click.argument("container_id")
@click.option("--ram")
@click.option("--cpu")
@click.option("--restart", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def resources_cmd(container_id, ram, cpu, restart):
    """Update RAM/CPU limits (Docker only)"""
    from dck.container import update_resources
    update_resources(container_id, ram, cpu, restart)


@cli.command("console")
@click.argument("container_id")
@click.option("--logs", "-l", "mode_flag", flag_value="logs")
@click.option("--shell", "-s", "mode_flag", flag_value="shell")
@click.option("--tail", "-t", type=int, default=20)
def console_cmd(container_id, mode_flag, tail):
    """Attach to a container's console (Docker only)"""
    console_container(container_id, mode=mode_flag or "attach", tail=tail)


# ── aliases (Docker SDK) ────────────────────────────────────────────

@cli.command("l")
@click.argument("container_id")
@click.option("--follow", "-f", is_flag=True)
@click.option("--tail", "-t", type=int, default=50)
def l_alias(container_id, follow, tail):
    """Alias: view logs"""
    docker_logs(container_id, follow, tail)


@cli.command("s")
@click.argument("container_id")
@click.option("--restart", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def s_alias(container_id, restart):
    """Alias: start"""
    docker_start(container_id, restart)


@cli.command("st")
@click.argument("container_id")
def st_alias(container_id):
    """Alias: stop"""
    docker_stop(container_id)


@cli.command("r")
@click.argument("container_id")
def r_alias(container_id):
    """Alias: restart"""
    docker_restart(container_id)


@cli.command("i")
def i_alias():
    """Alias: list images"""
    docker_images()


@cli.command("e")
@click.argument("container_id")
@click.argument("cmd", nargs=-1)
def e_alias(container_id, cmd):
    """Alias: exec"""
    exec_container(container_id, list(cmd) if cmd else None)


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
    """Live resource monitoring (Docker only)"""
    stats()


@cli.command("doctor")
def doctor_cmd():
    """Check system setup"""
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
@click.argument("container_id")
@click.option("--command", "-c", "cmd_val")
@click.option("--entrypoint", "-e", "entry_val")
@click.option("--file", "-f", "file_val")
@click.option("--clear", "-C", "clear_flag", is_flag=True)
def startup_cmd(container_id, cmd_val, entry_val, file_val, clear_flag):
    """Manage container startup settings (Docker only)"""
    if clear_flag:
        clear_startup_config(container_id)
    elif cmd_val:
        set_startup_command(container_id, cmd_val)
    elif entry_val:
        set_startup_entrypoint(container_id, entry_val)
    elif file_val:
        set_startup_file(container_id, file_val)
    else:
        show_startup_config(container_id)


# ── compose ─────────────────────────────────────────────────────────

@cli.group()
def compose():
    """Manage Docker Compose projects (Docker only)"""
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
