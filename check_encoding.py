import re
with open('routers/collection_routes.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find page_title
for m in re.finditer(r'page_title.*?[\x22]', content):
    print(repr(m.group()))

# Also check the route where page_title is set (line ~23)
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'page_title' in line:
        print(f'Line {i+1}: {repr(line.strip()[:120])}')
