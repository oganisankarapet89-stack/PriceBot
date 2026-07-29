import urllib.request, re, time

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
urls = {}

# Get all subcategories from main categories
cats = [
    'drenazh', 'geotekstil', 'kolodets', 'kanalizatsiya',
    'dozhdepriemniki_lotki', 'pnd_truby_i_fitingi',
    'polipropilen', 'instrumenty', 'radiatory_i_konvektory',
    'kollektory', 'armatura_dlya_sistemy_otopleniya',
    'fitingi_dlya_otopleniya',
]

all_subs = []
for cat in cats:
    url = f'https://senstroy.ru/catalog/{cat}/'
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        r = urllib.request.urlopen(req, timeout=15)
        html = r.read().decode('utf-8', errors='replace')
        subs = re.findall(r'href="(/catalog/{cat}/[a-zA-Z0-9_-]+/)"'.format(cat=cat), html)
        subs = list(dict.fromkeys(subs))
        for s in subs:
            all_subs.append(s)
        print(f'{cat}: {len(subs)} subs')
    except:
        pass

print(f'\nTotal subs: {len(all_subs)}')

for i, sub in enumerate(all_subs):
    if len(urls) >= 300:
        break
    sub_url = 'https://senstroy.ru' + sub
    try:
        time.sleep(1)
        req = urllib.request.Request(sub_url, headers=HEADERS)
        r = urllib.request.urlopen(req, timeout=15)
        html = r.read().decode('utf-8', errors='replace')
        pids = re.findall(r'item_block[^>]*data-id="(\d+)"', html)
        for pid in pids:
            if pid in urls:
                continue
            # try both patterns: with and without .html
            pat = r'data-id="{pid}".*?<a href="(/catalog/[^"]+)"[^>]*class="dark_link'.format(pid=pid)
            m = re.search(pat, html, re.DOTALL)
            if m:
                href = m.group(1).split('?')[0]
                urls[pid] = 'https://senstroy.ru' + href
        print(f'  [{i+1}/{len(all_subs)}] {sub} => {len(pids)} ids, total={len(urls)}', flush=True)
    except:
        print(f'  [{i+1}/{len(all_subs)}] {sub} ERROR', flush=True)
        continue

# Write
with open('product_map.py', 'w', encoding='utf-8') as f:
    f.write('PRODUCT_URLS = {\n')
    for pid in sorted(urls.keys(), key=int):
        f.write(f'    {pid}: {repr(urls[pid])},\n')
    f.write('}\n')
print(f'\nDone! Total: {len(urls)}', flush=True)
