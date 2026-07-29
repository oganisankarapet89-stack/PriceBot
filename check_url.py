import urllib.request, re
url = 'https://senstroy.ru/catalog/kolodets/truba_dvukhsloynaya_gofrirovannaya/28011/'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
r = urllib.request.urlopen(req, timeout=30)
html = r.read().decode('utf-8', errors='replace')
pm = re.search(r'itemprop="price"\s+content="([\d.]+)"', html)
if pm: print('Price meta:', pm.group(1))
dvm = re.search(r'data-value="([\d.]+)"', html)
if dvm: print('Data-value:', dvm.group(1))
og = re.search(r'og:title"\s+content="([^"]+)"', html)
if og: print('OG title:', og.group(1))
tl = re.search(r'<title>([^<]+)</title>', html)
if tl: print('Title:', tl.group(1)[:80])
