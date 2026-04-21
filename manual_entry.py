"""Interactive manual price entry for Coles and ALDI."""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Confirm, FloatPrompt, Prompt
from rich.table import Table

import database

console = Console()

STORE_LABELS = {
    "coles": "Coles",
    "aldi": "ALDI",
}

SUGGESTED_MELONS = [
    "Watermelon (whole)",
    "Watermelon (half)",
    "Watermelon (quarter)",
    "Rockmelon (whole)",
    "Rockmelon (half)",
    "Honeydew (whole)",
    "Honeydew (half)",
    "Seedless Watermelon (whole)",
    "Seedless Watermelon (half)",
]


def _pick_melon_name() -> str:
    console.print("\n[bold]Common melon products:[/bold]")
    for i, name in enumerate(SUGGESTED_MELONS, 1):
        console.print(f"  {i}. {name}")
    console.print(f"  {len(SUGGESTED_MELONS) + 1}. Enter custom name")

    while True:
        choice = Prompt.ask(
            "Select a product",
            choices=[str(i) for i in range(1, len(SUGGESTED_MELONS) + 2)],
        )
        idx = int(choice) - 1
        if idx < len(SUGGESTED_MELONS):
            return SUGGESTED_MELONS[idx]
        return Prompt.ask("Enter product name")


def _pick_unit() -> str | None:
    units = ["whole", "half", "quarter", "kg", "each", "skip"]
    console.print("\n[bold]Unit:[/bold]")
    for i, u in enumerate(units, 1):
        console.print(f"  {i}. {u}")
    choice = Prompt.ask("Select unit", choices=[str(i) for i in range(1, len(units) + 1)])
    selected = units[int(choice) - 1]
    return None if selected == "skip" else selected


def enter_prices_for_store(store: str) -> int:
    """Interactively enter prices for a store. Returns count of entries saved."""
    label = STORE_LABELS.get(store, store.title())
    console.rule(f"[bold cyan]Manual price entry — {label}[/bold cyan]")
    console.print(f"Enter melon prices observed at [bold]{label}[/bold] today.\n")

    count = 0
    while True:
        name = _pick_melon_name()
        unit = _pick_unit()
        price = FloatPrompt.ask(f"  Price for [green]{name}[/green] ($AUD)")
        was_price: float | None = None
        on_special = Confirm.ask("  Is this on special / discounted?", default=False)
        if on_special:
            was_price_input = Prompt.ask(
                "  Original price (leave blank to skip)", default=""
            )
            if was_price_input.strip():
                try:
                    was_price = float(was_price_input)
                except ValueError:
                    pass

        product_id = database.upsert_product(store, name, sku=None, unit=unit)
        database.record_price(product_id, price, was_price, on_special, source="manual")
        count += 1
        console.print(f"  [green]Saved[/green] ${price:.2f} for {name} at {label}.")

        if not Confirm.ask("\n  Add another product for this store?", default=True):
            break

    return count


def bulk_enter(stores: list[str] | None = None) -> None:
    """Run manual entry for all manual-tracked stores (Coles, ALDI) or a subset."""
    targets = stores or ["coles", "aldi"]
    total = 0
    for store in targets:
        total += enter_prices_for_store(store)
    console.print(f"\n[bold green]Done.[/bold green] {total} price(s) recorded.")


def show_entry_summary(store: str | None = None) -> None:
    """Print a table of the most-recently entered manual prices."""
    rows = database.get_latest_prices()
    manual_rows = [r for r in rows if r["source"] == "manual"]
    if store:
        manual_rows = [r for r in manual_rows if r["store"] == store]

    if not manual_rows:
        console.print("[yellow]No manual price entries found.[/yellow]")
        return

    table = Table(title="Latest Manual Entries", show_lines=True)
    table.add_column("Store", style="cyan")
    table.add_column("Product")
    table.add_column("Unit")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Was", justify="right", style="dim")
    table.add_column("Special", justify="center")
    table.add_column("Recorded")

    for r in manual_rows:
        special = "[red]Yes[/red]" if r["on_special"] else "No"
        was = f"${r['was_price']:.2f}" if r["was_price"] else "-"
        table.add_row(
            r["store"].title(),
            r["name"],
            r["unit"] or "-",
            f"${r['price']:.2f}",
            was,
            special,
            r["recorded_at"][:10],
        )

    console.print(table)
