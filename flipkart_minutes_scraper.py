import asyncio
import re
import time
import pandas as pd
import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# User configurations
BRANDS = ["Amul", "Ensure", "Horlicks", "Nestle", "Similac"]
OUTPUT_FILE = "Flipkart_Minutes_Brands.xlsx"

# Cookies provided by the user to restore location/session
# Loaded securely from an environment variable (FLIPKART_COOKIES) or local cookies.json
import os
import json

COOKIES = []
_cookies_env = os.getenv("FLIPKART_COOKIES")
if _cookies_env:
    try:
        COOKIES = json.loads(_cookies_env)
    except Exception:
        pass

if not COOKIES and os.path.exists("cookies.json"):
    try:
        with open("cookies.json", "r") as f:
            COOKIES = json.load(f)
    except Exception:
        pass

def clean_text(text):
    if not text:
        return None
    cleaned = " ".join(text.split()).strip()
    return cleaned if cleaned else None

def parse_price(price_str):
    if not price_str:
        return None
    num_str = re.sub(r'[^\d]', '', price_str)
    return float(num_str) if num_str else None

def parse_products(html_content, brand_name):
    soup = BeautifulSoup(html_content, "html.parser")
    products_list = []
    
    # Identify product links
    product_links = soup.find_all("a", href=lambda h: h and "/p/" in h)
    seen_containers = set()
    cards = []
    
    for a in product_links:
        # Find unique container cards containing image and price details
        current = a
        card_container = None
        for _ in range(5):
            parent = current.parent
            if not parent:
                break
            has_img = len(parent.find_all("img")) > 0
            has_price = len(parent.find_all(string=re.compile("₹"))) > 0
            if has_img and has_price:
                card_container = parent
                break
            current = parent
            
        if card_container:
            if card_container not in seen_containers:
                seen_containers.add(card_container)
                cards.append((card_container, a))
        else:
            if a not in seen_containers:
                seen_containers.add(a)
                cards.append((a, a))
                
    for card, a in cards:
        # 1. Page URL
        href = a['href']
        page_url = urljoin("https://www.flipkart.com", href)
        
        # 2. SKU Title & SKU Name
        sku_title = None
        title_div = a.find("div")
        if title_div:
            # Find leaf divs (divs with no child divs)
            leaf_divs = [d for d in a.find_all("div") if not d.find("div")]
            title_candidates = [d.text.strip() for d in leaf_divs if not re.search(r'\d+\s*mins?', d.text, re.IGNORECASE)]
            if title_candidates:
                sku_title = clean_text(title_candidates[0])
            else:
                sku_title = clean_text(title_div.text)
        else:
            sku_title = clean_text(a.text)
            
        # Clean trailing delivery time, "AD", etc.
        if sku_title:
            sku_title = re.sub(r'\d+\s*mins?$', '', sku_title).strip()
            sku_title = re.sub(r'\bAD$', '', sku_title).strip()
            sku_title = clean_text(sku_title)
        sku_name = sku_title
        
        # Clean brand name detection from SKU Title
        detected_brand = brand_name # fallback to search brand name (e.g. Amul, Nestle)
        if sku_title:
            for b in ["Amul", "Ensure", "Horlicks", "Nestle", "Similac"]:
                if re.search(r'\b' + re.escape(b) + r'\b', sku_title, re.IGNORECASE):
                    detected_brand = b
                    break
        
        # 3. Image URL
        img = card.find("img")
        image_url = img['src'] if img and img.has_attr('src') else None
        if image_url == "":
            image_url = None
            
        # 4. Prices (MRP & Selling Price)
        price_nodes = card.find_all(string=re.compile("₹"))
        price_values = []
        for node in price_nodes:
            val = parse_price(node)
            if val is not None and val not in price_values:
                price_values.append(val)
                
        if len(price_values) >= 2:
            price_values.sort(reverse=True)
            mrp = price_values[0]
            selling_price = price_values[1]
        elif len(price_values) == 1:
            mrp = price_values[0]
            selling_price = price_values[0]
        else:
            mrp = None
            selling_price = None
            
        # 5. Discount
        discount = None
        if mrp is not None and selling_price is not None and mrp > selling_price:
            discount_val = mrp - selling_price
            discount = f"₹{int(discount_val)} off"
            
        # Check for explicit discount text badge (e.g. "10% Off")
        discount_badge = card.find(string=re.compile(r'\d+%\s*Off', re.IGNORECASE))
        if discount_badge:
            discount = clean_text(discount_badge)
        else:
            percent_node = card.find(string=re.compile(r'\d+%'))
            off_node = card.find(string=re.compile(r'Off', re.IGNORECASE))
            if percent_node and off_node:
                discount = f"{clean_text(percent_node)} {clean_text(off_node)}"
                
        # 6. Gram / Size / Qty
        size = None
        qty = "Pack of 1"
        
        # Look for weight/volume pattern: e.g. 500 ml, 1 kg, 1 L, 250 g
        size_pattern = re.compile(r'\b\d+(\.\d+)?\s*(g|kg|ml|l|ltr|litres|litre|gm|gms|pcs|pack|units)\b', re.IGNORECASE)
        for node in card.find_all(string=True):
            node_clean = clean_text(node)
            if not node_clean:
                continue
            match = size_pattern.search(node_clean)
            if match:
                if "min" not in node_clean.lower() and "₹" not in node_clean and len(node_clean) < 25:
                    size = node_clean
                    break
                    
        # Parse qty from title or size
        if sku_title:
            qty_pattern = re.compile(r'\b(pack\s*of\s*\d+|\d+\s*pack)\b', re.IGNORECASE)
            qty_match = qty_pattern.search(sku_title)
            if not qty_match and size:
                qty_match = qty_pattern.search(size)
            if qty_match:
                qty = clean_text(qty_match.group(0))
            
        # 7. Sub-brand
        sub_brand = None
        if sku_title and detected_brand and sku_title.lower().startswith(detected_brand.lower()):
            sub_brand_text = sku_title[len(detected_brand):].strip()
            sub_brand_text = re.sub(r'^[\s,\-]+', '', sub_brand_text).strip()
            if sub_brand_text:
                sub_brand = sub_brand_text
                
        # Extract pid from page_url
        pid_match = re.search(r'[?&]pid=([^&]+)', page_url)
        web_pid = pid_match.group(1) if pid_match else None
        
        products_list.append({
            "rb_sku_platform_id": None,
            "pf_id": None,
            "platform_name": "Flipkart Minutes",
            "reseller_id": None,
            "sku_id": None,
            "web_pid": web_pid,
            "group_id": None,
            "brand_id": None,
            "brand_category_id": None,
            "msl": None,
            "cluster": None,
            "ean_code": None,
            "rb_code": None,
            "pantry_code": None,
            "created_by": None,
            "created_on": None, # Will be filled in main with execution timestamp
            "modified_by": None,
            "modified_on": None,
            "status": None,
            "page_url": page_url,
            "sku_name": sku_name,
            "is_competitor": None,
            "sku_title": sku_title,
            "comp_mapp": None,
            "brand_name": detected_brand,
            "brand_category": None,
            "item_code": None,
            "sub_brand": sub_brand,
            "mrp": mrp,
            "gram": size,
            "price_range": selling_price,
            "qty": qty,
            "image_url": image_url,
            "guardrail": None,
            "best_seller_category": None,
            "best_seller_category_id": None,
            "platform_uuid": None,
            "platform_account_id": None,
            "company_id": None
        })
        
    return products_list

async def crawl_brand(context, brand_name, idx):
    # Staggered launch to bypass anti-bot locks
    await asyncio.sleep(idx * 1.5)
    
    page = await context.new_page()
    await Stealth().apply_stealth_async(page) # Enable stealth checks bypass
    
    url = f"https://www.flipkart.com/search?q={brand_name}&marketplace=HYPERLOCAL"
    print(f"[{brand_name}] Navigating to: {url}")
    
    brand_products = {}
    
    try:
        # Load the search page
        await page.goto(url, wait_until="load", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Scroll and extract logic
        max_scrolls = 20
        no_new_products_count = 0
        
        for scroll_idx in range(max_scrolls):
            # Extract HTML page source
            html_content = await page.content()
            
            # Parse products from current HTML source
            current_products = parse_products(html_content, brand_name)
            
            # Add to unique dict
            new_added = 0
            for p in current_products:
                url_key = p["page_url"]
                if url_key not in brand_products:
                    brand_products[url_key] = p
                    new_added += 1
                    
            print(f"[{brand_name}] Scroll step {scroll_idx + 1}: Found {len(current_products)} items in DOM. Added {new_added} new. Total unique: {len(brand_products)}")
            
            # If we've gathered at least 20 unique products, we can stop scrolling
            if len(brand_products) >= 20:
                break
                
            # Scroll container down by 1000px dynamically
            scrolled = await page.evaluate("""() => {
                const divs = Array.from(document.querySelectorAll('div'));
                const container = divs.find(d => {
                    const s = window.getComputedStyle(d);
                    return (s.overflowY === 'auto' || s.overflowY === 'scroll') && d.scrollHeight > d.clientHeight;
                });
                if (container) {
                    container.scrollBy(0, 1000);
                    return true;
                }
                return false;
            }""")
            
            # If no container scrollable, fallback to window scroll
            if not scrolled:
                await page.evaluate("window.scrollBy(0, 1000)")
                
            await page.wait_for_timeout(1500)
            
            # If we scrolled and found 0 new products multiple times, stop
            if new_added == 0:
                no_new_products_count += 1
                if no_new_products_count >= 4:
                    break
            else:
                no_new_products_count = 0
                
        await page.close()
        
        # Get list of unique brand products and trim to exactly 20 if we got more
        final_list = list(brand_products.values())
        if len(final_list) > 20:
            final_list = final_list[:20]
            
        print(f"[{brand_name}] Completed. Returning {len(final_list)} unique products.")
        return final_list
        
    except Exception as e:
        print(f"[{brand_name}] Error during crawling: {e}")
        try:
            await page.close()
        except:
            pass
        final_list = list(brand_products.values())
        if len(final_list) > 20:
            final_list = final_list[:20]
        return final_list

async def main():
    start_time = time.time()
    print("Starting Flipkart Minutes Fast Scraper...")
    
    async with async_playwright() as p:
        # Use Chromium browser
        browser = await p.chromium.launch(headless=True)
        
        # Mobile User-Agent matching your cookies context
        user_agent = "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36"
        
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1280, 'height': 800}
        )
        
        # Add session cookies to the context
        await context.add_cookies(COOKIES)
        
        # Crawl all brands concurrently
        tasks = [crawl_brand(context, brand, i) for i, brand in enumerate(BRANDS)]
        results = await asyncio.gather(*tasks)
        
        await browser.close()
        
    # Combine results
    all_products = []
    for brand_products in results:
        all_products.extend(brand_products)
        
    if not all_products:
        print("No products crawled. Excel output was not written.")
        return
        
    # Populate run timestamp
    run_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for p in all_products:
        p["created_on"] = run_timestamp
        
    # Convert to DataFrame
    df = pd.DataFrame(all_products)
    
    # Deduplicate by URL to ensure uniqueness
    df.drop_duplicates(subset=["page_url"], inplace=True)
    
    # Define exact output column structure matching Book1.xlsx template
    columns_order = [
        'rb_sku_platform_id',
        'pf_id',
        'platform_name',
        'reseller_id',
        'sku_id',
        'web_pid',
        'group_id',
        'brand_id',
        'brand_category_id',
        'msl',
        'cluster',
        'ean_code',
        'rb_code',
        'pantry_code',
        'created_by',
        'created_on',
        'modified_by',
        'modified_on',
        'status',
        'page_url',
        'sku_name',
        'is_competitor',
        'sku_title',
        'comp_mapp',
        'brand_name',
        'brand_category',
        'item_code',
        'sub_brand',
        'mrp',
        'gram',
        'price_range',
        'qty',
        'image_url',
        'guardrail',
        'best_seller_category',
        'best_seller_category_id',
        'platform_uuid',
        'platform_account_id',
        'company_id'
    ]
    
    # Verify/fill missing columns with None (blank cells in Excel)
    for col in columns_order:
        if col not in df.columns:
            df[col] = None
            
    # Apply column ordering
    df = df[columns_order]
    
    # Write to Excel
    df.to_excel(OUTPUT_FILE, index=False)
    
    elapsed = time.time() - start_time
    print(f"\nSuccessfully wrote {len(df)} unique products to {OUTPUT_FILE}")
    print(f"Total time elapsed: {elapsed:.2f} seconds.")

if __name__ == "__main__":
    asyncio.run(main())
