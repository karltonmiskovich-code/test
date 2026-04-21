"""Woolworths API client for melon product price fetching."""

from __future__ import annotations

import time
import requests
from dataclasses import dataclass

BASE_URL = "https://www.woolworths.com.au/apis/ui/Search/products"
HOME_URL = "https://www.woolworths.com.au/"

_session = requests.Session()
_session_ready = False

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": _BROWSER_UA,
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


def _ensure_session() -> None:
    """Visit the Woolworths homepage to acquire session cookies before API calls."""
    global _session_ready
    if _session_ready:
        return
    try:
        _session.get(
            HOME_URL,
            headers={"User-Agent": _BROWSER_UA, "Accept": "text/html"},
            timeout=15,
        )
        _session_ready = True
    except requests.RequestException:
        # Proceed anyway — the API may still work without cookies
        _session_ready = True


def _raw_search(query: str, page_size: int = 36) -> list[dict]:
    """POST to the Woolworths search API and return raw product dicts."""
    _ensure_session()
    payload = {
        "Filters": [],
        "IsSpecial": False,
        "Location": f"/shop/search/products?searchTerm={query}",
        "PageNumber": 1,
        "PageSize": page_size,
        "SearchTerm": query,
        "SortType": "TraderRelevance",
    }
    resp = _session.post(BASE_URL, json=payload, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    products = []
    for bundle in (data.get("Products") or data.get("Bundles") or []):
        for product in (bundle.get("Products") or []):
            products.append(product)
    return products


def _derive_unit(name: str) -> str | None:
    n = name.lower()
    if "half" in n or "1/2" in n:
        return "half"
    if "quarter" in n or "1/4" in n:
        return "quarter"
    if "whole" in n:
        return "whole"
    return None


def _is_melon(name: str) -> bool:
    n = name.lower()
    melon_kw = ["watermelon", "rockmelon", "honeydew", "melon", "cantaloupe", "canteloupe"]
    exclude_kw = ["lolly", "candy", "juice", "drink", "dried", "frozen"]
    if any(ex in n for ex in exclude_kw):
        return False
    return any(kw in n for kw in melon_kw)


def search_products(query: str, page_size: int = 36) -> list[dict]:
    """Search Woolworths for ANY products matching query.

    Returns raw dicts (no melon filter) so callers can inspect all results and
    verify product names before saving. Each dict has keys:
      sku, name, price, was_price, on_special, unit, cup_price, cup_measure
    """
    try:
        raws = _raw_search(query, page_size)
    except requests.RequestException as exc:
        raise RuntimeError(f"Woolworths API request failed: {exc}") from exc

    results = []
    for raw in raws:
        name = raw.get("Name", "").strip()
        price = raw.get("Price")
        if not name or price is None:
            continue
        cup_price = raw.get("CupPrice")
        cup_measure = raw.get("CupMeasure")
        results.append({
            "sku": str(raw.get("Stockcode", "")),
            "name": name,
            "price": float(price),
            "was_price": float(raw["WasPrice"]) if raw.get("WasPrice") else None,
            "on_special": bool(raw.get("IsOnSpecial", False)),
            "unit": _derive_unit(name) or cup_measure,
            "cup_price": float(cup_price) if cup_price else None,
            "cup_measure": cup_measure,
        })
    return results


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
    cup_price = raw.get("CupPrice")
    cup_measure = raw.get("CupMeasure")
    return WoolworthsProduct(
        sku=sku,
        name=name,
        price=float(price),
        was_price=float(was_price) if was_price else None,
        on_special=on_special,
        unit=_derive_unit(name) or cup_measure,
        cup_price=float(cup_price) if cup_price else None,
        cup_measure=cup_measure,
    )


def diagnose(query: str = "watermelon") -> dict:
    """Return raw diagnostic info to help troubleshoot API issues."""
    info: dict = {}
    try:
        _ensure_session()
        info["cookies"] = list(_session.cookies.keys())
        payload = {
            "Filters": [],
            "IsSpecial": False,
            "Location": f"/shop/search/products?searchTerm={query}",
            "PageNumber": 1,
            "PageSize": 5,
            "SearchTerm": query,
            "SortType": "TraderRelevance",
        }
        resp = _session.post(BASE_URL, json=payload, headers=HEADERS, timeout=15)
        info["status_code"] = resp.status_code
        info["response_size"] = len(resp.text)
        info["response_preview"] = resp.text[:800]
        try:
            data = resp.json()
            info["top_level_keys"] = list(data.keys())
            bundles = data.get("Bundles") or []
            info["bundle_count"] = len(bundles)
            products = [p for b in bundles for p in (b.get("Products") or [])]
            info["product_count"] = len(products)
            if products:
                info["first_product_keys"] = list(products[0].keys())
                info["first_product_name"] = products[0].get("Name")
        except Exception as parse_err:
            info["json_parse_error"] = str(parse_err)
    except Exception as exc:
        info["request_error"] = str(exc)
    return info


def fetch_melon_products(verbose: bool = False) -> list[WoolworthsProduct]:
    """Fetch all fresh melon products from Woolworths using preset queries."""
    seen_skus: set[str] = set()
    results: list[WoolworthsProduct] = []

    for query in MELON_QUERIES:
        if verbose:
            print(f"  Querying Woolworths: '{query}' ...")
        try:
            raw_products = _raw_search(query)
        except (requests.RequestException, RuntimeError) as exc:
            if verbose:
                print(f"  Warning: {exc}")
            continue

        found = 0
        for raw in raw_products:
            product = _parse_product(raw)
            if product and product.sku not in seen_skus:
                seen_skus.add(product.sku)
                results.append(product)
                found += 1

        if verbose:
            print(f"    → {len(raw_products)} total results, {found} melons matched.")

        time.sleep(0.5)

    return results
