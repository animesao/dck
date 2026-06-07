import json
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from docker.errors import NotFound, APIError

from dck.client import get_client
from dck.i18n import t

console = Console()
DCK_DIR = Path.home() / ".dck"
STARTUP_FILE = DCK_DIR / "startup.json"


def load_startup_config():
    DCK_DIR.mkdir(parents=True, exist_ok=True)
    if STARTUP_FILE.exists():
        try:
            return json.loads(STARTUP_FILE.read_text())
        except (json.JSONDecodeError, Exception):
            return {}
    return {}


def save_startup_config(config):
    DCK_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_FILE.write_text(json.dumps(config, indent=2))


def get_startup_config(container_name):
    config = load_startup_config()
    return config.get(container_name, {})


def set_startup_command(container_name, command):
    config = load_startup_config()
    if container_name not in config:
        config[container_name] = {}
    config[container_name]["type"] = "command"
    config[container_name]["value"] = command
    save_startup_config(config)
    console.print(f"[green]{t('startup.set', container=container_name)}[/green]")


def set_startup_entrypoint(container_name, entrypoint):
    config = load_startup_config()
    if container_name not in config:
        config[container_name] = {}
    config[container_name]["type"] = "entrypoint"
    config[container_name]["value"] = entrypoint
    save_startup_config(config)
    console.print(f"[green]{t('startup.set', container=container_name)}[/green]")


def set_startup_file(container_name, file_path):
    config = load_startup_config()
    if container_name not in config:
        config[container_name] = {}
    config[container_name]["type"] = "script"
    config[container_name]["value"] = file_path
    save_startup_config(config)
    console.print(f"[green]{t('startup.set', container=container_name)}[/green]")


def clear_startup_config(container_name):
    config = load_startup_config()
    if container_name in config:
        del config[container_name]
        save_startup_config(config)
    console.print(f"[yellow]{t('startup.cleared', container=container_name)}[/yellow]")


def show_startup_config(container_name):
    cfg = get_startup_config(container_name)
    console.print(f"\n[bold cyan]{t('startup.show', container=container_name)}[/bold cyan]")
    if not cfg:
        console.print(f"  [dim]{t('startup.none')}[/dim]")
        return
    table = Table(border_style="cyan")
    table.add_column(t("startup.title"), style="bold")
    table.add_column("Value")
    stype = cfg.get("type", "")
    if stype == "command":
        table.add_row(t("startup.command"), cfg.get("value", ""))
    elif stype == "entrypoint":
        table.add_row(t("startup.entrypoint"), cfg.get("value", ""))
    elif stype == "script":
        table.add_row(t("startup.file"), cfg.get("value", ""))
    console.print(table)


def apply_startup_config(container_name):
    cfg = get_startup_config(container_name)
    if not cfg:
        return {}
    return cfg


def startup_prompt():
    if not Confirm.ask(f"  {t('startup.prompt')}", default=False):
        return {}
    console.print(f"  {t('startup.pick')}:")
    console.print(f"    1. {t('startup.type.none')}")
    console.print(f"    2. {t('startup.type.command')}")
    console.print(f"    3. {t('startup.type.entrypoint')}")
    console.print(f"    4. {t('startup.type.script')}")
    choice = Prompt.ask("  ", default="1")
    if choice == "2":
        cmd = Prompt.ask(f"  {t('startup.cmd_prompt')}")
        if cmd:
            return {"type": "command", "value": cmd}
    elif choice == "3":
        entry = Prompt.ask(f"  {t('startup.set_entrypoint')}")
        if entry:
            return {"type": "entrypoint", "value": entry}
    elif choice == "4":
        script = Prompt.ask(f"  {t('startup.file_prompt')}")
        if script:
            return {"type": "script", "value": script}
    return {}


def save_startup_for_container(container_name, startup_cfg):
    if not startup_cfg:
        return
    config = load_startup_config()
    config[container_name] = startup_cfg
    save_startup_config(config)
