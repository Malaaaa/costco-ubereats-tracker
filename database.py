"""SQLite database layer for Costco UberEats Tracker.

Provides persistent storage for products, snapshots, and change events.
Replaces the CSV history/ directory and changes.json with a single
costco_tracker.db file.

Usage:
    from database import TrackerDB
    db = TrackerDB()
    db.save_snapshot(store_names, all_products)
    changes = db.detect_changes()
    db.close()
"""

import sqlite3
import os
from datetime import datetime

from config import DB_PATH


class TrackerDB:
    """SQLite-backed storage for product tracking data."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        """Create tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                image_url TEXT DEFAULT '',
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                store_count INTEGER DEFAULT 0,
                product_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS product_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                store_name TEXT NOT NULL,
                price TEXT DEFAULT 'NOT CARRIED',
                stock TEXT DEFAULT 'NOT CARRIED',
                deal TEXT DEFAULT '',
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                change_type TEXT NOT NULL,
                message TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                store_name TEXT DEFAULT '',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE INDEX IF NOT EXISTS idx_ps_snapshot ON product_snapshots(snapshot_id);
            CREATE INDEX IF NOT EXISTS idx_ps_product ON product_snapshots(product_id);
            CREATE INDEX IF NOT EXISTS idx_changes_snapshot ON changes(snapshot_id);
            CREATE INDEX IF NOT EXISTS idx_changes_product ON changes(product_id);
        """)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Product Management
    # ------------------------------------------------------------------

    def upsert_product(self, name, image_url=""):
        """Insert or update a product, returning its ID."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO products (name, image_url, first_seen, last_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   image_url = CASE WHEN excluded.image_url != '' THEN excluded.image_url ELSE products.image_url END,
                   last_seen = excluded.last_seen""",
            (name, image_url, now, now),
        )
        row = self.conn.execute(
            "SELECT id FROM products WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    # ------------------------------------------------------------------
    # Snapshot Management
    # ------------------------------------------------------------------

    def create_snapshot(self, store_names, all_products):
        """Save a full snapshot of all products across all stores.

        Args:
            store_names: List of store name strings
            all_products: Dict of {product_name: {store_name: {price, stock, deals, img_url}}}

        Returns:
            The new snapshot ID
        """
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            "INSERT INTO snapshots (timestamp, store_count, product_count) VALUES (?, ?, ?)",
            (now, len(store_names), len(all_products)),
        )
        snapshot_id = cursor.lastrowid

        for product_name, store_data in all_products.items():
            # Pick best image
            best_img = ""
            for s in store_names:
                img = store_data.get(s, {}).get("img_url", "")
                if img:
                    best_img = img
                    break

            product_id = self.upsert_product(product_name, best_img)

            for store_name in store_names:
                data = store_data.get(store_name)
                if data:
                    self.conn.execute(
                        """INSERT INTO product_snapshots
                           (snapshot_id, product_id, store_name, price, stock, deal)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            snapshot_id,
                            product_id,
                            store_name,
                            data["price"],
                            data["stock"],
                            data["deals"],
                        ),
                    )

        self.conn.commit()
        print(f"[DB] Snapshot #{snapshot_id} saved: {len(all_products)} products, {len(store_names)} stores")
        return snapshot_id

    def get_latest_snapshot_id(self):
        """Return the ID of the most recent snapshot, or None."""
        row = self.conn.execute(
            "SELECT id FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None

    def get_previous_snapshot_id(self, current_id):
        """Return the snapshot ID before the given one, or None."""
        row = self.conn.execute(
            "SELECT id FROM snapshots WHERE id < ? ORDER BY id DESC LIMIT 1",
            (current_id,),
        ).fetchone()
        return row["id"] if row else None

    def get_snapshot_data(self, snapshot_id):
        """Load all product data for a snapshot.

        Returns:
            Dict of {product_name: {store_name: {price, stock, deal}}}
        """
        rows = self.conn.execute(
            """SELECT p.name, ps.store_name, ps.price, ps.stock, ps.deal
               FROM product_snapshots ps
               JOIN products p ON p.id = ps.product_id
               WHERE ps.snapshot_id = ?""",
            (snapshot_id,),
        ).fetchall()

        data = {}
        for row in rows:
            name = row["name"]
            store = row["store_name"]
            if name not in data:
                data[name] = {}
            data[name][store] = {
                "price": row["price"],
                "stock": row["stock"],
                "deal": row["deal"],
            }
        return data

    def get_store_names(self, snapshot_id):
        """Get the distinct store names for a snapshot."""
        rows = self.conn.execute(
            """SELECT DISTINCT store_name FROM product_snapshots
               WHERE snapshot_id = ? ORDER BY store_name""",
            (snapshot_id,),
        ).fetchall()
        return [row["store_name"] for row in rows]

    # ------------------------------------------------------------------
    # Change Tracking
    # ------------------------------------------------------------------

    def record_change(self, snapshot_id, product_name, change_type, message,
                      severity="info", store_name=""):
        """Record a change event."""
        product_id = self.conn.execute(
            "SELECT id FROM products WHERE name = ?", (product_name,)
        ).fetchone()

        if not product_id:
            product_id = self.upsert_product(product_name)
        else:
            product_id = product_id["id"]

        self.conn.execute(
            """INSERT INTO changes
               (snapshot_id, product_id, change_type, message, severity, store_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (snapshot_id, product_id, change_type, message, severity, store_name),
        )

    def get_latest_changes(self, snapshot_id=None):
        """Get changes for a snapshot (or latest). Returns dict compatible with dashboard.

        Returns:
            Dict of {product_name: [message_str, ...]}
        """
        if snapshot_id is None:
            snapshot_id = self.get_latest_snapshot_id()
        if snapshot_id is None:
            return {}

        rows = self.conn.execute(
            """SELECT p.name, c.message
               FROM changes c
               JOIN products p ON p.id = c.product_id
               WHERE c.snapshot_id = ?
               ORDER BY p.name""",
            (snapshot_id,),
        ).fetchall()

        changes = {}
        for row in rows:
            changes.setdefault(row["name"], []).append(row["message"])
        return changes

    def get_change_stats(self, snapshot_id):
        """Get aggregated change statistics for a snapshot."""
        rows = self.conn.execute(
            """SELECT change_type, COUNT(*) as cnt
               FROM changes WHERE snapshot_id = ?
               GROUP BY change_type""",
            (snapshot_id,),
        ).fetchall()
        return {row["change_type"]: row["cnt"] for row in rows}

    # ------------------------------------------------------------------
    # Query Helpers
    # ------------------------------------------------------------------

    def get_all_products(self):
        """Return all products ordered by name."""
        return self.conn.execute(
            "SELECT * FROM products ORDER BY name"
        ).fetchall()

    def get_snapshot_count(self):
        """Return total number of snapshots."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM snapshots").fetchone()
        return row["cnt"]

    def get_product_history(self, product_name, limit=10):
        """Get price/stock history for a specific product across snapshots."""
        rows = self.conn.execute(
            """SELECT s.timestamp, ps.store_name, ps.price, ps.stock, ps.deal
               FROM product_snapshots ps
               JOIN snapshots s ON s.id = ps.snapshot_id
               JOIN products p ON p.id = ps.product_id
               WHERE p.name = ?
               ORDER BY s.timestamp DESC
               LIMIT ?""",
            (product_name, limit * 10),  # multiply by ~stores
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
