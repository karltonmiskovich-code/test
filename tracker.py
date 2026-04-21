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
@click.argument("query")
@click.option("--save", is_flag=True, help="Save all results to the tracker.")
def search(query: str, save: bool) -> None:
    """Search Woolworths by QUERY and display raw results.

    Use this to verify product names and prices before they are saved.

    \b
    Examples:
      tracker.py search watermelon
      tracker.py search "seedless watermelon"
      tracker.py search rockmelon --save
    """
    console.print(f"[bold cyan]Searching Woolworths for '{query}'...[/bold cyan]")
    try:
        products = woolworths_api.search_products(query)
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    if not products:
        console.print("[yellow]No results returned. Try a different query.[/yellow]")
        return

    from rich.table import Table
    table = Table(title=f"Woolworths search: '{query}'  ({len(products)} results)", show_lines=True)
    table.add_column("#", width=4)
    table.add_column("Product Name", min_width=36)
    table.add_column("Price", justify="right")
    table.add_column("Was", justify="right", style="dim")
    table.add_column("Special", justify="center")
    table.add_column("SKU")

    for i, p in enumerate(products, 1):
        special = "[red]YES[/red]" if p["on_special"] else "No"
        was = f"${p['was_price']:.2f}" if p["was_price"] else "-"
        table.add_row(str(i), p["name"], f"${p['price']:.2f}", was, special, p["sku"])

    console.print(table)

    if save:
        saved = 0
        for p in products:
            pid = database.upsert_product("woolworths", p["name"], p["sku"], p["unit"])
            database.record_price(pid, p["price"], p["was_price"], p["on_special"], "api")
            saved += 1
        console.print(f"[green]Saved {saved} product(s) to tracker.[/green]")


@cli.command()
@click.argument("query", default="watermelon")
def debug(query: str) -> None:
    """Show raw Woolworths API response details to diagnose connection issues.

    \b
    Examples:
      tracker.py debug
      tracker.py debug rockmelon
    """
    console.print(f"[bold cyan]Diagnosing Woolworths API for '{query}'...[/bold cyan]\n")
    info = woolworths_api.diagnose(query)

    if "request_error" in info:
        console.print(f"[red]Connection failed:[/red] {info['request_error']}")
        return

    status_color = "green" if info.get("status_code") == 200 else "red"
    console.print(f"HTTP status:      [{status_color}]{info.get('status_code')}[/{status_color}]")
    console.print(f"Response size:    {info.get('response_size', 0)} bytes")
    console.print(f"Cookies received: {info.get('cookies', [])}")
    console.print(f"Top-level keys:   {info.get('top_level_keys', 'N/A')}")
    console.print(f"Bundles:          {info.get('bundle_count', 'N/A')}")
    console.print(f"Products:         {info.get('product_count', 'N/A')}")

    if info.get("first_product_name"):
        console.print(f"First product:    {info['first_product_name']}")

    if "json_parse_error" in info:
        console.print(f"\n[red]JSON parse error:[/red] {info['json_parse_error']}")

    console.print(f"\n[dim]--- Response preview (first 800 chars) ---[/dim]")
    console.print(info.get("response_preview", "(empty)"))


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
