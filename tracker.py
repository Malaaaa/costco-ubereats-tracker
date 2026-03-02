"""Change tracker: compares current vs. historical snapshots.

Supports two storage backends (configured in config.py):
  - 'sqlite': Uses TrackerDB for snapshot comparison and change persistence
  - 'csv': Legacy mode using history/ directory and changes.json

Detects and reports:
  - New / removed products
  - Restocks and stock-outs (per store)
  - Price drops and increases (per store)
  - New deals, expired deals, and changed deal text (per store)
"""

import csv
import glob
import json
import os
import shutil
from datetime import datetime

from config import STORAGE_BACKEND


def _clean_store_label(store_name, max_len=12):
    """Shorten a raw store column name for display."""
    label = (
        store_name
        .replace("Costco_", "")
        .replace("_", " ")
        .split(" On")[0]
    )
    if len(label) > max_len:
        label = label[: max_len - 2] + ".."
    return label


def _classify_change(change_type):
    """Return (emoji, severity) for a change type."""
    mapping = {
        "new_product":  ("🆕", "positive"),
        "removed":      ("🗑️", "negative"),
        "restock":      ("📦", "positive"),
        "out_of_stock": ("⚠️", "negative"),
        "price_drop":   ("💰", "positive"),
        "price_up":     ("📈", "negative"),
        "new_deal":     ("🔥", "positive"),
        "deal_expired": ("❌", "negative"),
        "deal_changed": ("🔄", "info"),
    }
    return mapping.get(change_type, ("ℹ️", "info"))


def _detect_changes(old_data, new_data, store_names):
    """Compare two snapshot dicts and return changes + stats.

    Args:
        old_data: Dict {product_name: {store_name: {price, stock, deal}}}
        new_data: Same structure as old_data
        store_names: List of store name strings

    Returns:
        (changes_dict, stats_dict)
        changes_dict: {product_name: [(change_type, message, severity), ...]}
        stats_dict: {change_type: count}
    """
    changes = {}
    stats = {
        "new_product": 0, "removed": 0,
        "restock": 0, "out_of_stock": 0,
        "price_drop": 0, "price_up": 0,
        "new_deal": 0, "deal_expired": 0, "deal_changed": 0,
    }

    # New products
    for prod in new_data:
        if prod not in old_data:
            emoji, severity = _classify_change("new_product")
            changes.setdefault(prod, []).append(
                ("new_product", f"{emoji} Newly Added to Catalog", severity)
            )
            stats["new_product"] += 1

    # Removed products
    for prod in old_data:
        if prod not in new_data:
            emoji, severity = _classify_change("removed")
            changes.setdefault(prod, []).append(
                ("removed", f"{emoji} Removed from Catalog", severity)
            )
            stats["removed"] += 1

    # Per-store changes for existing products
    for prod, new_stores in new_data.items():
        if prod not in old_data:
            continue

        old_stores = old_data[prod]

        for store in store_names:
            label = _clean_store_label(store)
            old = old_stores.get(store, {})
            new = new_stores.get(store, {})

            old_price = old.get("price", "NOT CARRIED")
            new_price = new.get("price", "NOT CARRIED")
            old_stock = old.get("stock", "NOT CARRIED")
            new_stock = new.get("stock", "NOT CARRIED")
            old_deal = old.get("deal", "").strip()
            new_deal = new.get("deal", "").strip()

            # Stock changes
            if old_stock == "Out of Stock" and new_stock == "Available":
                e, s = _classify_change("restock")
                changes.setdefault(prod, []).append(
                    ("restock", f"{e} Restocked at {label}", s)
                )
                stats["restock"] += 1
            elif old_stock == "Available" and new_stock == "Out of Stock":
                e, s = _classify_change("out_of_stock")
                changes.setdefault(prod, []).append(
                    ("out_of_stock", f"{e} Out of Stock at {label}", s)
                )
                stats["out_of_stock"] += 1

            # Price changes
            try:
                np_val = float(new_price.replace("$", "").replace(",", ""))
                op_val = float(old_price.replace("$", "").replace(",", ""))
                if np_val < op_val:
                    diff = op_val - np_val
                    e, s = _classify_change("price_drop")
                    changes.setdefault(prod, []).append(
                        ("price_drop", f"{e} Price Drop at {label} (↓${diff:.2f})", s)
                    )
                    stats["price_drop"] += 1
                elif np_val > op_val:
                    diff = np_val - op_val
                    e, s = _classify_change("price_up")
                    changes.setdefault(prod, []).append(
                        ("price_up", f"{e} Price Up at {label} (↑${diff:.2f})", s)
                    )
                    stats["price_up"] += 1
            except (ValueError, AttributeError):
                pass

            # Deal changes
            if new_deal and not old_deal:
                e, s = _classify_change("new_deal")
                changes.setdefault(prod, []).append(
                    ("new_deal", f"{e} New Deal at {label}: {new_deal}", s)
                )
                stats["new_deal"] += 1
            elif old_deal and not new_deal:
                e, s = _classify_change("deal_expired")
                changes.setdefault(prod, []).append(
                    ("deal_expired", f"{e} Deal Expired at {label} (was: {old_deal})", s)
                )
                stats["deal_expired"] += 1
            elif old_deal and new_deal and old_deal != new_deal:
                e, s = _classify_change("deal_changed")
                changes.setdefault(prod, []).append(
                    ("deal_changed", f"{e} Deal Changed at {label}: {old_deal} → {new_deal}", s)
                )
                stats["deal_changed"] += 1

    return changes, stats


def _print_summary(changes, stats):
    """Print a categorized console summary of detected changes."""
    total = sum(len(v) for v in changes.values())
    print(f"\n{'=' * 56}")
    print(f"  CHANGE TRACKING SUMMARY")
    print(f"{'=' * 56}")
    print(f"  Products with changes: {len(changes)}")
    print(f"  Total change events:   {total}")
    print(f"{'─' * 56}")

    labels = {
        "new_product":  "🆕  New products:",
        "removed":      "🗑️  Removed products:",
        "restock":      "📦  Restocked:",
        "out_of_stock": "⚠️  Out of Stock:",
        "price_drop":   "💰  Price drops:",
        "price_up":     "📈  Price increases:",
        "new_deal":     "🔥  New deals:",
        "deal_expired": "❌  Expired deals:",
        "deal_changed": "🔄  Changed deals:",
    }

    for key, label in labels.items():
        if stats.get(key, 0) > 0:
            print(f"  {label:24s} {stats[key]}")

    if total == 0:
        print("  ✅  No changes detected since last snapshot.")

    print(f"{'=' * 56}\n")

    # Show sample changes
    shown = 0
    for prod, entries in changes.items():
        if shown >= 10:
            print(f"  ... and {len(changes) - shown} more products with changes.")
            break
        print(f"  [{prod}]")
        for _, msg, _ in entries:
            print(f"    {msg}")
        shown += 1


# ---------------------------------------------------------------------------
# SQLite Backend
# ---------------------------------------------------------------------------

def _run_sqlite():
    """Track changes using the SQLite database."""
    from database import TrackerDB

    with TrackerDB() as db:
        latest_id = db.get_latest_snapshot_id()
        if latest_id is None:
            print("[!] No snapshots in database. Run analyzer first.")
            return

        prev_id = db.get_previous_snapshot_id(latest_id)
        if prev_id is None:
            print("[!] First snapshot recorded. No previous data to compare.")
            # Write empty changes.json for dashboard compatibility
            with open("changes.json", "w") as f:
                json.dump({}, f, indent=2)
            return

        print(f"[+] Comparing snapshot #{latest_id} against #{prev_id}")

        store_names = db.get_store_names(latest_id)
        old_data = db.get_snapshot_data(prev_id)
        new_data = db.get_snapshot_data(latest_id)

        changes, stats = _detect_changes(old_data, new_data, store_names)

        # Record changes to database
        for prod, entries in changes.items():
            for change_type, message, severity in entries:
                db.record_change(
                    latest_id, prod, change_type, message, severity
                )
        db.conn.commit()

        # Write changes.json for dashboard compatibility
        flat_changes = {
            prod: [msg for _, msg, _ in entries]
            for prod, entries in changes.items()
        }
        with open("changes.json", "w", encoding="utf-8") as f:
            json.dump(flat_changes, f, indent=2, ensure_ascii=False)

        _print_summary(changes, stats)


# ---------------------------------------------------------------------------
# CSV Backend (Legacy)
# ---------------------------------------------------------------------------

def _run_csv():
    """Track changes using CSV history/ directory."""
    os.makedirs("history", exist_ok=True)

    current_file = "costco_all_stores_comparison.csv"
    if not os.path.exists(current_file):
        print("[!] No comparison CSV found. Run analyzer first.")
        return

    history_files = sorted(glob.glob("history/*.csv"))

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    snapshot_path = f"history/{timestamp}.csv"
    shutil.copy(current_file, snapshot_path)

    if not history_files:
        print("[!] First snapshot created. No previous data to compare.")
        with open("changes.json", "w") as f:
            json.dump({}, f, indent=2)
        return

    last_file = history_files[-1]
    print(f"[+] Comparing against: {last_file}")

    # Load old CSV into dict format matching _detect_changes input
    old_data = {}
    with open(last_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        old_store_names = [
            c.replace(" - Price", "")
            for c in (reader.fieldnames or [])
            if c.endswith(" - Price")
        ]
        for row in reader:
            prod = row["Product Name"]
            old_data[prod] = {}
            for s in old_store_names:
                old_data[prod][s] = {
                    "price": row.get(f"{s} - Price", "NOT CARRIED"),
                    "stock": row.get(f"{s} - Stock", "NOT CARRIED"),
                    "deal": row.get(f"{s} - Deal", ""),
                }

    # Load new CSV
    new_data = {}
    store_names = []
    with open(current_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        store_names = [
            c.replace(" - Price", "")
            for c in (reader.fieldnames or [])
            if c.endswith(" - Price")
        ]
        for row in reader:
            prod = row["Product Name"]
            new_data[prod] = {}
            for s in store_names:
                new_data[prod][s] = {
                    "price": row.get(f"{s} - Price", "NOT CARRIED"),
                    "stock": row.get(f"{s} - Stock", "NOT CARRIED"),
                    "deal": row.get(f"{s} - Deal", ""),
                }

    changes, stats = _detect_changes(old_data, new_data, store_names)

    # Write changes.json
    flat_changes = {
        prod: [msg for _, msg, _ in entries]
        for prod, entries in changes.items()
    }
    with open("changes.json", "w", encoding="utf-8") as f:
        json.dump(flat_changes, f, indent=2, ensure_ascii=False)

    _print_summary(changes, stats)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def run_tracker():
    """Run change tracking with the configured storage backend."""
    if STORAGE_BACKEND == "sqlite":
        _run_sqlite()
    else:
        _run_csv()


if __name__ == "__main__":
    run_tracker()
