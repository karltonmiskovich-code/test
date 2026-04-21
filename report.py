"""Price comparison and reporting for the melon price tracker."""

from __future__ import annotations

from collections import defaultdict

from rich.console import Console
from rich.table import Table
from rich.text import Text

import database

console = Console()

STORE_ORDER = ["woolworths", "coles", "aldi"]
STORE_COLORS = {
    "woolworths": "green",
    "coles": "red",
    "aldi": "bright_blue",
}


def _price_cell(price: float | None, is_cheapest: bool, on_special: bool) -> Text:
    if price is None:
        return Text("-", style="dim")
    label = f"${price:.2f}"
    if on_special:
        label += " *"
    style = "bold green" if is_cheapest else ("yellow" if on_special else "")
    return Text(label, style=style)


def print_comparison_table(name_filter: str = "") -> None:
    """Print a side-by-side price comparison across all stores."""
    rows = database.get_cheapest_today(name_filter)
    if not rows:
        console.print("[yellow]No price data found. Run 'fetch' or 'enter' first.[/yellow]")
        return

    # Group by product name
    by_name: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by_name[r["name"]][r["store"]] = dict(r)

    table = Table(
        title=f"Melon Price Comparison{'  (filter: ' + name_filter + ')' if name_filter else ''}",
        show_lines=True,
        caption="* = on special  |  [bold green]green[/bold green] = cheapest store",
    )
    table.add_column("Product", min_width=26)
    table.add_column("Unit", style="dim", min_width=8)
    for store in STORE_ORDER:
        color = STORE_COLORS[store]
        table.add_column(store.title(), justify="right", style=color, min_width=10)
    table.add_column("Best Buy", justify="left", min_width=16)

    for name in sorted(by_name.keys()):
        store_data = by_name[name]
        prices = {
            s: store_data[s]["price"]
            for s in STORE_ORDER
            if s in store_data
        }
        min_price = min(prices.values()) if prices else None
        units = {s: store_data[s].get("unit") for s in store_data}
        unit_str = next((u for u in units.values() if u), "-")

        cells = []
        best_stores = []
        for store in STORE_ORDER:
            if store not in store_data:
                cells.append(Text("-", style="dim"))
            else:
                d = store_data[store]
                is_cheapest = d["price"] == min_price
                cells.append(_price_cell(d["price"], is_cheapest, bool(d["on_special"])))
                if is_cheapest:
                    best_stores.append(store.title())

        best_text = " / ".join(best_stores)
        if min_price is not None:
            best_text = f"${min_price:.2f} @ {best_text}"
        table.add_row(name, unit_str, *cells, best_text)

    console.print(table)
    console.print("[dim]Prices sourced: Woolworths via API; Coles & ALDI via manual entry.[/dim]")


def print_history_table(store: str | None = None, name_like: str | None = None) -> None:
    """Print price history for a store or product."""
    rows = database.get_price_history(store, name_like)
    if not rows:
        console.print("[yellow]No history found for the given filters.[/yellow]")
        return

    title_parts = ["Price History"]
    if store:
        title_parts.append(f"— {store.title()}")
    if name_like:
        title_parts.append(f"— '{name_like}'")

    table = Table(title=" ".join(title_parts), show_lines=True)
    table.add_column("Store", style="cyan")
    table.add_column("Product")
    table.add_column("Unit", style="dim")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Was", justify="right", style="dim")
    table.add_column("Special", justify="center")
    table.add_column("Source", style="dim")
    table.add_column("Recorded (UTC)")

    for r in rows:
        special = "[red]Yes[/red]" if r["on_special"] else "No"
        was = f"${r['was_price']:.2f}" if r["was_price"] else "-"
        table.add_row(
            r["store"].title(),
            r["name"],
            r["unit"] or "-",
            f"${r['price']:.2f}",
            was,
            special,
            r["source"],
            r["recorded_at"],
        )

    console.print(table)


def print_specials() -> None:
    """Print all products currently on special."""
    rows = database.get_latest_prices()
    specials = [r for r in rows if r["on_special"]]
    if not specials:
        console.print("[yellow]No specials found in the current data.[/yellow]")
        return

    table = Table(title="Current Melon Specials", show_lines=True)
    table.add_column("Store", style="cyan")
    table.add_column("Product")
    table.add_column("Sale Price", justify="right", style="bold green")
    table.add_column("Was", justify="right", style="dim")
    table.add_column("Saving", justify="right", style="yellow")
    table.add_column("Recorded")

    for r in specials:
        saving = ""
        if r["was_price"]:
            diff = r["was_price"] - r["price"]
            pct = (diff / r["was_price"]) * 100
            saving = f"-${diff:.2f} ({pct:.0f}%)"
        table.add_row(
            r["store"].title(),
            r["name"],
            f"${r['price']:.2f}",
            f"${r['was_price']:.2f}" if r["was_price"] else "-",
            saving,
            r["recorded_at"][:10],
        )

    console.print(table)
