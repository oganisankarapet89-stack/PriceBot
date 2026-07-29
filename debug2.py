import urllib.request, urllib.parse, re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

url = "https://senstroy.ru/catalog/?q=" + urllib.parse.quote("труба")
req = urllib.request.Request(url, headers=HEADERS)
r = urllib.request.urlopen(req, timeout=30)
html = r.read().decode("utf-8", errors="replace")

# find all item_block sections
blocks = re.split(r'<div[^>]*class="[^"]*item_block[^"]*"', html)
print(f"Found {len(blocks)-1} item blocks", flush=True)

products = []
for i, block in enumerate(blocks[1:], 1):
    # get data-id
    pid_m = re.search(r'data-id="(\d+)"', block[:200])
    pid = pid_m.group(1) if pid_m else "?"
    
    # find the product link href (not category links)
    # look for href in name/title links
    href_m = re.search(r'<a href="(/catalog/[^"]+)"[^>]*class="[^"]*name[^"]*"', block)
    if href_m:
        href = href_m.group(1)
    else:
        # try dark_link or js-notice-block__title
        href_m = re.search(r'<a href="(/catalog/[^"]+)"[^>]*class="dark_link[^"]*js-notice-block__title[^"]*"', block)
        if href_m:
            href = href_m.group(1)
        else:
            href_m = re.search(r'<a href="(/catalog/[^"]+)"[^>]*>([^<]+)</a>', block)
            href = href_m.group(1) if href_m else None
    
    if href:
        full = "https://senstroy.ru" + re.sub(r'\?.*', '', href.split('?')[0] if '?' in href else href)
        if full not in [p[1] for p in products]:
            products.append((pid, full))
            print(f"{len(products)}. ID={pid} {full}", flush=True)
    
    if len(products) >= 100:
        break

print(f"\nTOTAL: {len(products)}", flush=True)
