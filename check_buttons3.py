from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
resp = client.get('/collections')
print('Status:', resp.status_code)
html = resp.text
# Show a relevant snippet
import re
# Find the table section
idx = html.find('<table')
if idx >= 0:
    print('TABLE found at', idx)
    print(html[idx:idx+1000])
else:
    # Show what's in the body
    body_start = html.find('<body')
    body_end = html.find('</body>')
    if body_start >= 0 and body_end >= 0:
        body = html[body_start:body_end]
        print('BODY length:', len(body))
        print(body[:2000])
    else:
        print('NO BODY')
        print(html[:2000])
