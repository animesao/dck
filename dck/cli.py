import os
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from dck.runtime import (
    Container, list_containers, get_container,
    pull_image, list_images, remove_image,
    doctor, system_prune, save_image, load_image,
    resolve_preset, validate_egg, apply_egg, builtin_eggs, load_egg,
    _load_config, _write_config,
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


# ── CLI root ─────────────────────────────────────────────────────

@click.group()
@click.version_option(package_name="dck")
def cli():
    pass


# ── pull ─────────────────────────────────────────────────────────

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


# ── images ───────────────────────────────────────────────────────

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


# ── rmi ──────────────────────────────────────────────────────────

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


# ── commit ───────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
@click.argument("image")
@click.option("--tag", "-t", default="latest")
def commit(container, image, tag):
    """Commit container to new image"""
    _check()
    c = get_container(container)
    if not c:
        console.print(f"[red]Container '{container}' not found[/red]")
        raise SystemExit(1)
    try:
        c.commit(image, tag)
        console.print(f"[green]✓[/green] Committed {c.name} as {image}:{tag}")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


# ── save ─────────────────────────────────────────────────────────

@cli.command()
@click.argument("image")
@click.argument("output", type=click.Path())
@click.option("--tag", "-t", default="latest")
def save(image, output, tag):
    """Save image to tar.gz archive"""
    _check()
    if ":" in image:
        image, tag = image.split(":", 1)
    try:
        save_image(image, tag, output)
        console.print(f"[green]✓[/green] Saved {image}:{tag} → {output}")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


# ── load ─────────────────────────────────────────────────────────

@cli.command()
@click.argument("input", type=click.Path(exists=True))
def load(input):
    """Load image from tar.gz archive"""
    _check()
    try:
        load_image(input)
        console.print(f"[green]✓[/green] Loaded {input}")
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


# ── run ──────────────────────────────────────────────────────────

@cli.command(context_settings=dict(ignore_unknown_options=False))
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


# ── ps ───────────────────────────────────────────────────────────

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


# ── stop ─────────────────────────────────────────────────────────

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


# ── start ────────────────────────────────────────────────────────

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


# ── restart ──────────────────────────────────────────────────────

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


# ── rm ───────────────────────────────────────────────────────────

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


# ── exec ─────────────────────────────────────────────────────────

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


# ── ssh ──────────────────────────────────────────────────────────

@cli.command()
@click.argument("container")
@click.argument("shell", nargs=-1)
@click.option("--user", "-u", default="root")
def ssh(container, shell, user):
    """SSH into container"""
    cmd = list(shell) if shell else ["/bin/sh", "-c", f"exec su - {user} 2>/dev/null || exec /bin/sh"]
    ctx = click.get_current_context()
    ctx.invoke(exec_cmd, container=container, cmd=tuple(cmd), interactive=True, tty=True)


# ── logs ─────────────────────────────────────────────────────────

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


# ── inspect ──────────────────────────────────────────────────────

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


# ── system ───────────────────────────────────────────────────────

@cli.group()
def system():
    """Manage system resources"""


@system.command()
@click.option("--all", "-a", "all_flag", is_flag=True, help="Also remove all images")
def prune(all_flag):
    """Remove stopped containers, overlays, logs, and optionally images"""
    _check()
    with console.status("Pruning..."):
        r = system_prune(all_=all_flag)
    console.print(f"[green]✓[/green] Removed {r['containers']} containers, {r['overlay']} overlays"
                  f"{', ' + str(r['images']) + ' images' if all_flag else ''}")


# ── up ───────────────────────────────────────────────────────────

@cli.command()
@click.option("--file", "-f", "config_file", help="Config file (dck.json/toml/yaml/yml)")
@click.option("--external-ip", help="External IP for port display")
def up(config_file, external_ip):
    """Start containers from config file"""
    _check()
    cfg = _find_config(config_file)
    for name, svc in cfg.get("services", {}).items():
        image = svc.get("image", "alpine:latest")
        tag = svc.get("tag", "latest")
        ports = svc.get("ports", {})
        volumes = svc.get("volumes", {})
        env = svc.get("env", {})
        ram = svc.get("ram")
        cpu = svc.get("cpu")
        restart = svc.get("restart", "no")
        hostname = svc.get("hostname", "")
        workdir = svc.get("workdir", "")

        try:
            img = pull_image(image, tag, progress_callback=None)
        except Exception as e:
            console.print(f"[red]{image}:{tag} pull failed: {e}[/red]")
            continue

        port_map = {}
        for cp, hp in ports.items():
            port_map[str(cp)] = int(hp)

        vol_map = {}
        for h, c in volumes.items():
            vol_map[os.path.expandvars(h)] = c

        cfg_data = {
            "image": f"{image}:{tag}",
            "cmd": svc.get("cmd", []),
            "rootfs": img["rootfs"],
            "ports": port_map,
            "volumes": vol_map,
            "env": env,
            "ram": ram,
            "cpu": cpu,
            "hostname": hostname,
            "workdir": workdir,
            "entrypoint": svc.get("entrypoint", ""),
            "tty": False,
            "interactive": False,
            "detach": True,
            "rm": False,
            "restart": restart,
        }

        c = Container(name=name, config=cfg_data)
        c.create()
        try:
            c.start()
            console.print(f"[green]✓[/green] Started {c.name} ({image}:{tag})")
        except RuntimeError as e:
            console.print(f"[red]{name}: {e}[/red]")
            lf = c.cfg.get("log", "")
            if lf and Path(lf).exists():
                for line in Path(lf).read_text().strip().split("\n")[-3:]:
                    console.print(f"  [dim]{line}[/dim]")
            c.remove()


# ── down ─────────────────────────────────────────────────────────

@cli.command()
@click.option("--file", "-f", "config_file", help="Config file (dck.json/toml/yaml/yml)")
@click.option("--time", "-t", "timeout", type=int, default=10)
def down(config_file, timeout):
    """Stop containers from config file"""
    _check()
    cfg = _find_config(config_file)
    names = set(cfg.get("services", {}).keys())
    for f in Path.home().glob(".dck/containers/*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("name") in names:
                c = Container(config=d)
                c.state_file = f
                c.name = d.get("name", c.name)
                c.stop(timeout=timeout)
                console.print(f"[green]✓[/green] Stopped {c.name}")
        except Exception:
            pass


def _find_config(config_file):
    if config_file:
        p = Path(config_file)
        if not p.exists():
            console.print(f"[red]Config not found: {config_file}[/red]")
            raise SystemExit(1)
        return _load_config(p)
    for name in ("dck.json", "dck.toml", "dck.yaml", "dck.yml"):
        p = Path(name)
        if p.exists():
            return _load_config(p)
    console.print("[red]No config file found (dck.json/toml/yaml/yml)[/red]")
    raise SystemExit(1)


# ── egg ──────────────────────────────────────────────────────────

@cli.group()
def egg():
    """Manage Pterodactyl-style eggs"""


@egg.command()
@click.argument("name")
@click.option("--file", "-f", "egg_file", help="Egg JSON/TOML file")
def create(name, egg_file):
    """Create an egg from a file"""
    _check()
    if not egg_file:
        console.print("[red]Specify egg file with --file|-f[/red]")
        raise SystemExit(1)
    try:
        data = load_egg(egg_file)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    errors = validate_egg(data)
    if errors:
        for e in errors:
            console.print(f"[red]Validation error: {e}[/red]")
        raise SystemExit(1)
    eggs_dir = Path.home() / ".dck" / "eggs" / name
    eggs_dir.mkdir(parents=True, exist_ok=True)
    egg_path = eggs_dir / "egg.json"
    egg_path.write_text(json.dumps(data, indent=2))
    console.print(f"[green]✓[/green] Egg '{name}' created at {egg_path}")


@egg.command()
@click.argument("egg_file")
def validate(egg_file):
    """Validate an egg file"""
    try:
        data = load_egg(egg_file)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    errors = validate_egg(data)
    if errors:
        for e in errors:
            console.print(f"[red]✗ {e}[/red]")
        raise SystemExit(1)
    console.print(f"[green]✓[/green] Egg is valid")


@egg.command("list")
def list_eggs():
    """List available eggs"""
    eggs = builtin_eggs()
    eggs_dir = Path.home() / ".dck" / "eggs"
    if eggs_dir.exists():
        for d in eggs_dir.iterdir():
            if d.is_dir():
                for ef in d.glob("egg.*"):
                    eggs[ef.stem] = {}
    if not eggs:
        console.print("[dim]No eggs[/dim]")
        return
    t = Table(border_style="cyan")
    t.add_column("Name", style="bold")
    t.add_column("Source")
    for name in sorted(eggs):
        src = "builtin" if name in builtin_eggs() else "user"
        t.add_row(name, src)
    console.print(t)


@egg.command()
@click.argument("name")
@click.argument("container")
@click.option("--env", "-e", multiple=True, help="KEY=VALUE")
def install(name, container, env):
    """Apply egg to a container"""
    _check()
    try:
        egg_data = load_egg(name)
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    errors = validate_egg(egg_data)
    if errors:
        for e in errors:
            console.print(f"[red]Validation error: {e}[/red]")
        raise SystemExit(1)
    c = get_container(container)
    if not c:
        console.print(f"[red]Container '{container}' not found[/red]")
        raise SystemExit(1)
    user_env = {}
    for e in env or []:
        if "=" in e:
            k, v = e.split("=", 1)
            user_env[k] = v
    result = apply_egg(egg_data, user_env)
    c.cfg["cmd"] = result["command"]
    c.cfg["env"].update(result["env"])
    c.cfg["ports"].update(result["ports"])
    c.save()
    console.print(f"[green]✓[/green] Applied egg '{name}' to {c.name}")
    console.print(f"  Start: {result['command']}")


# ── preset ───────────────────────────────────────────────────────

@cli.group()
def preset():
    """Manage application presets"""


@preset.command("list")
def list_presets():
    """List available presets"""
    from dck.runtime import PRESETS
    t = Table(border_style="cyan")
    t.add_column("Name", style="bold")
    t.add_column("Image")
    t.add_column("Description")
    descs = {
        "paper": "Paper Minecraft server",
        "purpur": "Purpur Minecraft server",
        "forge": "Forge Minecraft server",
        "spigot": "Spigot Minecraft server",
        "nginx": "Nginx web server",
        "apache": "Apache HTTP server",
        "mariadb": "MariaDB database",
        "postgres": "PostgreSQL database",
        "redis": "Redis cache",
        "node": "Node.js runtime",
        "python": "Python runtime",
        "golang": "Go runtime",
        "lamp": "LAMP stack",
        "rust": "Rust game server",
        "factorio": "Factorio game server",
        "terraria": "Terraria game server",
    }
    for name in sorted(PRESETS):
        img = PRESETS[name].get("image", "")
        desc = descs.get(name, "")
        t.add_row(name, img, desc)
    console.print(t)


@preset.command()
@click.argument("name")
def info(name):
    """Show preset details"""
    from dck.runtime import PRESETS
    if name not in PRESETS:
        console.print(f"[red]Unknown preset: {name}[/red]")
        raise SystemExit(1)
    data = PRESETS[name]
    t = Table(border_style="cyan", title=f"Preset: {name}")
    t.add_column("Key", style="bold")
    t.add_column("Value")
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        t.add_row(k, str(v))
    console.print(t)


@preset.command()
@click.argument("name")
@click.option("--name", "-n", "cname", help="Container name")
@click.option("--port", "-p", multiple=True, help="Extra port mappings")
@click.option("--volume", "-v", multiple=True, help="Extra volume mounts")
@click.option("--env", "-e", multiple=True, help="Extra env vars")
@click.option("--ram", help="Memory limit")
@click.option("--param", "-P", multiple=True, help="Preset parameter (key=value)")
@click.option("--detach", "-d", is_flag=True)
@click.option("--external-ip", help="External IP for port display")
def apply(name, cname, port, volume, env, ram, external_ip, detach, param):
    """Apply a preset and run a container"""
    _check()
    params = {}
    for p in param or []:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k] = v

    try:
        resolved = resolve_preset(name, params)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    image = resolved.get("image", "alpine:latest")
    tag = "latest"
    if ":" in image:
        image, tag = image.split(":", 1)

    ports = {}
    for p in list(resolved.get("ports", [])) + list(port or []):
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

    vols = {}
    for v in list(resolved.get("volumes", [])) + list(volume or []):
        if ":" in v:
            h, c = v.split(":", 1)
            vols[h] = c

    envd = dict(resolved.get("env", {}))
    for e in (env or []):
        if "=" in e:
            k, v = e.split("=", 1)
            envd[k] = v

    try:
        img = pull_image(image, tag, progress_callback=None)
    except Exception as e:
        console.print(f"[red]Failed to pull {image}:{tag}: {e}[/red]")
        raise SystemExit(1)

    cfg = {
        "image": f"{image}:{tag}",
        "cmd": resolved.get("command", []),
        "rootfs": img["rootfs"],
        "ports": ports,
        "volumes": vols,
        "env": envd,
        "ram": ram,
        "cpu": resolved.get("cpu"),
        "hostname": "",
        "workdir": resolved.get("workdir", ""),
        "entrypoint": resolved.get("entrypoint", ""),
        "tty": False,
        "interactive": False,
        "detach": detach,
        "rm": False,
        "restart": resolved.get("restart", "no"),
    }

    c = Container(name=cname, config=cfg)
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
        ip = _ext_ip(external_ip)
        for cp, hp in ports.items():
            cn = cp.split("/")[0]
            proto = cp.split("/")[1] if "/" in cp else "tcp"
            line = f"  [cyan]{hp}:{cn}/{proto}[/cyan]"
            if ip and proto == "tcp":
                line += f"  [dim]http://{ip}:{hp}[/dim]"
            console.print(line)


# ── doctor ───────────────────────────────────────────────────────

@cli.command()
def doctor_cmd():
    """System readiness check"""
    _check()
    console.print("[bold]dck doctor — system check[/bold]\n")
    ok = True
    def check(cond, msg):
        nonlocal ok
        console.print(f"  {'[green]✓[/green]' if cond else '[red]✗[/red]'} {msg}")
        if not cond:
            ok = False
    def warn(cond, msg):
        if not cond:
            console.print(f"  [yellow]⚠[/yellow] {msg}")
    check(os.geteuid() == 0, "root")
    check(Path("/proc/self/ns").exists(), "namespaces")
    check(Path("/sys/fs/cgroup/cgroup.controllers").exists(), "cgroups v2")
    check("overlay" in Path("/proc/filesystems").read_text(), "overlayfs")
    r = __import__("subprocess").run(["which", "ip", "iptables", "nsenter"], capture_output=True)
    check(r.returncode == 0, "ip + iptables + nsenter")
    console.print()
    console.print("[green]System ready[/green]" if ok else "[red]Some checks failed[/red]")
