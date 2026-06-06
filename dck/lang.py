import click
from rich.console import Console
from rich.table import Table

from dck.i18n import set_lang, LANG, TRANSLATIONS, t

console = Console()


@click.command("lang")
@click.argument("code", required=False)
def lang_cmd(code):
    """Set display language (ru or en)"""
    available = list(TRANSLATIONS.keys())

    if not code:
        table = Table(title="Languages", border_style="cyan")
        table.add_column("Code", style="bold")
        table.add_column("Language")
        table.add_column("Status")
        for lang_code in available:
            status = "[green]active[/green]" if lang_code == LANG else ""
            table.add_row(lang_code, TRANSLATIONS[lang_code].get("lang.name", lang_code), status)
        console.print(table)
        console.print(f"\nUsage: dck lang [{'|'.join(available)}]")
        return

    if code not in available:
        console.print(f"[red]Error:[/red] Unsupported language '{code}'. Use: {', '.join(available)}")
        return

    set_lang(code)
    console.print(f"Language set to [green]{TRANSLATIONS[code].get('lang.name', code)}[/green]")
