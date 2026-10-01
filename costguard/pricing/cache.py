"""SQLite Write-Through Pricing Cache for CostGuard."""

import sqlite3
import time
from pathlib import Path
from typing import Optional

from costguard.config import DEFAULT_DB_PATH


class PricingCache:
    """Manages local SQLite cache for Azure retail pricing records."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.hits = 0
        self.misses = 0
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a connection with appropriate isolation and timeout."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize the cache schema if it does not already exist."""
        # Ensure parent directories exist
        db_file = Path(self.db_path)
        if db_file.parent and not db_file.parent.exists():
            db_file.parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pricing_cache (
                    sku TEXT NOT NULL,
                    region TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    hourly_rate REAL NOT NULL,
                    cached_at INTEGER NOT NULL,
                    PRIMARY KEY (sku, region, currency)
                );
                """
            )
            conn.commit()

    def get(self, sku: str, region: str, currency: str) -> Optional[float]:
        """Look up hourly rate from cache.

        Args:
            sku: Resource SKU name (e.g. Standard_B2s).
            region: Normalized ARM region (e.g. eastus).
            currency: Currency code (e.g. INR).

        Returns:
            Hourly rate if cached, otherwise None.
        """
        if not sku or not region or not currency:
            return None

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT hourly_rate FROM pricing_cache
                WHERE sku = ? AND region = ? AND currency = ?
                """,
                (sku.strip(), region.strip().lower(), currency.strip().upper()),
            )
            row = cursor.fetchone()
            if row is not None:
                self.hits += 1
                return float(row["hourly_rate"])

        self.misses += 1
        return None

    def set(self, sku: str, region: str, currency: str, hourly_rate: float) -> None:
        """Store or update a pricing record in the SQLite cache.

        Args:
            sku: Resource SKU name.
            region: Normalized ARM region.
            currency: Currency code.
            hourly_rate: Resolved hourly price.
        """
        if not sku or not region or not currency:
            return

        now = int(time.time())
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO pricing_cache (sku, region, currency, hourly_rate, cached_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sku, region, currency) DO UPDATE SET
                    hourly_rate = excluded.hourly_rate,
                    cached_at = excluded.cached_at;
                """,
                (sku.strip(), region.strip().lower(), currency.strip().upper(), float(hourly_rate), now),
            )
            conn.commit()

    def clear(self) -> int:
        """Clear all records from the pricing cache.

        Returns:
            Number of rows deleted.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM pricing_cache;")
            count = cursor.rowcount
            conn.commit()
            return count

    def get_stats(self) -> tuple[int, int]:
        """Return (cache_hits, cache_misses)."""
        return self.hits, self.misses
