import urllib.request, urllib.parse, re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

url = "https://senstroy.ru/catalog/?q=" + urllib.parse.quote("труба")
req = urllib.request.Request(url, headers=HEADERS)
r = urllib.request.urlopen(req, timeout=30)
html = r.read().decode("utf-8", errors="replace")

idx = html.find('item_block')
if idx >= 0:
    start = max(0, idx - 200)
    block = html[start:start+5000]
    print(block)
else:
    print("No item_block found")
