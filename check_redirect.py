import urllib.request, re
# Try to find product by numeric ID on Senstroy
# Try searching with just the number (will it redirect?)
url = 'https://senstroy.ru/catalog/?q=28011'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
r = urllib.request.urlopen(req, timeout=30)
print(f'Status: {r.status}, URL: {r.url}')
html = r.read().decode('utf-8', errors='replace')
# Check if there's any product grid
if 'item_block' in html:
    print('Has item_block (search worked)')
else:
    print('No search results')
# Check if redirected to product page
if r.url != url:
    print(f'Redirected to: {r.url}')
