"""Multi-store Costco UberEats scraper using GraphQL API interception.

Connects to a Windows Chrome instance via CDP, searches for all local Costco
stores on UberEats, and extracts product data by intercepting the GraphQL
network responses while scrolling through each store page.
"""

import csv
import glob
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

from config import (
    DEAL_KEYWORDS,
    EXCLUDED_NAME_PREFIXES,
    INITIAL_LOAD_DELAY,
    MAX_SCROLLS,
    PAYLOAD_ADDRESS,
    SCROLL_DELAY,
    SCROLL_DISTANCE,
    STALL_THRESHOLD,
    STORE_LOAD_DELAY,
)
from chrome_utils import find_cdp_url, start_windows_chrome, stop_windows_chrome

# Module-level buffer for API-intercepted products (reset per store)
_api_products = {}


# ---------------------------------------------------------------------------
# API Interception
# ---------------------------------------------------------------------------

def _extract_overlay_text(node):
    """Recursively pull all 'text' strings from a nested JSON structure."""
    results = []
    if isinstance(node, dict):
        if "text" in node and isinstance(node["text"], str):
            results.append(node["text"])
        for v in node.values():
            results.extend(_extract_overlay_text(v))
    elif isinstance(node, list):
        for item in node:
            results.extend(_extract_overlay_text(item))
    return results


def _find_items(node):
    """Walk the JSON tree, pulling structured product entries into _api_products."""
    if isinstance(node, dict):
        if "title" in node and "price" in node:
            price_val = 0.0
            purchase_options = (
                node.get("purchaseInfo", {})
                    .get("purchaseOptions", [])
            )
            if purchase_options:
                v2 = purchase_options[0].get("purchasePriceV2", {})
                try:
                    base = float(v2.get("base", {}).get("low", 0))
                    exp = float(v2.get("exponent", 0))
                    price_val = base * (10 ** exp)
                except (ValueError, TypeError):
                    pass

            stock = "Available"
            if (node.get("isSoldOut", False)
                    or node.get("itemAvailabilityState") == "SOLD_OUT"):
                stock = "Out of Stock"

            deal = ""
            tags = node.get("imageOverlayElements", [])
            if tags:
                for t in _extract_overlay_text(tags):
                    if any(kw in t.lower() for kw in DEAL_KEYWORDS):
                        deal = t.strip()
                        break

            img_url = node.get("imageUrl", "")
            title = node.get("title", "").strip()

            if title and title not in _api_products:
                _api_products[title] = {
                    "name": title,
                    "price": f"${price_val:,.2f}" if price_val > 0 else "N/A",
                    "stock": stock,
                    "deals": deal,
                    "img_url": img_url,
                    "full_text": "(API Extracted via GraphQL Payload)",
                }

        for v in node.values():
            _find_items(v)

    elif isinstance(node, list):
        for item in node:
            _find_items(item)


def _on_response(response):
    """Playwright response handler – intercept UberEats GraphQL payloads."""
    if "getStoreV1" not in response.url and "graphql" not in response.url:
        return
    try:
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            _find_items(response.json())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Page Interaction
# ---------------------------------------------------------------------------

def _scroll_and_capture(page):
    """Scroll through a store page, triggering lazy-loaded API responses."""
    print("    [~] Binding GraphQL API Interceptor...")
    _api_products.clear()
    page.on("response", _on_response)

    print("    [~] Harvesting network packets...")
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    time.sleep(INITIAL_LOAD_DELAY)

    last_height = page.evaluate("document.body.scrollHeight")
    stall_count = 0
    scrolled = 0

    while scrolled < MAX_SCROLLS:
        page.evaluate(f"window.scrollBy(0, {SCROLL_DISTANCE})")
        time.sleep(SCROLL_DELAY)
        scrolled += 1

        new_height = page.evaluate("document.body.scrollHeight")

        if new_height == last_height:
            # Attempt to click a "Load more" / "Show more" button
            load_more = page.locator(
                "button:has-text('Load more'), button:has-text('Show more')"
            )
            if load_more.count() > 0 and load_more.first.is_visible():
                print("    [~] Clicking 'Load more' button...")
                load_more.first.click(force=True)
                time.sleep(4)
                continue

            stall_count += 1
            if stall_count >= STALL_THRESHOLD:
                print("    [~] Scroll bottom reached. API ingestion complete.")
                break
        else:
            stall_count = 0

        last_height = new_height

        if scrolled % 4 == 0 or stall_count > 0:
            print(
                f"        Scrolled Y:{new_height} [{scrolled}/{MAX_SCROLLS}]. "
                f"Captured {len(_api_products)} products via JSON API."
            )

    try:
        page.remove_listener("response", _on_response)
    except Exception:
        pass

    return list(_api_products.values())


def _discover_store_urls(page):
    """From the UberEats search results page, collect all Costco store URLs."""
    search_url = (
        f"https://www.ubereats.com/ca/search?"
        f"eventSource=searchHistoryV2&pl={PAYLOAD_ADDRESS}"
        f"&q=costco&sc=SEARCH_SUGGESTION"
        f"&searchType=GLOBAL_SEARCH&vertical=ALL"
    )
    print("[+] Querying search engine for 'Costco' stores...")
    page.goto(search_url, timeout=90000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(8)

    # Scroll down to trigger React's Intersection Observers
    print("[+] Forcing UI lazyload to reveal hidden carousels...")
    for _ in range(8):
        page.keyboard.press("PageDown")
        time.sleep(1.5)

    # Force any hidden horizontal carousels to render by removing overflow
    page.evaluate("""
        document.querySelectorAll('ul, div, section').forEach(el => {
            if(el.scrollWidth > el.clientWidth) {
                el.style.overflow = 'visible';
                el.scrollLeft = el.scrollWidth;
            }
        });
    """)
    time.sleep(3)

    # Collect all Costco store links
    seen = {}
    for anchor in page.locator("a").all():
        try:
            href = anchor.get_attribute("href")
            if href and "costco" in href.lower() and "/store/" in href.lower():
                base_href = href.split("?")[0]
                full_url = (
                    "https://www.ubereats.com" + base_href
                    if base_href.startswith("/")
                    else base_href
                )
                seen.setdefault(full_url, True)
        except Exception:
            continue

    return list(seen.keys())


def _store_name_from_url(url, index):
    """Derive a human-readable store name from its UberEats URL slug."""
    try:
        slug = url.split("/store/")[1].split("/")[0].split("?")[0]
        return slug.replace("-", " ").title()
    except Exception:
        return f"Costco_Branch_{index + 1}"


# ---------------------------------------------------------------------------
# Main Entry
# ---------------------------------------------------------------------------

def run_scraper():
    """Full multi-store scrape pipeline.

    1. Launches Chrome, connects via CDP
    2. Discovers all local Costco stores
    3. Scrapes each store via API interception
    4. Saves per-store CSV files
    """
    print("[======================================================]")
    print("[+] Starting Multi-Store Costco UberEats Scraper")

    # Clean up previous per-store CSVs
    for f in glob.glob("products_*.csv"):
        os.remove(f)

    start_windows_chrome()
    cdp_url = find_cdp_url()

    if not cdp_url:
        print("[-] Error: Could not bind CDP to Windows Chrome.")
        return

    with sync_playwright() as pw:
        try:
            print("[+] Connecting Playwright -> Windows Chrome...")
            browser = pw.chromium.connect_over_cdp(cdp_url)
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            print("[+] Navigating to UberEats Homepage...")
            page.goto("https://www.ubereats.com/", timeout=90000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(4)

            # Optional login prompt
            print("\n[?] Do you want to log into your UberEats / Costco account?")
            print("    (Logging in fetches personalized deals and membership discounts.)")

            if "-y" in sys.argv:
                print("    [!] Auto-resume: '-y' flag detected.")
            else:
                choice = input("    Type 'y' to login, or press ENTER to skip: ").strip().lower()
                if choice == "y":
                    print("[!] ACTION REQUIRED: Log in using the Chrome window.")
                    input("[!] Press ENTER after you are logged in... ")
                    print("[+] Login confirmed. Resuming...")

            store_urls = _discover_store_urls(page)
            print(f"[+] Detected {len(store_urls)} Costco warehouses.")

            for i, url in enumerate(store_urls):
                print(f"\n[{'=' * 54}]")
                print(f"[+] [{i + 1}/{len(store_urls)}] Scanning: {url}")
                try:
                    page.goto(url, timeout=90000)
                    page.wait_for_load_state("domcontentloaded")
                    time.sleep(STORE_LOAD_DELAY)
                except Exception as e:
                    print(f"[-] Connection dropped for {url}: {e}")
                    continue

                store_name = _store_name_from_url(url, i)
                if not store_name or len(store_name) < 4:
                    store_name = f"Costco_Branch_{i + 1}"

                print(f"[+] Store: {store_name}")
                products = _scroll_and_capture(page)

                if products:
                    filename = f"products_{store_name.replace(' ', '_')}.csv"
                    with open(filename, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(
                            f,
                            fieldnames=["name", "price", "stock", "deals", "img_url", "full_text"],
                        )
                        writer.writeheader()
                        writer.writerows(products)
                    print(f"[+] Exported {len(products)} products -> {filename}")
                else:
                    print("[-] No products captured. Skipping this store.")

            browser.close()
            stop_windows_chrome()

        except Exception as e:
            print(f"[-] Execution error: {e}")
            stop_windows_chrome()


if __name__ == "__main__":
    run_scraper()
