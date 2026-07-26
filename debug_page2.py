"""Debug: check login and collections"""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Try login
resp = client.post("/login", data={"username": "admin", "password": "admin"}, follow_redirects=False)
print(f"Login status: {resp.status_code}")
print(f"Location: {resp.headers.get('location', 'none')}")
print(f"Cookies: {resp.cookies}")

# Get collections after login
resp2 = client.get("/collections", cookies=resp.cookies)
print(f"Collections status: {resp2.status_code}")
print(f"URL: {resp2.url}")
print(f"Content first 500: {resp2.text[:500]}")
