import urllib.request, re
url = 'https://senstroy.ru/catalog/?q=28011'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
r = urllib.request.urlopen(req, timeout=30)
html = r.read().decode('utf-8', errors='replace')
blocks = re.split(r'item_block\s+"', html)
print('Blocks:', len(blocks))
if len(blocks) > 1:
    print(blocks[1][:2000])
else:
    print('No blocks')
    print(html[:2000])
