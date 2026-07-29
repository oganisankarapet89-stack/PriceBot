import urllib.request, urllib.parse, re, time, sys

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

visited = set()
products = []

terms = [
    "труба", "фитинг", "муфта", "кран", "хомут",
    "отвод", "тройник", "заглушка", "штуцер",
    "ниппель", "фланец", "вентиль", "манжета",
    "седло", "коллектор", "адаптер", "редукция",
    "уголок", "крестовина", "переход",
    "шаровый", "терморегулятор", "фильтр", "редуктор",
    "манометр", "гильза", "кронштейн", "прокладка",
    "уплотнитель", "лента",
]

full_urls = set()

for term in terms:
    if len(products) >= 100:
        break
    url = "https://senstroy.ru/catalog/?q=" + urllib.parse.quote(term)
    try:
        time.sleep(1.5)
        req = urllib.request.Request(url, headers=HEADERS)
        r = urllib.request.urlopen(req, timeout=30)
        html = r.read().decode("utf-8", errors="replace")

        blocks = re.split(r'<div[^>]*class="[^"]*item_block[^"]*"', html)
        for block in blocks[1:]:
            if len(products) >= 100:
                break
            pid_m = re.search(r'data-id="(\d+)"', block[:200])
            pid = pid_m.group(1) if pid_m else "?"
            if pid in visited:
                continue
            visited.add(pid)
            products.append(pid)
            print(pid, flush=True)
    except Exception as e:
        print(f"#{term}", file=sys.stderr, flush=True)
        continue

print(f"\nTOTAL={len(products)}", file=sys.stderr, flush=True)
