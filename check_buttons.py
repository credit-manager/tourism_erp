from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
resp = client.get('/collections')
html = resp.text
keywords = ['submit', 'badge-blue', 'wf_map', '\u0645\u0633\u0648\u062f\u0629', '\u062A\u0642\u062F\u064A\u0645']
for k in keywords:
    found = k in html
    print(f'{k}: {"found" if found else "NOT FOUND"}')
# Check a record row for buttons
if '/collections/' in html:
    import re
    for m in re.finditer(r'/collections/\d+/submit', html):
        print(f'Found button: {m.group()}')
print('Done')
