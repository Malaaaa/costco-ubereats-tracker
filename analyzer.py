"""Multi-store product comparison and CSV matrix generator.

Reads per-store CSV files (products_*.csv) produced by the scraper,
merges them into a unified comparison matrix, and outputs both the
matrix CSV and per-store statistics. Also saves data to SQLite when
the storage backend is configured as 'sqlite'.
"""

import csv
import glob
import os
from collections import defaultdict

from config import STORAGE_BACKEND


def run_analyzer():
    """Merge per-store CSVs into a single comparison matrix."""
    print("=== MULTI-STORE COSTCO UBEREATS COMPARATOR ===")

    csv_files = glob.glob("products_*.csv")
    if not csv_files:
        print("No store CSV files found. Run scraper.py first.")
        return

    print(f"Found {len(csv_files)} store data files.")

    all_products = defaultdict(dict)
    store_names = [
        os.path.basename(f).replace(".csv", "").replace("products_", "")
        for f in csv_files
    ]

    # Load all per-store data into a unified product -> store -> metadata map
    for store_file, store_name in zip(csv_files, store_names):
        with open(store_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["name"].strip()
                all_products[name][store_name] = {
                    "price": row["price"],
                    "stock": row["stock"],
                    "deals": row["deals"],
                    "img_url": row.get("img_url", ""),
                }

    total_unique = len(all_products)
    print(f"Total Unique Products Across All Stores: {total_unique}")

    # Build the comparison matrix CSV (always generated for dashboard)
    matrix_filename = "costco_all_stores_comparison.csv"

    headers = ["Product Name", "Image_URL"]
    for store in store_names:
        headers.extend([
            f"{store} - Price",
            f"{store} - Stock",
            f"{store} - Deal",
        ])

    with open(matrix_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for product in sorted(all_products.keys()):
            best_img = ""
            for s in store_names:
                img = all_products[product].get(s, {}).get("img_url", "")
                if img:
                    best_img = img
                    break

            row = [product, best_img]
            for store in store_names:
                data = all_products[product].get(store)
                if data:
                    row.extend([data["price"], data["stock"], data["deals"]])
                else:
                    row.extend(["NOT CARRIED", "NOT CARRIED", ""])
            writer.writerow(row)

    print(f"[+] Comparison matrix saved: {matrix_filename}")

    # Save snapshot to SQLite database
    if STORAGE_BACKEND == "sqlite":
        from database import TrackerDB
        with TrackerDB() as db:
            db.create_snapshot(store_names, dict(all_products))

    # Per-store statistics
    for store in store_names:
        carried = sum(1 for p in all_products if store in all_products[p])
        oos = sum(
            1 for p in all_products
            if store in all_products[p]
            and all_products[p][store]["stock"] == "Out of Stock"
        )
        pct = carried / total_unique * 100 if total_unique else 0
        print(f"\n[Store] {store}:")
        print(f"  - Carries {carried} products ({pct:.1f}% of catalog)")
        print(f"  - Out of stock: {oos}")

    # Exclusivity analysis
    exclusive = [
        (prod, list(avail.keys())[0])
        for prod, avail in all_products.items()
        if len(avail) == 1
    ]
    universal = [
        prod for prod, avail in all_products.items()
        if len(avail) == len(store_names)
    ]

    print(f"\n[Analysis] {len(universal)} products at ALL stores.")
    print(f"[Analysis] {len(exclusive)} products exclusive to a single store.")

    if exclusive:
        print("\nSample Exclusive Items:")
        for product, store in exclusive[:5]:
            print(f"  - {product} (Only at {store})")


if __name__ == "__main__":
    run_analyzer()
