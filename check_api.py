import urllib.request, re, json

# Check if Senstroy has a JSON API
urls = [
    'https://senstroy.ru/catalog/?q=&ajax=Y',
    'https://senstroy.ru/catalog/?ajax=Y',
    'https://senstroy.ru/api/catalog/',
    'https://senstroy.ru/bitrix/components/bitrix/catalog.section/ajax.php',
    'https://senstroy.ru/catalog/kolodets/truba_dvukhsloynaya_gofrirovannaya/28011/?ajax=Y',
]
for u in urls:
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'X-Requested-With': 'XMLHttpRequest'})
        r = urllib.request.urlopen(req, timeout=15)
        data = r.read().decode('utf-8', errors='replace')
        content_type = r.headers.get('Content-Type', '')
        print(f'{r.status} {u[:70]} | type={content_type[:30]} len={len(data)}')
        if 'json' in content_type:
            print(f'  JSON: {data[:200]}')
    except Exception as e:
        print(f'ERROR: {u[:70]} => {str(e)[:60]}')
