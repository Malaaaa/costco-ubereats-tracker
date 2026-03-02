"""HTML dashboard generator for Costco UberEats product comparison.

Reads the comparison matrix CSV and changes.json to produce a single-file
interactive HTML dashboard with product cards, multi-store filtering,
deal highlighting, and change tracking badges.
"""

import csv
import json
import os


def _change_badge_style(change_text):
    """Return a Tailwind CSS class string based on the change type emoji."""
    if any(k in change_text for k in ["🆕", "📦", "💰", "🔥"]):
        # Positive: green
        return "bg-emerald-50 text-emerald-700 border-emerald-200"
    elif any(k in change_text for k in ["🗑️", "⚠️", "📈", "❌"]):
        # Negative: red/amber
        return "bg-red-50 text-red-700 border-red-200"
    elif "🔄" in change_text:
        # Info: blue
        return "bg-blue-50 text-blue-700 border-blue-200"
    # Default
    return "bg-gray-50 text-gray-700 border-gray-200"


def build_dashboard():
    """Generate visualizer.html from comparison CSV + changes.json."""
    products = []
    store_names = []
    changes = {}

    if os.path.exists("changes.json"):
        with open("changes.json", "r", encoding="utf-8") as f:
            changes = json.load(f)

    try:
        with open("costco_all_stores_comparison.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            store_names = [
                c.replace(" - Price", "")
                for c in reader.fieldnames
                if c.endswith(" - Price")
            ]
            for row in reader:
                products.append(row)
    except Exception as e:
        print(f"[-] Could not build dashboard. Run analyzer first. Error: {e}")
        return

    print(
        f"[+] Generating dashboard for {len(products)} products "
        f"across {len(store_names)} stores..."
    )

    # ---------- HTML HEADER ----------
    html = f'''\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Costco UberEats Analyzer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background-color: #f3f4f6; font-family: 'Inter', sans-serif; }}
        .glass {{ background: rgba(255,255,255,0.85); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.3); }}
    </style>
    <script>
        let selectedStores = ["ALL"];

        function toggleStore(storeName) {{
            if (storeName === 'ALL') {{
                selectedStores = ['ALL'];
            }} else {{
                if (selectedStores.includes('ALL')) selectedStores = [];
                if (selectedStores.includes(storeName)) {{
                    selectedStores = selectedStores.filter(s => s !== storeName);
                    if (selectedStores.length === 0) selectedStores = ['ALL'];
                }} else {{
                    selectedStores.push(storeName);
                }}
            }}
            document.querySelectorAll('.store-pill').forEach(pill => {{
                const sn = pill.getAttribute('data-store');
                const activeClass = 'store-pill cursor-pointer select-none text-xs px-3 py-1.5 rounded-full font-bold transition-colors bg-blue-600 text-white shadow-sm';
                const inactiveClass = 'store-pill cursor-pointer select-none text-xs px-3 py-1.5 rounded-full font-bold transition-colors bg-white border border-gray-300 text-gray-600 hover:bg-gray-100';
                if (selectedStores.includes('ALL')) {{
                    pill.className = (sn === 'ALL') ? activeClass : inactiveClass;
                }} else {{
                    pill.className = selectedStores.includes(sn) ? activeClass : inactiveClass;
                }}
            }});
            applyFilters();
        }}

        function applyFilters() {{
            const q = document.getElementById('search_box').value.toLowerCase();
            const dealOnly = document.getElementById('deals_toggle').checked;
            const changesOnly = document.getElementById('changes_toggle').checked;

            document.querySelectorAll('.product-card').forEach(card => {{
                const name = card.getAttribute('data-name').toLowerCase();
                const stores = card.getAttribute('data-stores').split(',');
                const hasDeal = card.getAttribute('data-has-deal') === 'true';
                const hasChange = card.getAttribute('data-has-change') === 'true';

                let show = true;
                if (q && !name.includes(q)) show = false;
                if (!selectedStores.includes('ALL')) {{
                    let found = false;
                    for (let s of selectedStores) {{
                        if (stores.includes(s)) {{ found = true; break; }}
                    }}
                    if (!found) show = false;
                }}
                if (dealOnly && !hasDeal) show = false;
                if (changesOnly && !hasChange) show = false;

                card.style.display = show ? 'flex' : 'none';
            }});
        }}
    </script>
</head>
<body class="p-8">
    <div class="max-w-screen-2xl mx-auto">
        <div class="flex flex-col xl:flex-row xl:justify-between xl:items-end mb-8 gap-6">
            <div>
                <h1 class="text-4xl font-extrabold text-gray-900 mb-2 tracking-tight">Costco Tracker</h1>
                <p class="text-gray-600 font-medium">Live Matrix of Delivery Pricing & Stock ({len(store_names)} locations scanned)</p>
            </div>

            <div class="flex flex-col gap-4 bg-white px-6 py-5 rounded-xl shadow-sm border border-gray-200" style="min-width:55%">
                <div class="flex flex-wrap gap-4 items-center w-full">
                    <input type="text" id="search_box" onkeyup="applyFilters()" placeholder="🔍 Search products..." class="px-4 py-2 border border-blue-200 bg-blue-50 focus:bg-white rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 flex-1 text-sm font-medium transition-all">

                    <div class="flex items-center bg-red-50 px-3 py-2 rounded-lg border border-red-100 hover:bg-red-100 transition-colors">
                        <input type="checkbox" id="deals_toggle" onchange="applyFilters()" class="w-4 h-4 text-red-600 rounded border-red-300 focus:ring-red-500 cursor-pointer">
                        <label for="deals_toggle" class="ml-2 font-bold text-red-700 uppercase tracking-widest text-[11px] cursor-pointer select-none">Deals Only</label>
                    </div>

                    <div class="flex items-center bg-purple-50 px-3 py-2 rounded-lg border border-purple-100 hover:bg-purple-100 transition-colors">
                        <input type="checkbox" id="changes_toggle" onchange="applyFilters()" class="w-4 h-4 text-purple-600 rounded border-purple-300 focus:ring-purple-500 cursor-pointer">
                        <label for="changes_toggle" class="ml-2 font-bold text-purple-700 uppercase tracking-widest text-[11px] cursor-pointer select-none">Changes Only</label>
                    </div>
                </div>

                <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-gray-100 mt-1">
                    <span class="text-xs font-bold text-gray-400 uppercase tracking-wide mr-2">Filter Warehouses:</span>
                    <div onclick="toggleStore('ALL')" data-store="ALL" class="store-pill cursor-pointer select-none text-xs px-3 py-1.5 rounded-full font-bold transition-colors bg-blue-600 text-white">All</div>
'''

    # Store filter pills
    for s in store_names:
        clean_s = (
            s.replace("Costco_", "")
             .replace("_", " ")
             .replace(" Toronto On", "")
             .replace(" Scarborough On", "")
             .replace(" Mississauga On", "")
             .replace(" Etobicoke On", "")
             .replace(" North York On", "")
        )
        safe_s = clean_s.replace("'", "\\'")
        html += (
            f'                    <div onclick="toggleStore(\'{safe_s}\')" '
            f'data-store="{clean_s}" '
            f'class="store-pill cursor-pointer select-none text-xs px-3 py-1.5 '
            f'rounded-full font-bold transition-colors bg-white border '
            f'border-gray-300 text-gray-600 hover:bg-gray-100">{clean_s}</div>\n'
        )

    html += '''\
                </div>
            </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
'''

    # ---------- PRODUCT CARDS ----------
    rendered_count = 0

    def has_any_deal(p):
        return any(
            p.get(f"{s} - Deal", "").strip()
            for s in store_names
        )

    # Sort: deals first, then alphabetical
    products.sort(key=lambda x: (not has_any_deal(x), x.get("Product Name", "")))

    for p in products:
        prod_name = (
            p.get("Product Name", "Unnamed Product")
             .replace('"', '&quot;')
             .replace("'", '&#39;')
        )
        prod_changes = changes.get(p.get("Product Name", "Unnamed Product"), [])
        has_change = bool(prod_changes)

        # Build change badges with severity-based colors
        changes_ui = ""
        if prod_changes:
            badges = []
            for c in prod_changes:
                style = _change_badge_style(c)
                badges.append(
                    f"<span class='{style} text-[10px] px-1.5 py-0.5 "
                    f"rounded border mt-1 inline-block font-medium'>{c}</span>"
                )
            changes_ui = (
                f"<div class='mt-1 flex flex-wrap gap-1'>{''.join(badges)}</div>"
            )

        img = p.get("Image_URL") or "https://via.placeholder.com/150?text=No+Image"

        store_tags = ""
        prices = []
        product_has_deal = False
        deals_map = {}
        active_stores_list = []

        for s in store_names:
            price_val = p.get(f"{s} - Price", "NOT CARRIED").strip()
            deal_val = p.get(f"{s} - Deal", "").strip()

            if price_val and price_val != "NOT CARRIED":
                clean_s = (
                    s.replace("Costco_", "")
                     .replace("_", " ")
                     .replace(" Toronto On", "")
                     .replace(" North York On", "")
                     .replace(" Etobicoke On", "")
                     .replace(" Scarborough On", "")
                     .replace(" Mississauga On", "")
                )
                active_stores_list.append(clean_s)

                display_s = clean_s[:16] + ".." if len(clean_s) > 18 else clean_s

                if deal_val:
                    product_has_deal = True
                    deals_map.setdefault(deal_val, []).append(display_s)

                store_tags += (
                    f'<span class="inline-block bg-blue-100 text-blue-800 '
                    f'border-blue-200 text-[10px] px-2 py-0.5 rounded-full '
                    f'uppercase font-bold tracking-wide mr-1 mt-1 shadow-sm '
                    f'border" title="{s} - {price_val}">{display_s}</span>'
                )
                prices.append(price_val)

        if not prices:
            continue

        rendered_count += 1

        # Compute lowest price
        lowest_price = "$?"
        try:
            numerical = [
                float(pr.replace("$", "").replace(",", "").strip())
                for pr in prices
                if "$" in pr
            ]
            if numerical:
                lowest_price = f"${min(numerical):.2f}"
            else:
                lowest_price = min(prices)
        except Exception:
            lowest_price = min(prices)

        # Deal ribbon
        deal_ribbon = ""
        if product_has_deal:
            deal_ribbon = (
                '<div class="absolute top-2 right-2 bg-gradient-to-r '
                'from-red-600 to-rose-500 text-white text-[10px] font-black '
                'px-3 py-1.5 rounded-full shadow-lg border border-red-400 '
                'uppercase tracking-widest animate-pulse z-10">Sale Active</div>'
            )

        # Store exclusivity badge
        exclusivity = ""
        if len(prices) == 1 and not product_has_deal:
            exclusivity = (
                '<div class="absolute top-2 left-2 bg-gray-800 text-white '
                'text-[9px] font-bold px-2 py-1 rounded select-none '
                'opacity-80 uppercase z-10">Store Exclusive</div>'
            )

        # Deals box
        deals_box = ""
        if deals_map:
            deal_items = []
            for d_text, s_list in deals_map.items():
                if len(s_list) == len(store_names) and len(store_names) > 1:
                    store_label = "All Warehouses"
                elif len(s_list) >= 4:
                    store_label = f"{len(s_list)} Warehouses"
                else:
                    store_label = ", ".join(s_list)

                deal_items.append(
                    f"<div class='text-xs text-red-600 font-bold mb-1'>"
                    f"💥 {d_text} "
                    f"<span class='text-[10px] text-gray-500 font-normal'>"
                    f"({store_label})</span></div>"
                )
            deals_box = (
                "<div class='mt-2 p-2 bg-red-50 rounded border border-red-100'>"
                + "".join(deal_items)
                + "</div>"
            )

        active_stores_str = ",".join(active_stores_list).replace('"', '&quot;')

        html += f'''\
            <div class="product-card glass rounded-xl shadow-sm overflow-hidden hover:shadow-xl transition-all relative flex flex-col hover:-translate-y-1 hover:border-blue-300"
                 data-has-deal="{str(product_has_deal).lower()}"
                 data-has-change="{str(has_change).lower()}"
                 data-name="{prod_name}"
                 data-stores="{active_stores_str}">
                {deal_ribbon}
                {exclusivity}
                <div class="h-48 w-full bg-white flex items-center justify-center p-4">
                    <img src="{img}" class="max-h-full max-w-full object-contain mix-blend-multiply" loading="lazy" alt="product image">
                </div>
                <div class="p-5 flex-1 flex flex-col bg-gradient-to-b from-transparent to-gray-50/50">
                    <h3 class="text-sm font-bold text-gray-800 line-clamp-2 mb-2 leading-tight flex-1" title="{prod_name}">{prod_name}</h3>

                    {deals_box}
                    {changes_ui}

                    <div class="flex justify-between items-end mt-2 pb-2">
                        <div>
                            <span class="text-xs text-gray-500 font-semibold uppercase tracking-wider block mb-0.5">Best Base Price</span>
                            <span class="text-2xl font-black text-emerald-600 tracking-tighter">{lowest_price}</span>
                        </div>
                        <div class="text-right">
                           <span class="text-xs font-bold text-gray-400 block pb-1">{len(prices)}/{len(store_names)} Stores</span>
                        </div>
                    </div>
                    <div class="mt-2 text-xs text-gray-500 border-t border-gray-100 pt-3 flex flex-wrap gap-1">
                        {store_tags}
                    </div>
                </div>
            </div>
'''

    html += '''\
        </div>
    </div>
</body>
</html>
'''

    with open("visualizer.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(
        f"[+] Dashboard generated: visualizer.html "
        f"({rendered_count} products rendered)"
    )


if __name__ == "__main__":
    build_dashboard()
