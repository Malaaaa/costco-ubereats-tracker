"""Entry point for the Costco UberEats Tracker pipeline.

Execution order:
  1. Scrape all local Costco stores via API interception
  2. Analyze and merge per-store data into comparison matrix
  3. Track changes against previous snapshot
  4. Generate the HTML dashboard

Usage:
  python run.py          # Full pipeline (scrape + analyze + track + dashboard)
  python run.py -y       # Skip login prompt (auto-resume)
  python run.py --skip-scrape   # Skip scraping, only re-analyze existing data
"""

import sys

from scraper import run_scraper
from analyzer import run_analyzer
from tracker import run_tracker
from dashboard import build_dashboard


def main():
    skip_scrape = "--skip-scrape" in sys.argv

    if not skip_scrape:
        print("\n" + "=" * 60)
        print("  PHASE 1: SCRAPING")
        print("=" * 60)
        run_scraper()

    print("\n" + "=" * 60)
    print("  PHASE 2: ANALYSIS")
    print("=" * 60)
    run_analyzer()

    print("\n" + "=" * 60)
    print("  PHASE 3: CHANGE TRACKING")
    print("=" * 60)
    run_tracker()

    print("\n" + "=" * 60)
    print("  PHASE 4: DASHBOARD GENERATION")
    print("=" * 60)
    build_dashboard()

    print("\n[✓] Pipeline complete. Open visualizer.html in your browser.")


if __name__ == "__main__":
    main()
