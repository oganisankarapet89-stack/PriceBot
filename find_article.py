import urllib.request, re
url = 'https://senstroy.ru/catalog/kolodets/truba_dvukhsloynaya_gofrirovannaya/28011/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
r = urllib.request.urlopen(req, timeout=30)
html = r.read().decode('utf-8', errors='replace')

# Try to find article/artikul on the product page
# Bitrix often stores article in data or meta
patterns = [
    r'артикул[:\s]*([^\s<,]+)',
    r'article[:\s]*([^\s<,]+)',
    r'sku[:\s]*([^\s<,]+)',
    r'data-artikul="([^"]+)"',
    r'data-article="([^"]+)"',
    r'itemprop="sku"\s+content="([^"]+)"',
    r'class="[^"]*article[^"]*"[^>]*>([^<]+)',
    r'<span[^>]*>Артикул[^<]*<[^>]*>([^<]+)',
    r'Артикул[^:]*:[^<]*<[^>]*>([^<]+)',
]

for pat in patterns:
    m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
    if m:
        print(f'FOUND: {pat} => {m.group(1).strip()}')
    else:
        print(f'NOT FOUND: {pat}')
