# Costco UberEats Tracker

Automated price, stock, and deal tracker for Costco products on UberEats.
Scrapes multiple local Costco stores via GraphQL API interception, generates a comparison matrix, tracks changes over time, and produces an interactive HTML dashboard.

## Architecture

```
run.py              → Entry point (chains all 4 phases)
├── scraper.py      → Multi-store scraper via Playwright + CDP
├── analyzer.py     → Merges per-store CSVs into comparison matrix
├── tracker.py      → Detects stock/price/deal changes vs. history
└── dashboard.py    → Generates interactive HTML dashboard

config.py           → Shared constants (Chrome path, ports, tuning)
chrome_utils.py     → WSL → Windows Chrome CDP connection utilities
```

## Quick Start

```bash
# Full pipeline: scrape → analyze → track → dashboard
python run.py

# Skip the login prompt
python run.py -y

# Re-analyze existing data (no scraping)
python run.py --skip-scrape
```

## Change Tracking

The tracker detects the following changes between snapshots:

| Change Type        | Example                                    |
|--------------------|--------------------------------------------|
| 🆕 New Product     | Product newly appeared in catalog          |
| 🗑️ Removed Product | Product disappeared from catalog            |
| 📦 Restocked       | Was Out of Stock → now Available           |
| ⚠️ Out of Stock    | Was Available → now Out of Stock            |
| 💰 Price Drop      | Price decreased at a specific store        |
| 📈 Price Increase  | Price increased at a specific store        |
| 🔥 New Deal        | New discount appeared at a store           |
| ❌ Deal Expired     | Discount removed from a store              |
| 🔄 Deal Changed    | Discount text changed at a store           |

## Dashboard

Open `visualizer.html` in any browser after running the pipeline. Features:
- Product cards with images, prices, and availability
- Multi-store filter pills
- Deal-only filter toggle
- **Changes-only filter toggle** (new)
- Color-coded change badges (green = positive, red = negative, blue = info)
- Store exclusivity indicators

## Requirements

- Python 3.8+
- Windows Chrome (accessed via CDP from WSL)
- `pip install playwright requests beautifulsoup4`
- `playwright install chromium`
