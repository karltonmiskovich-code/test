"""SQLite database layer for melon price tracker."""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "melon_prices.db"

STORES = ("woolworths", "coles", "aldi")

MELON_TYPES = (
    "Watermelon (whole)",
    "Watermelon (half)",
    "Watermelon (quarter)",
    "Rockmelon (whole)",
    "Rockmelon (half)",
    "Honeydew (whole)",
    "Honeydew (half)",
    "Seedless Watermelon (whole)",
    "Seedless Watermelon (half)",
    "Mixed Melons",
)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                store       TEXT NOT NULL CHECK(store IN ('woolworths','coles','aldi')),
                name        TEXT NOT NULL,
                sku         TEXT,
                unit        TEXT,
                UNIQUE(store, sku)
            );

            CREATE TABLE IF NOT EXISTS prices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id  INTEGER NOT NULL REFERENCES products(id),
                price       REAL NOT NULL,
                was_price   REAL,
                on_special  INTEGER NOT NULL DEFAULT 0,
                source      TEXT NOT NULL CHECK(source IN ('api','manual')),
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_prices_product ON prices(product_id);
            CREATE INDEX IF NOT EXISTS idx_prices_recorded ON prices(recorded_at);
        """)


def upsert_product(store: str, name: str, sku: str | None, unit: str | None) -> int:
    with get_connection() as conn:
        if sku:
            row = conn.execute(
                "SELECT id FROM products WHERE store=? AND sku=?", (store, sku)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE products SET name=?, unit=? WHERE id=?",
                    (name, unit, row["id"]),
                )
                return row["id"]
        row = conn.execute(
            "SELECT id FROM products WHERE store=? AND name=?", (store, name)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE products SET sku=?, unit=? WHERE id=?",
                (sku, unit, row["id"]),
            )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO products (store, name, sku, unit) VALUES (?,?,?,?)",
            (store, name, sku, unit),
        )
        return cur.lastrowid


def record_price(
    product_id: int,
    price: float,
    was_price: float | None,
    on_special: bool,
    source: str,
) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO prices (product_id, price, was_price, on_special, source, recorded_at)
               VALUES (?,?,?,?,?,?)""",
            (product_id, price, was_price, int(on_special), source, now),
        )


def get_latest_prices() -> list[sqlite3.Row]:
    """Return the most recent price entry per product."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT p.store, p.name, p.unit, p.sku,
                   pr.price, pr.was_price, pr.on_special, pr.source, pr.recorded_at
            FROM products p
            JOIN prices pr ON pr.product_id = p.id
            WHERE pr.id = (
                SELECT id FROM prices WHERE product_id = p.id
                ORDER BY recorded_at DESC LIMIT 1
            )
            ORDER BY p.name, p.store
        """).fetchall()


def get_price_history(store: str | None = None, name_like: str | None = None) -> list[sqlite3.Row]:
    query = """
        SELECT p.store, p.name, p.unit, pr.price, pr.was_price,
               pr.on_special, pr.source, pr.recorded_at
        FROM products p
        JOIN prices pr ON pr.product_id = p.id
        WHERE 1=1
    """
    params: list = []
    if store:
        query += " AND p.store = ?"
        params.append(store)
    if name_like:
        query += " AND p.name LIKE ?"
        params.append(f"%{name_like}%")
    query += " ORDER BY p.name, p.store, pr.recorded_at DESC"
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def get_cheapest_today(melon_name_like: str = "") -> list[sqlite3.Row]:
    """Return the cheapest current price for each melon type across all stores."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT p.store, p.name, p.unit, pr.price, pr.was_price,
                   pr.on_special, pr.recorded_at
            FROM products p
            JOIN prices pr ON pr.product_id = p.id
            WHERE pr.id = (
                SELECT id FROM prices WHERE product_id = p.id
                ORDER BY recorded_at DESC LIMIT 1
            )
            AND p.name LIKE ?
            ORDER BY p.name, pr.price ASC
        """, (f"%{melon_name_like}%",)).fetchall()
