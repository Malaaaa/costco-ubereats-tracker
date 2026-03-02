"""Change tracker: compares current vs. historical snapshots.

Detects and reports:
  - New / removed products
  - Restocks and stock-outs (per store)
  - Price drops and increases (per store)
  - New deals, expired deals, and changed deal text (per store)

Results are saved to changes.json for dashboard consumption
and printed as a categorized console summary.
"""

import csv
import glob
import json
import os
import shutil
from datetime import datetime


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


def run_tracker():
    """Compare the current comparison CSV against the most recent snapshot."""
    os.makedirs("history", exist_ok=True)

    current_file = "costco_all_stores_comparison.csv"
    if not os.path.exists(current_file):
        print("[!] No comparison CSV found. Run analyzer first.")
        return

    # Discover existing snapshots (sorted chronologically)
    history_files = sorted(glob.glob("history/*.csv"))

    # Save today's snapshot
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    snapshot_path = f"history/{timestamp}.csv"
    shutil.copy(current_file, snapshot_path)

    if not history_files:
        print("[!] First snapshot created. No previous data to compare against.")
        with open("changes.json", "w") as f:
            json.dump({}, f, indent=2)
        return

    last_file = history_files[-1]
    print(f"[+] Comparing against previous snapshot: {last_file}")

    # ---- Load previous data ----
    old_data = {}
    with open(last_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        old_fields = reader.fieldnames or []
        for row in reader:
            old_data[row["Product Name"]] = row

    # ---- Load current data ----
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
            new_data[row["Product Name"]] = row

    # ---- Detect changes ----
    changes = {}

    # Counters for the summary
    stats = {
        "new_products": 0,
        "removed_products": 0,
        "restocked": 0,
        "out_of_stock": 0,
        "price_drops": 0,
        "price_increases": 0,
        "new_deals": 0,
        "expired_deals": 0,
        "changed_deals": 0,
    }

    # --- New products ---
    for prod in new_data:
        if prod not in old_data:
            changes.setdefault(prod, []).append("🆕 Newly Added to Catalog")
            stats["new_products"] += 1

    # --- Removed products ---
    for prod in old_data:
        if prod not in new_data:
            changes.setdefault(prod, []).append("🗑️ Removed from Catalog")
            stats["removed_products"] += 1

    # --- Per-store changes for existing products ---
    for prod, new_row in new_data.items():
        if prod not in old_data:
            continue

        old_row = old_data[prod]

        for store in store_names:
            price_col = f"{store} - Price"
            stock_col = f"{store} - Stock"
            deal_col = f"{store} - Deal"
            label = _clean_store_label(store)

            old_price = old_row.get(price_col, "NOT CARRIED")
            new_price = new_row.get(price_col, "NOT CARRIED")
            old_stock = old_row.get(stock_col, "NOT CARRIED")
            new_stock = new_row.get(stock_col, "NOT CARRIED")
            old_deal = old_row.get(deal_col, "").strip()
            new_deal = new_row.get(deal_col, "").strip()

            # ---- Stock changes ----
            if old_stock == "Out of Stock" and new_stock == "Available":
                changes.setdefault(prod, []).append(
                    f"📦 Restocked at {label}"
                )
                stats["restocked"] += 1

            elif old_stock == "Available" and new_stock == "Out of Stock":
                changes.setdefault(prod, []).append(
                    f"⚠️ Out of Stock at {label}"
                )
                stats["out_of_stock"] += 1

            # ---- Price changes ----
            try:
                np_val = float(new_price.replace("$", "").replace(",", ""))
                op_val = float(old_price.replace("$", "").replace(",", ""))
                if np_val < op_val:
                    diff = op_val - np_val
                    changes.setdefault(prod, []).append(
                        f"💰 Price Drop at {label} (↓${diff:.2f})"
                    )
                    stats["price_drops"] += 1
                elif np_val > op_val:
                    diff = np_val - op_val
                    changes.setdefault(prod, []).append(
                        f"📈 Price Up at {label} (↑${diff:.2f})"
                    )
                    stats["price_increases"] += 1
            except (ValueError, AttributeError):
                pass

            # ---- Deal changes ----
            if new_deal and not old_deal:
                changes.setdefault(prod, []).append(
                    f"🔥 New Deal at {label}: {new_deal}"
                )
                stats["new_deals"] += 1

            elif old_deal and not new_deal:
                changes.setdefault(prod, []).append(
                    f"❌ Deal Expired at {label} (was: {old_deal})"
                )
                stats["expired_deals"] += 1

            elif old_deal and new_deal and old_deal != new_deal:
                changes.setdefault(prod, []).append(
                    f"🔄 Deal Changed at {label}: {old_deal} → {new_deal}"
                )
                stats["changed_deals"] += 1

    # ---- Save to changes.json ----
    with open("changes.json", "w", encoding="utf-8") as f:
        json.dump(changes, f, indent=2, ensure_ascii=False)

    # ---- Console Summary ----
    total_changes = sum(len(v) for v in changes.values())
    print(f"\n{'=' * 56}")
    print(f"  CHANGE TRACKING SUMMARY")
    print(f"{'=' * 56}")
    print(f"  Products with changes: {len(changes)}")
    print(f"  Total change events:   {total_changes}")
    print(f"{'─' * 56}")

    if stats["new_products"]:
        print(f"  🆕  New products:       {stats['new_products']}")
    if stats["removed_products"]:
        print(f"  🗑️  Removed products:   {stats['removed_products']}")
    if stats["restocked"]:
        print(f"  📦  Restocked:          {stats['restocked']}")
    if stats["out_of_stock"]:
        print(f"  ⚠️  Out of Stock:       {stats['out_of_stock']}")
    if stats["price_drops"]:
        print(f"  💰  Price drops:        {stats['price_drops']}")
    if stats["price_increases"]:
        print(f"  📈  Price increases:    {stats['price_increases']}")
    if stats["new_deals"]:
        print(f"  🔥  New deals:          {stats['new_deals']}")
    if stats["expired_deals"]:
        print(f"  ❌  Expired deals:      {stats['expired_deals']}")
    if stats["changed_deals"]:
        print(f"  🔄  Changed deals:      {stats['changed_deals']}")

    if total_changes == 0:
        print("  ✅  No changes detected since last snapshot.")

    print(f"{'=' * 56}\n")

    # Show sample changes (up to 10)
    shown = 0
    for prod, msgs in changes.items():
        if shown >= 10:
            remaining = len(changes) - shown
            print(f"  ... and {remaining} more products with changes.")
            break
        print(f"  [{prod}]")
        for msg in msgs:
            print(f"    {msg}")
        shown += 1


if __name__ == "__main__":
    run_tracker()
