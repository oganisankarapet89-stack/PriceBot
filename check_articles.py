import urllib.request, re, html as html_mod
url = 'https://senstroy.ru/catalog/?q=%D1%82%D1%80%D1%83%D0%B1%D0%B0'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
r = urllib.request.urlopen(req, timeout=30)
html = r.read().decode('utf-8', errors='replace')
blocks = re.split(r'item_block\s+"', html)
for i, block in enumerate(blocks[1:6], 1):
    pid = re.search(r'data-id="(\d+)"', block[:200])
    art = re.search(r'article_block[^>]*data-value="([^"]+)"', block)
    name = re.search(r'dark_link[^>]*><span>([^<]+)</span>', block)
    print(f'{i}. ID={pid.group(1) if pid else "?"}, Article={html_mod.unescape(art.group(1)).strip() if art else "?"}, Name={html_mod.unescape(name.group(1)).strip() if name else "?"}')
