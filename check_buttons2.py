from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
resp = client.get('/collections')
html = resp.text
# Look for workflow-related content in rendered HTML
checks = [
    '\u0645\u0633\u0648\u062f\u0629',  # مسودة
    '\u0642\u064A\u062F \u0627\u0644\u0645\u0631\u0627\u062C\u0639\u0629',  # قيد المراجعة
    '\u0645\u0631\u062D\u0651\u0644',  # مرحّل
    '\u0645\u0644\u063A\u064A',  # ملغي
    '/collections/',
    'badge-gray',
    'badge-green',
    'badge-red',
]
for c in checks:
    found = c in html
    print(f'  {c}: {"found" if found else "NOT FOUND"}'[:80])
# Find all form actions with /collections/\d+/ in the rendered HTML
import re
actions = re.findall(r'action="/collections/\d+/[a-z]+"', html)
print(f'Form actions found: {actions}')
# Find all soft-badge with workflow status
badges = re.findall(r'soft-badge badge-\w+">([^<]+)', html)
print(f'Badges found: {badges[:20]}')
print('Done')
