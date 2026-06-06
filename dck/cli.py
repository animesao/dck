import click
from rich.console import Console

from dck.container import (
    list_containers,
    view_logs,
    start_container,
    stop_container,
    restart_container,
    remove_container,
    set_restart_policy,
)
from dck.image import list_images, pull_image, remove_image
from dck.compose import compose_up, compose_down, compose_ps, compose_logs
from dck.stats import stats
from dck.doctor import doctor
from dck.create import create_interactive, show_templates as show_tmpl, run_custom
from dck.uninstall import uninstall
from dck.lang import lang_cmd
from dck.port import ports_cmd

console = Console()


@click.group()
@click.version_option(package_name="dck")
def cli():
    """dck - Simple Docker CLI client

    Manage containers, images, compose projects and more.
    """
    pass


@cli.command("ps")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all containers (default shows running)")
def ps(show_all):
    """List containers"""
    list_containers(show_all)


@cli.command("logs")
@click.argument("container")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.option("--tail", "-t", type=int, default=50, help="Number of lines to show from the end")
def logs(container, follow, tail):
    """View container logs"""
    view_logs(container, follow, tail)


@cli.command("start")
@click.argument("container")
@click.option("--restart", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]),
              help="Set restart policy after starting")
def start(container, restart):
    """Start a container"""
    start_container(container, restart)


@cli.command("stop")
@click.argument("container")
def stop(container):
    """Stop a container"""
    stop_container(container)


@cli.command("restart")
@click.argument("container")
def restart(container):
    """Restart a container"""
    restart_container(container)


@cli.command("rm")
@click.argument("container")
@click.option("--force", "-f", is_flag=True, help="Force remove running container")
@click.option("--volumes", "-v", is_flag=True, help="Remove anonymous volumes")
def rm(container, force, volumes):
    """Remove a container"""
    remove_container(container, force, volumes)


@cli.command("restart-policy")
@click.argument("container")
@click.argument("policy", type=click.Choice(["no", "always", "unless-stopped", "on-failure"]))
def restart_policy(container, policy):
    """Set container restart policy (auto-start on boot/reboot)"""
    set_restart_policy(container, policy)


@cli.command("images")
def images():
    """List Docker images"""
    list_images()


@cli.command("pull")
@click.argument("image")
def pull(image):
    """Pull an image from registry"""
    pull_image(image)


@cli.command("rmi")
@click.argument("image")
@click.option("--force", "-f", is_flag=True, help="Force remove image")
def rmi(image, force):
    """Remove an image"""
    remove_image(image, force)


@cli.group()
def compose():
    """Manage Docker Compose projects"""
    pass


@compose.command("up")
@click.option("--detach", "-d", is_flag=True, help="Run containers in background")
@click.option("--build", is_flag=True, help="Build images before starting")
def compose_up_cmd(detach, build):
    """Create and start containers"""
    compose_up(detach, build)


@compose.command("down")
@click.option("--volumes", "-v", is_flag=True, help="Remove named volumes")
def compose_down_cmd(volumes):
    """Stop and remove containers"""
    compose_down(volumes)


@compose.command("ps")
def compose_ps_cmd():
    """List services in compose project"""
    compose_ps()


@compose.command("logs")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.option("--tail", "-t", type=int, default=50, help="Number of lines to show from the end")
@click.argument("service", required=False)
def compose_logs_cmd(follow, tail, service):
    """View compose service logs"""
    compose_logs(follow, tail, service)


@cli.command("stats")
def stats_cmd():
    """Live container resource monitoring (CPU, memory, network)"""
    stats()


@cli.command("doctor")
def doctor_cmd():
    """Check Docker installation and show install instructions"""
    doctor()


@cli.command("create")
@click.argument("template_name", required=False)
@click.option("--name", "-n", help="Container name")
@click.option("--ram", help="Memory limit (e.g. 512m, 2g)")
@click.option("--cpu", help="CPU limit (e.g. 0.5, 2)")
@click.option("--port", "-p", multiple=True, help="Port mapping (host:container/proto)")
@click.option("--env", "-e", multiple=True, help="Environment variable (KEY=value)")
@click.option("--volume", "-v", multiple=True, help="Volume mount (host:container)")
@click.option("--list", "-l", "list_only", is_flag=True, help="List templates")
def create_cmd(template_name, name, ram, cpu, port, env, volume, list_only):
    """Create a container from a template (nginx, minecraft, etc.)"""
    create_interactive(template_name, name, ram, cpu, port, env, volume, list_only)


@cli.command("templates")
def templates_cmd():
    """List available container templates"""
    show_tmpl()


@cli.command("uninstall")
def uninstall_cmd():
    """Remove dck completely from your system"""
    uninstall()


@cli.command("run")
@click.argument("image")
@click.option("--name", "-n", help="Container name")
@click.option("--ram", help="Memory limit (e.g. 512m, 2g)")
@click.option("--cpu", help="CPU limit (e.g. 0.5, 2)")
def run_cmd(image, name, ram, cpu):
    """Run a container from any Docker image (interactive setup)"""
    run_custom(image, name, ram, cpu)


cli.add_command(lang_cmd)
cli.add_command(ports_cmd)


if __name__ == "__main__":
    cli()
