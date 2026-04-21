"""Woolworths API client for melon product price fetching."""

from __future__ import annotations

import time
import requests
from dataclasses import dataclass

BASE_URL = "https://www.woolworths.com.au/apis/ui/Search/products"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.woolworths.com.au/",
    "Origin": "https://www.woolworths.com.au",
    "Content-Type": "application/json",
}

MELON_QUERIES = [
    "fresh watermelon",
    "fresh rockmelon",
    "fresh honeydew melon",
]


@dataclass
class WoolworthsProduct:
    sku: str
    name: str
    price: float
    was_price: float | None
    on_special: bool
    unit: str | None
    cup_price: float | None
    cup_measure: str | None


def _search(query: str, page_size: int = 24) -> list[dict]:
    payload = {
        "Filters": [],
        "IsSpecial": False,
        "Location": f"/shop/search/products?searchTerm={query}",
        "PageNumber": 1,
        "PageSize": page_size,
        "SearchTerm": query,
        "SortType": "TraderRelevance",
    }
    try:
        resp = requests.post(BASE_URL, json=payload, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        bundles = data.get("Bundles") or []
        products = []
        for bundle in bundles:
            for product in bundle.get("Products") or []:
                products.append(product)
        return products
    except requests.RequestException as exc:
        raise RuntimeError(f"Woolworths API request failed: {exc}") from exc


def _is_melon(name: str) -> bool:
    name_lower = name.lower()
    melon_keywords = [
        "watermelon", "rockmelon", "honeydew", "melon",
        "canteloupe", "cantaloupe",
    ]
    exclude_keywords = ["lolly", "candy", "juice", "drink", "dried", "frozen"]
    if any(ex in name_lower for ex in exclude_keywords):
        return False
    return any(kw in name_lower for kw in melon_keywords)


def _parse_product(raw: dict) -> WoolworthsProduct | None:
    name = raw.get("Name", "").strip()
    if not name or not _is_melon(name):
        return None

    sku = str(raw.get("Stockcode", ""))
    price = raw.get("Price")
    if price is None:
        return None

    was_price = raw.get("WasPrice")
    on_special = bool(raw.get("IsOnSpecial", False))

    # Unit / cup measure
    cup_price = raw.get("CupPrice")
    cup_measure = raw.get("CupMeasure")

    # Try to derive a human-readable unit from the product name
    unit = None
    name_lower = name.lower()
    if "half" in name_lower or "1/2" in name_lower:
        unit = "half"
    elif "quarter" in name_lower or "1/4" in name_lower:
        unit = "quarter"
    elif "whole" in name_lower:
        unit = "whole"
    elif cup_measure:
        unit = cup_measure

    return WoolworthsProduct(
        sku=sku,
        name=name,
        price=float(price),
        was_price=float(was_price) if was_price else None,
        on_special=on_special,
        unit=unit,
        cup_price=float(cup_price) if cup_price else None,
        cup_measure=cup_measure,
    )


def fetch_melon_products(verbose: bool = False) -> list[WoolworthsProduct]:
    """Fetch all fresh melon products from Woolworths and return parsed results."""
    seen_skus: set[str] = set()
    results: list[WoolworthsProduct] = []

    for query in MELON_QUERIES:
        if verbose:
            print(f"  Querying Woolworths: '{query}' ...")
        try:
            raw_products = _search(query)
        except RuntimeError as exc:
            if verbose:
                print(f"  Warning: {exc}")
            continue

        for raw in raw_products:
            product = _parse_product(raw)
            if product and product.sku not in seen_skus:
                seen_skus.add(product.sku)
                results.append(product)

        time.sleep(0.5)  # be polite between queries

    return results
