import os
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from dck.runtime import (
    Container, list_containers, get_container,
    pull_image, list_images, remove_image,
    doctor,
)

console = Console()


def _check():
    if os.name != "posix" or not os.path.exists("/proc/self/ns") or os.geteuid() != 0:
        console.print("[red]Need Linux + root[/red]")
        raise SystemExit(1)


def _ext_ip(external_ip=None):
    if external_ip:
        return external_ip
    v = os.environ.get("DCK_EXTERNAL_IP")
    if v:
        return v
    try:
        r = __import__("subprocess").run(["hostname", "-I"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            return r.stdout.strip().split()[0]
    except Exception:
        pass
    return None


# ── CLI ──────────────────────────────────────────────────────────────

@click.group()
@click.version_option(package_name="dck")
def cli():
    pass


# ── pull ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def pull(image, tag):
    """Pull image from Docker Hub"""
    _check()
    if ":" in image:
        image, tag = image.split(":", 1)
    try:
        with console.status(f"Pulling {image}:{tag}..."):
            pull_image(image, tag, progress_callback=lambda m: console.log(f"  {m}"))
        console.print(f"[green]✓[/green] Pulled {image}:{tag}")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


# ── images ───────────────────────────────────────────────────────────

@cli.command()
def images():
    """List pulled images"""
    _check()
    imgs = list_images()
    if not imgs:
        console.print("[dim]No images[/dim]")
        return
    t = Table(border_style="cyan")
    t.add_column("Repository", style="bold")
    t.add_column("Tag")
    t.add_column("CMD")
    for img in imgs:
        t.add_row(img["name"], img["tag"], img["cmd"])
    console.print(t)


# ── rmi ──────────────────────────────────────────────────────────────

@cli.command()
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def rmi(image, tag):
    """Remove image"""
    _check()
    if remove_image(image, tag):
        console.print(f"[green]✓[/green] Removed {image}:{tag}")
    else:
        console.print(f"[yellow]Not found[/yellow]")


# ── run ──────────────────────────────────────────────────────────────

@cli.command()
@click.argument("image")
@click.argument("cmd", nargs=-1)
@click.option("--name", "-n", help="Container name")
@click.option("--tag", default="latest")
@click.option("--port", "-p", multiple=True, help="host:container[/proto]")
@click.option("--volume", "-v", multiple=True, help="host:container")
@click.option("--env", "-e", multiple=True, help="KEY=VALUE")
@click.option("--env-file", help="Read env from file")
@click.option("--interactive", "-i", is_flag=True)
@click.option("--tty", "-t", is_flag=True)
@click.option("--detach", "-d", is_flag=True)
@click.option("--rm", is_flag=True)
@click.option("--ram", help="Memory (512m, 2g)")
@click.option("--cpu", help="CPU cores (0.5, 2)")
@click.option("--workdir", "-w", help="Working dir")
@click.option("--hostname", "-h", help="Hostname")
@click.option("--entrypoint", help="Override entrypoint")
@click.option("--external-ip", help="External IP for port display")
@click.option("--restart", type=click.Choice(["no", "always", "on-failure"]), default="no")
def run(image, cmd, name, tag, port, volume, env, env_file,
        interactive, tty, detach, rm, ram, cpu, workdir, hostname,
        entrypoint, external_ip, restart):
    """Run container"""
    _check()

    if ":" in image:
        image, tag = image.split(":", 1)

    # env
    envd = {}
    if env_file:
        try:
            for line in Path(env_file).read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    envd[k.strip()] = v.strip()
        except Exception as e:
            console.print(f"[red]env-file: {e}[/red]")

    for e in (env or []):
        if "=" in e:
            k, v = e.split("=", 1)
            envd[k] = v

    # ports
    ports = {}
    for p in (port or []):
        parts = p.split(":")
        if len(parts) == 2:
            try:
                hp = int(parts[0])
                rest = parts[1]
                cp = rest
                proto = "tcp"
                if "/" in rest:
                    cp, proto = rest.split("/", 1)
                ports[f"{cp}/{proto}"] = hp
            except ValueError:
                console.print(f"[red]Bad port: {p}[/red]")

    # volumes
    vols = {}
    for v in (volume or []):
        if ":" in v:
            h, c = v.split(":", 1)
            vols[h] = c

    # pull
    try:
        img = pull_image(image, tag,
                         progress_callback=lambda m: console.log(f"  {m}") if detach or not tty else None)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    rootfs = img["rootfs"]

    # image config for defaults
    img_cfg = {}
    cf = Path.home() / ".dck" / "images" / image.replace("/", "_") / tag / "config.json"
    if cf.exists():
        try:
            img_cfg = json.loads(cf.read_text()).get("config", {})
        except Exception:
            pass

    # cmd
    if cmd:
        image_cmd = list(cmd)
    else:
        ep = entrypoint.split() if entrypoint else img_cfg.get("Entrypoint", [])
        dc = img_cfg.get("Cmd", [])
        image_cmd = (ep + dc) if ep else dc
    if not image_cmd:
        image_cmd = ["/bin/sh"]

    img_env = {}
    for e in img_cfg.get("Env", []):
        if "=" in e:
            k, v = e.split("=", 1)
            img_env[k] = v
    img_env.update(envd)

    cfg = {
        "image": f"{image}:{tag}",
        "cmd": image_cmd,
        "rootfs": rootfs,
        "ports": ports,
        "volumes": vols,
        "env": img_env,
        "ram": ram,
        "cpu": cpu,
        "hostname": hostname or "",
        "workdir": workdir or img_cfg.get("WorkingDir", ""),
        "entrypoint": entrypoint or "",
        "tty": tty or interactive,
        "interactive": interactive,
        "detach": detach,
        "rm": rm,
        "restart": restart,
    }

    c = Container(name=name, config=cfg)
    c.create()
    console.print(f"[green]✓[/green] {c.name}")

    try:
        c.start()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        lf = c.cfg.get("log", "")
        if lf and Path(lf).exists():
            for line in Path(lf).read_text().strip().split("\n")[-3:]:
                console.print(f"  [dim]{line}[/dim]")
        c.remove()
        raise SystemExit(1)

    if c.status() == "running":
        pid = c.cfg.get("pid")
        if not interactive and not tty:
            console.print(f"  PID: {pid}")
        ip = _ext_ip(external_ip)
        for cp, hp in ports.items():
            cn = cp.split("/")[0]
            proto = cp.split("/")[1] if "/" in cp else "tcp"
            line = f"  [cyan]{hp}:{cn}/{proto}[/cyan]"
            if ip and proto == "tcp":
                line += f"  [dim]http://{ip}:{hp}[/dim]"
            console.print(line)

        # UFW
        if ports:
            try:
                r = __import__("subprocess").run(["ufw", "status"], capture_output=True, text=True, timeout=5)
                if r.returncode == 0 and "active" in r.stdout.lower():
                    for cp, hp in ports.items():
                        if str(hp) != "22":
                            proto = cp.split("/")[1] if "/" in cp else "tcp"
                            __import__("subprocess").run(["ufw", "allow", f"{hp}/{proto}"],
                                                         capture_output=True, timeout=10)
                            console.print(f"  UFW: [green]opened {hp}/{proto}[/green]")
                    __import__("subprocess").run(["ufw", "allow", "22/tcp"], capture_output=True, timeout=10)
            except Exception:
                pass

        if not interactive and not tty:
            console.print(f"\n  [dim]exec {c.name}[/dim]")
            console.print(f"  [dim]logs {c.name}[/dim]")
            console.print(f"  [dim]stop {c.name}[/dim]")


# ── ps ───────────────────────────────────────────────────────────────

@cli.command("ps")
@click.option("--all", "-a", "all_flag", is_flag=True)
def ps_cmd(all_flag):
    """List containers"""
    _check()
    cs = list_containers(all_=all_flag)
    if not cs:
        console.print("[dim]No containers[/dim]")
        return
    t = Table(border_style="cyan")
    t.add_column("ID", style="bold", width=12)
    t.add_column("Name")
    t.add_column("Image")
    t.add_column("Status")
    t.add_column("Ports")
    for c in cs:
        ports = ", ".join(f"{h}:{cpt}" for cpt, h in c.get("ports", {}).items())
        st = c.get("live_status", c.get("status", "?"))
        style = "green" if st == "running" else "yellow"
        t.add_row(c.get("id", "")[:12], c.get("name", ""), c.get("image", ""),
                  f"[{style}]{st}[/{style}]", ports)
    console.print(t)


# ── stop ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
@click.option("--time", "-t", "timeout", type=int, default=10)
def stop(container, timeout):
    """Stop container"""
    _check()
    c = get_container(container)
    if not c:
        console.print(f"[red]Container '{container}' not found[/red]")
        raise SystemExit(1)
    c.stop(timeout=timeout)
    console.print(f"[green]✓[/green] Stopped {c.name}")


# ── start ────────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
def start(container):
    """Start stopped container"""
    _check()
    c = get_container(container)
    if not c:
        console.print(f"[red]Not found: {container}[/red]")
        raise SystemExit(1)
    c.remove()
    c.cfg.pop("pid", None)
    c.cfg.pop("status", None)
    c.cfg.pop("network", None)
    c.cfg.pop("veth", None)
    c.cfg.pop("merged", None)
    c.cfg.pop("cgroup", None)
    c.cfg.pop("log", None)
    c = c.create()
    try:
        c.start()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        lf = c.cfg.get("log", "")
        if lf and Path(lf).exists():
            for line in Path(lf).read_text().strip().split("\n")[-3:]:
                console.print(f"  [dim]{line}[/dim]")
        c.remove()
        raise SystemExit(1)
    console.print(f"[green]✓[/green] Started {c.name}")


# ── restart ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
@click.option("--time", "-t", "timeout", type=int, default=10)
def restart(container, timeout):
    """Restart container"""
    _check()
    c = get_container(container)
    if not c:
        console.print(f"[red]Not found: {container}[/red]")
        raise SystemExit(1)
    c.stop(timeout=timeout)
    c.remove()
    c.cfg.pop("pid", None)
    c.cfg.pop("status", None)
    c.cfg.pop("network", None)
    c.cfg.pop("veth", None)
    c.cfg.pop("merged", None)
    c.cfg.pop("cgroup", None)
    c.cfg.pop("log", None)
    c = c.create()
    try:
        c.start()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        lf = c.cfg.get("log", "")
        if lf and Path(lf).exists():
            for line in Path(lf).read_text().strip().split("\n")[-3:]:
                console.print(f"  [dim]{line}[/dim]")
        c.remove()
        raise SystemExit(1)
    console.print(f"[green]✓[/green] Restarted {c.name}")


# ── rm ───────────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
@click.option("--force", "-f", is_flag=True)
def rm(container, force):
    """Remove container"""
    _check()
    c = get_container(container)
    if not c:
        console.print(f"[red]Not found: {container}[/red]")
        raise SystemExit(1)
    if force:
        c.stop()
    c.remove()
    console.print(f"[green]✓[/green] Removed {c.name}")


# ── exec ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
@click.argument("cmd", nargs=-1, required=True)
@click.option("--interactive", "-i", is_flag=True)
@click.option("--tty", "-t", is_flag=True)
def exec_cmd(container, cmd, interactive, tty):
    """Exec in running container"""
    _check()
    c = get_container(container)
    if not c:
        console.print(f"[red]Not found: {container}[/red]")
        raise SystemExit(1)
    if c.status() != "running":
        console.print(f"[red]{container} is not running[/red]")
        raise SystemExit(1)
    try:
        c.exec_run(list(cmd), interactive=interactive or tty, tty=tty)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


# ── ssh ──────────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
@click.argument("shell", nargs=-1)
@click.option("--user", "-u", default="root")
def ssh(container, shell, user):
    """SSH into container"""
    cmd = list(shell) if shell else ["/bin/sh", "-c", f"exec su - {user} 2>/dev/null || exec /bin/sh"]
    ctx = click.get_current_context()
    ctx.invoke(exec_cmd, container=container, cmd=tuple(cmd), interactive=True, tty=True)


# ── logs ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
@click.option("--tail", "-t", type=int, default=50)
@click.option("--follow", "-f", is_flag=True)
def logs(container, tail, follow):
    """View logs"""
    _check()
    c = get_container(container)
    if not c:
        console.print(f"[red]Not found: {container}[/red]")
        raise SystemExit(1)
    out = c.logs(tail=tail, follow=follow)
    if out:
        console.print(out)


# ── inspect ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
def inspect(container):
    """Container details"""
    _check()
    c = get_container(container)
    if not c:
        console.print(f"[red]Not found: {container}[/red]")
        raise SystemExit(1)
    t = Table(border_style="cyan")
    t.add_column("Key", style="bold")
    t.add_column("Value")
    for k, v in c.cfg.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        t.add_row(k, str(v))
    console.print(t)


# ── doctor ───────────────────────────────────────────────────────────

@cli.command()
def doctor_cmd():
    """System check"""
    doctor()
