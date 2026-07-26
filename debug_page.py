"""Debug: check rendered HTML of /collections"""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Login first
login_resp = client.post("/login", data={"username": "admin", "password": "admin"}, follow_redirects=False)
cookies = login_resp.cookies

# Access collections with session
resp = client.get("/collections", cookies=cookies)
print(f"Status: {resp.status_code}")

html = resp.text

# Extract body
body_start = html.find('<body')
body_end = html.find('</body>')
if body_start >= 0 and body_end >= 0:
    body = html[body_start:body_end]
    # Find table section
    import re
    tables = re.findall(r'<table[^>]*>.*?</table>', body, re.DOTALL)
    print(f"Found {len(tables)} tables")
    for i, t in enumerate(tables):
        if '/collections/' in t or 'soft-badge' in t or '\u0645\u0633\u0648\u062f\u0629' in t:
            print(f"--- Table {i} ---")
            print(t[:800])
    # Check for workflow badges outside tables
    for kw in ['soft-badge', '\u0645\u0633\u0648\u062f\u0629', '\u0645\u0631\u062D\u0651\u0644', '\u0645\u0644\u063A\u064A']:
        if kw in body:
            print(f"Found '{kw}' in body")
        else:
            print(f"NOT found '{kw}' in body")
else:
    print(html[:2000])
