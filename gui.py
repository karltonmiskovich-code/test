#!/usr/bin/env python3
"""Melon Price Tracker — Tkinter GUI. Run with: python gui.py"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from collections import defaultdict

import database
import woolworths_api

MELON_SUGGESTIONS = [
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

UNITS = ["", "whole", "half", "quarter", "kg", "each"]
STORES = ["woolworths", "coles", "aldi"]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Melon Price Tracker")
        self.geometry("1100x700")
        self.minsize(900, 580)
        database.init_db()
        self._apply_style()
        self._build_notebook()
        self._build_statusbar()

    # ── Style ─────────────────────────────────────────────────────────────────

    def _apply_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("vista")   # looks best on Windows
        except tk.TclError:
            s.theme_use("clam")
        s.configure("TNotebook.Tab", padding=[14, 6])
        s.configure("Heading.TLabel", font=("Segoe UI", 10, "bold"))
        s.configure("Info.TLabel", font=("Segoe UI", 9), foreground="#666666")

    # ── Notebook ──────────────────────────────────────────────────────────────

    def _build_notebook(self):
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_search_tab()
        self._build_manual_tab()
        self._build_compare_tab()
        self._build_specials_tab()
        self._build_history_tab()

    def _build_statusbar(self):
        self._status = tk.StringVar(value="Ready — search Woolworths or enter manual prices to get started.")
        bar = ttk.Label(self, textvariable=self._status, relief="sunken",
                        anchor="w", font=("Segoe UI", 9), foreground="#444444")
        bar.pack(fill="x", side="bottom", ipady=3, padx=0)

    def _set_status(self, msg: str):
        self._status.set(msg)
        self.update_idletasks()

    # ── Shared helper: treeview + scrollbar ──────────────────────────────────

    @staticmethod
    def _make_tree(parent, columns: list[tuple], height: int = 16) -> ttk.Treeview:
        """columns = [(id, heading, width, anchor), ...]"""
        col_ids = [c[0] for c in columns]
        tree = ttk.Treeview(parent, columns=col_ids, show="headings",
                            selectmode="extended", height=height)
        for col_id, heading, width, anchor in columns:
            tree.heading(col_id, text=heading,
                         command=lambda c=col_id, t=tree: _sort_tree(t, c, False))
            tree.column(col_id, width=width, anchor=anchor, minwidth=40)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return tree

    # ── Tab 1 — Search Woolworths ─────────────────────────────────────────────

    def _build_search_tab(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="  Search Woolworths  ")

        # Top: query bar
        qf = ttk.Frame(f)
        qf.pack(fill="x", pady=(0, 6))
        ttk.Label(qf, text="Search query:", style="Heading.TLabel").pack(side="left")
        self._q = tk.StringVar(value="melon")
        entry = ttk.Entry(qf, textvariable=self._q, width=30)
        entry.pack(side="left", padx=6)
        entry.bind("<Return>", lambda _: self._do_search())
        self._search_btn = ttk.Button(qf, text="Search Woolworths", command=self._do_search)
        self._search_btn.pack(side="left", padx=4)
        ttk.Label(qf, text="Tip: try 'watermelon', 'rockmelon', 'honeydew'",
                  style="Info.TLabel").pack(side="left", padx=14)

        # Results tree
        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True)
        self._stree = self._make_tree(tf, [
            ("name",    "Product Name",  370, "w"),
            ("price",   "Price ($)",      80, "e"),
            ("was",     "Was ($)",        80, "e"),
            ("special", "On Special",     80, "center"),
            ("sku",     "SKU",           100, "center"),
        ])
        self._stree.tag_configure("special", background="#fff3cd")

        # Bottom: save button + info
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(6, 0))
        ttk.Button(bf, text="Save Selected to Tracker",
                   command=self._save_search_selection).pack(side="left")
        ttk.Label(bf, text="  Ctrl+click or Shift+click to select multiple rows",
                  style="Info.TLabel").pack(side="left")
        self._search_info = tk.StringVar()
        ttk.Label(bf, textvariable=self._search_info,
                  style="Info.TLabel").pack(side="right", padx=10)

    def _do_search(self):
        query = self._q.get().strip()
        if not query:
            return
        self._search_btn.configure(state="disabled")
        self._search_info.set("Searching...")
        for row in self._stree.get_children():
            self._stree.delete(row)
        self._set_status(f"Searching Woolworths for '{query}'...")

        def worker():
            try:
                products = woolworths_api.search_products(query)
                self.after(0, lambda: self._populate_search(products))
            except Exception as exc:
                self.after(0, lambda e=exc: self._search_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_search(self, products: list[dict]):
        for p in products:
            tags = ("special",) if p["on_special"] else ()
            self._stree.insert("", "end", values=(
                p["name"],
                f"${p['price']:.2f}",
                f"${p['was_price']:.2f}" if p["was_price"] else "-",
                "YES" if p["on_special"] else "No",
                p["sku"],
            ), tags=tags)
        count = len(products)
        self._search_info.set(f"{count} result(s) found.")
        self._search_btn.configure(state="normal")
        self._set_status(f"Search complete — {count} product(s) returned from Woolworths.")

    def _search_error(self, msg: str):
        self._search_btn.configure(state="normal")
        self._search_info.set("Search failed.")
        self._set_status(f"Error: {msg}")
        messagebox.showerror(
            "Woolworths API Error",
            f"Could not reach the Woolworths API.\n\n{msg}\n\n"
            "Check your internet connection and try again.",
        )

    def _save_search_selection(self):
        selected = self._stree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Select one or more rows to save.")
            return
        saved = 0
        for iid in selected:
            name, price_s, was_s, special_s, sku = self._stree.item(iid, "values")
            price = float(price_s.replace("$", ""))
            was = float(was_s.replace("$", "")) if was_s != "-" else None
            on_special = special_s == "YES"
            unit = woolworths_api._derive_unit(name)
            pid = database.upsert_product("woolworths", name, sku, unit)
            database.record_price(pid, price, was, on_special, "api")
            saved += 1
        self._set_status(f"Saved {saved} Woolworths product(s) to tracker.")
        messagebox.showinfo("Saved", f"{saved} product(s) saved.")
        self._refresh_compare()
        self._refresh_specials()

    # ── Tab 2 — Manual Entry (Coles / ALDI) ──────────────────────────────────

    def _build_manual_tab(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="  Manual Entry (Coles / ALDI)  ")

        # Left: form
        form = ttk.LabelFrame(f, text=" New Price Entry ", padding=14)
        form.pack(side="left", fill="y", padx=(0, 12))

        ttk.Label(form, text="Store:").grid(row=0, column=0, sticky="w", pady=5)
        self._store_var = tk.StringVar(value="coles")
        sf = ttk.Frame(form)
        sf.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(sf, text="Coles", variable=self._store_var, value="coles").pack(side="left")
        ttk.Radiobutton(sf, text="ALDI",  variable=self._store_var, value="aldi").pack(side="left", padx=10)

        ttk.Label(form, text="Product:").grid(row=1, column=0, sticky="w", pady=5)
        self._prod_var = tk.StringVar()
        prod_cb = ttk.Combobox(form, textvariable=self._prod_var,
                               values=MELON_SUGGESTIONS, width=30)
        prod_cb.grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(form, text="Unit:").grid(row=2, column=0, sticky="w", pady=5)
        self._unit_var = tk.StringVar()
        ttk.Combobox(form, textvariable=self._unit_var, values=UNITS,
                     width=30).grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(form, text="Price ($):").grid(row=3, column=0, sticky="w", pady=5)
        self._price_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._price_var, width=14).grid(
            row=3, column=1, sticky="w", pady=5)

        ttk.Label(form, text="Was price ($):").grid(row=4, column=0, sticky="w", pady=5)
        self._was_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._was_var, width=14).grid(
            row=4, column=1, sticky="w", pady=5)

        self._special_var = tk.BooleanVar()
        ttk.Checkbutton(form, text="On Special / Discounted",
                        variable=self._special_var).grid(row=5, column=1, sticky="w", pady=8)

        ttk.Button(form, text="Save Price", command=self._save_manual).grid(
            row=6, column=1, sticky="w")

        self._manual_msg = tk.StringVar()
        ttk.Label(form, textvariable=self._manual_msg, foreground="green",
                  font=("Segoe UI", 9)).grid(row=7, column=0, columnspan=2,
                                              pady=(8, 0), sticky="w")

        # Right: recent entries
        rf = ttk.LabelFrame(f, text=" Recent Manual Entries ", padding=8)
        rf.pack(side="left", fill="both", expand=True)
        self._mtree = self._make_tree(rf, [
            ("store",   "Store",    80, "w"),
            ("product", "Product", 220, "w"),
            ("unit",    "Unit",     65, "center"),
            ("price",   "Price",    70, "e"),
            ("was",     "Was",      70, "e"),
            ("special", "Special",  60, "center"),
            ("date",    "Date",     90, "center"),
        ])
        self._mtree.tag_configure("special", background="#fff3cd")
        self._refresh_manual_tree()

    def _save_manual(self):
        store = self._store_var.get()
        name  = self._prod_var.get().strip()
        unit  = self._unit_var.get().strip() or None
        price_s = self._price_var.get().strip()
        was_s   = self._was_var.get().strip()
        on_special = self._special_var.get()

        if not name:
            messagebox.showwarning("Missing Field", "Enter a product name.")
            return
        try:
            price = float(price_s)
        except ValueError:
            messagebox.showwarning("Invalid Price", "Price must be a number (e.g. 4.99).")
            return
        was: float | None = None
        if was_s:
            try:
                was = float(was_s)
            except ValueError:
                messagebox.showwarning("Invalid Was Price", "Was price must be a number.")
                return

        pid = database.upsert_product(store, name, None, unit)
        database.record_price(pid, price, was, on_special, "manual")
        self._manual_msg.set(f"Saved ${price:.2f} for {name} @ {store.title()}")
        self._set_status(f"Manual entry saved: {name} @ {store.title()} — ${price:.2f}")
        self._price_var.set("")
        self._was_var.set("")
        self._special_var.set(False)
        self._refresh_manual_tree()
        self._refresh_compare()
        self._refresh_specials()

    def _refresh_manual_tree(self):
        for row in self._mtree.get_children():
            self._mtree.delete(row)
        for r in database.get_latest_prices():
            if r["source"] != "manual":
                continue
            tags = ("special",) if r["on_special"] else ()
            self._mtree.insert("", "end", values=(
                r["store"].title(),
                r["name"],
                r["unit"] or "-",
                f"${r['price']:.2f}",
                f"${r['was_price']:.2f}" if r["was_price"] else "-",
                "YES" if r["on_special"] else "No",
                r["recorded_at"][:10],
            ), tags=tags)

    # ── Tab 3 — Price Comparison ──────────────────────────────────────────────

    def _build_compare_tab(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="  Price Comparison  ")

        # Filter / refresh row
        fr = ttk.Frame(f)
        fr.pack(fill="x", pady=(0, 6))
        ttk.Label(fr, text="Filter:", style="Heading.TLabel").pack(side="left")
        self._cmp_filter = tk.StringVar()
        ttk.Entry(fr, textvariable=self._cmp_filter, width=24).pack(side="left", padx=6)
        ttk.Button(fr, text="Refresh", command=self._refresh_compare).pack(side="left", padx=4)
        ttk.Label(fr, text="green = cheapest   *  = on special",
                  style="Info.TLabel").pack(side="left", padx=14)

        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True)
        self._ctree = self._make_tree(tf, [
            ("product",     "Product",     250, "w"),
            ("unit",        "Unit",         65, "center"),
            ("woolworths",  "Woolworths",  110, "e"),
            ("coles",       "Coles",       110, "e"),
            ("aldi",        "ALDI",        110, "e"),
            ("best",        "Best Buy",    190, "w"),
        ])
        self._ctree.tag_configure("cheapest", background="#d4edda")
        self._ctree.tag_configure("special",  background="#fff3cd")
        self._refresh_compare()

    def _refresh_compare(self):
        for row in self._ctree.get_children():
            self._ctree.delete(row)

        name_filter = self._cmp_filter.get().strip() if hasattr(self, "_cmp_filter") else ""
        rows = database.get_cheapest_today(name_filter)
        if not rows:
            return

        by_name: dict[str, dict] = defaultdict(lambda: {"unit": "-"})
        for r in rows:
            n = r["name"]
            by_name[n]["unit"] = r["unit"] or "-"
            by_name[n][r["store"]] = {"price": r["price"], "special": bool(r["on_special"])}

        for name in sorted(by_name.keys()):
            d = by_name[name]
            prices = {s: d[s]["price"] for s in STORES if s in d}
            if not prices:
                continue
            min_p = min(prices.values())
            best = [s.title() for s, p in prices.items() if p == min_p]
            any_special = any(d.get(s, {}).get("special") for s in STORES)

            def fmt(s: str) -> str:
                if s not in d:
                    return "-"
                v = f"${d[s]['price']:.2f}"
                return v + " *" if d[s]["special"] else v

            tag = "cheapest" if len(best) < len(prices) else ("special" if any_special else "")
            self._ctree.insert("", "end", values=(
                name, d["unit"],
                fmt("woolworths"), fmt("coles"), fmt("aldi"),
                f"${min_p:.2f} @ {' / '.join(best)}",
            ), tags=(tag,) if tag else ())

    # ── Tab 4 — Specials ──────────────────────────────────────────────────────

    def _build_specials_tab(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="  Specials  ")

        ttk.Button(f, text="Refresh", command=self._refresh_specials).pack(anchor="w", pady=(0, 8))

        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True)
        self._sptree = self._make_tree(tf, [
            ("store",   "Store",       100, "w"),
            ("product", "Product",     260, "w"),
            ("price",   "Sale Price",   90, "e"),
            ("was",     "Was",          90, "e"),
            ("saving",  "Saving",      120, "center"),
            ("date",    "Date",        100, "center"),
        ])
        self._sptree.tag_configure("deal", background="#d4edda")
        self._refresh_specials()

    def _refresh_specials(self):
        for row in self._sptree.get_children():
            self._sptree.delete(row)
        for r in database.get_latest_prices():
            if not r["on_special"]:
                continue
            saving = ""
            if r["was_price"]:
                diff = r["was_price"] - r["price"]
                pct  = (diff / r["was_price"]) * 100
                saving = f"-${diff:.2f}  ({pct:.0f}% off)"
            self._sptree.insert("", "end", values=(
                r["store"].title(),
                r["name"],
                f"${r['price']:.2f}",
                f"${r['was_price']:.2f}" if r["was_price"] else "-",
                saving,
                r["recorded_at"][:10],
            ), tags=("deal",))

    # ── Tab 5 — History ───────────────────────────────────────────────────────

    def _build_history_tab(self):
        f = ttk.Frame(self._nb, padding=10)
        self._nb.add(f, text="  History  ")

        ff = ttk.Frame(f)
        ff.pack(fill="x", pady=(0, 8))
        ttk.Label(ff, text="Store:").pack(side="left")
        self._hist_store = tk.StringVar(value="All")
        ttk.Combobox(ff, textvariable=self._hist_store,
                     values=["All", "Woolworths", "Coles", "ALDI"],
                     state="readonly", width=12).pack(side="left", padx=4)
        ttk.Label(ff, text="  Product contains:").pack(side="left")
        self._hist_product = tk.StringVar()
        he = ttk.Entry(ff, textvariable=self._hist_product, width=22)
        he.pack(side="left", padx=4)
        he.bind("<Return>", lambda _: self._refresh_history())
        ttk.Button(ff, text="Apply",  command=self._refresh_history).pack(side="left", padx=4)
        ttk.Button(ff, text="Clear",  command=self._clear_hist_filters).pack(side="left")

        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True)
        self._htree = self._make_tree(tf, [
            ("store",   "Store",       90, "w"),
            ("product", "Product",    230, "w"),
            ("unit",    "Unit",        65, "center"),
            ("price",   "Price",       80, "e"),
            ("was",     "Was",         80, "e"),
            ("special", "Special",     65, "center"),
            ("source",  "Source",      65, "center"),
            ("date",    "Date (UTC)", 150, "center"),
        ])
        self._htree.tag_configure("special", background="#fff3cd")
        self._refresh_history()

    def _clear_hist_filters(self):
        self._hist_store.set("All")
        self._hist_product.set("")
        self._refresh_history()

    def _refresh_history(self):
        for row in self._htree.get_children():
            self._htree.delete(row)
        store_sel = self._hist_store.get()
        store_arg = None if store_sel == "All" else store_sel.lower()
        name_arg  = self._hist_product.get().strip() or None
        rows = database.get_price_history(store_arg, name_arg)
        for r in rows:
            tags = ("special",) if r["on_special"] else ()
            self._htree.insert("", "end", values=(
                r["store"].title(),
                r["name"],
                r["unit"] or "-",
                f"${r['price']:.2f}",
                f"${r['was_price']:.2f}" if r["was_price"] else "-",
                "YES" if r["on_special"] else "No",
                r["source"],
                r["recorded_at"],
            ), tags=tags)
        self._set_status(f"History: {len(rows)} record(s) shown.")


# ── Column sort helper ────────────────────────────────────────────────────────

def _sort_tree(tree: ttk.Treeview, col: str, descending: bool):
    data = [(tree.set(iid, col), iid) for iid in tree.get_children("")]
    try:
        data.sort(key=lambda t: float(t[0].replace("$", "").replace("*", "").strip()),
                  reverse=descending)
    except ValueError:
        data.sort(reverse=descending)
    for idx, (_, iid) in enumerate(data):
        tree.move(iid, "", idx)
    tree.heading(col, command=lambda: _sort_tree(tree, col, not descending))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
