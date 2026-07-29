import urllib.request, re

urls = [
    'https://senstroy.ru/catalog/28011/',
    'https://senstroy.ru/28011/',
    'https://senstroy.ru/catalog/detail.php?ELEMENT_ID=28011',
    'https://senstroy.ru/catalog/index.php?ELEMENT_ID=28011',
]
for u in urls:
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
        r = urllib.request.urlopen(req, timeout=15)
        html = r.read().decode('utf-8', errors='replace')
        tl = re.search(r'<title>([^<]+)', html)
        pm = re.search(r'itemprop="price"\s+content="([\d.]+)"', html)
        status = r.status
        final_url = r.url[:80]
        title = tl.group(1)[:40] if tl else '?'
        price = pm.group(1) if pm else '?'
        print(f'{status} {final_url} | title={title} | price={price}')
    except Exception as e:
        print(f'ERROR: {u} => {str(e)[:60]}')
