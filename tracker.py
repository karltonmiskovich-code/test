#!/usr/bin/env python3
"""
Melon Price Tracker — CLI entry point.

Commands:
  fetch      Pull latest prices from Woolworths API
  enter      Manually enter prices for Coles and/or ALDI
  compare    Show side-by-side price comparison across all stores
  history    Show price history (optionally filtered)
  specials   Show all current specials / discounted items
"""

import sys
import click
from rich.console import Console

import database
import woolworths_api
import manual_entry
import report

console = Console()


@click.group()
def cli() -> None:
    """Fresh melon price tracker — Woolworths (API), Coles & ALDI (manual)."""
    database.init_db()


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show query details.")
def fetch(verbose: bool) -> None:
    """Fetch latest melon prices from the Woolworths API."""
    console.print("[bold cyan]Fetching from Woolworths API...[/bold cyan]")
    try:
        products = woolworths_api.fetch_melon_products(verbose=verbose)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    if not products:
        console.print("[yellow]No melon products returned from Woolworths.[/yellow]")
        return

    saved = 0
    for p in products:
        pid = database.upsert_product("woolworths", p.name, p.sku, p.unit)
        database.record_price(pid, p.price, p.was_price, p.on_special, source="api")
        saved += 1
        if verbose:
            special_tag = " [SPECIAL]" if p.on_special else ""
            console.print(f"  {p.name:<45} ${p.price:.2f}{special_tag}")

    console.print(f"[green]Saved {saved} Woolworths product(s).[/green]")


@cli.command()
@click.argument("stores", nargs=-1, type=click.Choice(["coles", "aldi"], case_sensitive=False))
def enter(stores: tuple[str, ...]) -> None:
    """Manually enter melon prices for COLES and/or ALDI.

    If no stores are specified, both Coles and ALDI are prompted.

    \b
    Examples:
      tracker.py enter
      tracker.py enter coles
      tracker.py enter aldi
      tracker.py enter coles aldi
    """
    target_stores = list(stores) if stores else ["coles", "aldi"]
    manual_entry.bulk_enter(target_stores)


@cli.command()
@click.option("--filter", "name_filter", default="", help="Filter by product name substring.")
def compare(name_filter: str) -> None:
    """Show a price comparison table across all stores."""
    report.print_comparison_table(name_filter)


@cli.command()
@click.option("--store", type=click.Choice(["woolworths", "coles", "aldi"]), default=None)
@click.option("--product", "name_like", default=None, help="Filter by product name substring.")
def history(store: str | None, name_like: str | None) -> None:
    """Show price history, optionally filtered by store or product name."""
    report.print_history_table(store, name_like)


@cli.command()
def specials() -> None:
    """Show all melon products currently on special."""
    report.print_specials()


@cli.command()
def status() -> None:
    """Show a summary of tracked products and latest prices."""
    rows = database.get_latest_prices()
    if not rows:
        console.print("[yellow]No data yet. Run 'fetch' or 'enter' first.[/yellow]")
        return

    by_store: dict[str, list] = {}
    for r in rows:
        by_store.setdefault(r["store"], []).append(r)

    for store, products in sorted(by_store.items()):
        color = report.STORE_COLORS.get(store, "white")
        console.print(f"\n[bold {color}]{store.title()}[/bold {color}] — {len(products)} product(s)")
        for p in products:
            special = " [red](special)[/red]" if p["on_special"] else ""
            console.print(f"  {p['name']:<45} ${p['price']:.2f}{special}  [dim]{p['recorded_at'][:10]}[/dim]")


if __name__ == "__main__":
    cli()
