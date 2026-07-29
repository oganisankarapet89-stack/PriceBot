import urllib.request, re, html as html_mod

url = 'https://senstroy.ru/catalog/kolodets/truba_dvukhsloynaya_gofrirovannaya/28011/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
r = urllib.request.urlopen(req, timeout=30)
html = r.read().decode('utf-8', errors='replace')

# Find the article number displayed on the page
# Look for "Артикул" in the HTML
idx = html.find('Артикул')
if idx >= 0:
    snippet = html[idx:idx+500]
    print('Артикул section:', repr(snippet[:300]))
else:
    # Try English "Article" or "SKU"
    idx2 = html.find('itemprop="sku"')
    if idx2 >= 0:
        snippet = html[max(0,idx2-100):idx2+200]
        print('SKU section:', repr(snippet))
    else:
        # Look for article_block
        idx3 = html.find('article_block')
        if idx3 >= 0:
            snippet = html[idx3:idx3+300]
            print('article_block:', repr(snippet))
        
# Also extract OG title for the product name
og = re.search(r'og:title"\s+content="([^"]+)"', html)
if og:
    print(f'Product name: {og.group(1)[:80]}')
