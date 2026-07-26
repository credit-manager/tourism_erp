"""Run full Decimal conversion tests with server"""
import sys, os, time, socket, subprocess, urllib.request, urllib.parse, http.cookiejar

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

print("=" * 60)
print("STEP 1: Unit Tests (no server needed)")
print("=" * 60)

from decimal import Decimal
from currency_utils import D, DECIMAL_ZERO, sum_decimals

assert D(None) == Decimal("0.00"), "D(None)"
assert D(0) == Decimal("0.00"), "D(0)"
assert D("123.45") == Decimal("123.45")
assert D(123.45) == Decimal("123.45")
assert D("123.456") == Decimal("123.46"), "round up"
assert D("123.454") == Decimal("123.45"), "round down"
assert D("abc") == Decimal("0.00")
assert sum_decimals(["10.50", "20.25"]) == Decimal("30.75")
print("  [OK] currency_utils D() and sum_decimals()")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from models import Reservation

engine = create_engine("sqlite:///tourism_erp.db")
with Session(engine) as session:
    r = session.query(Reservation).first()
    if r:
        assert isinstance(r.stay_cost, Decimal)
        assert isinstance(r.company_cost, Decimal)
        assert isinstance(r.paid_to_office, Decimal)
        assert isinstance(r.remaining_to_office, Decimal)
        assert isinstance(r.remaining_to_hotel, Decimal)
        assert isinstance(r.net_sale_price, Decimal)
        assert isinstance(r.initial_profit, Decimal)
        assert isinstance(r.total_profit, Decimal)
        assert isinstance(r.total_commissions, Decimal)
        assert isinstance(r.is_paid_in_full, bool)
        print(f"  [OK] Reservation properties return Decimal")
        print(f"       stay_cost={r.stay_cost}, company_cost={r.company_cost}")
        print(f"       remaining_to_office={r.remaining_to_office}")
        print(f"       total_profit={r.total_profit}")

from routers.__init__ import safe_format, compute_account_balance
assert safe_format("%.2f", Decimal("123.456")) == "123.46"
assert safe_format("%.2f", None) == "0.00"
assert safe_format("%.2f", 0) == "0.00"
print("  [OK] safe_format() works with Decimal")

from models import Account
with Session(engine) as session:
    accts = session.query(Account).limit(3).all()
    for a in accts:
        bal = compute_account_balance(session, a)
        assert bal is not None
    print(f"  [OK] compute_account_balance() - {len(accts)} accounts OK")

print()
print("=" * 60)
print("STEP 2: HTTP Integration Tests (starting server)")
print("=" * 60)

# Find free port
def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) != 0

PORT = 18765
while not is_port_free(PORT):
    PORT += 1

server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(PORT)],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)

BASE = f"http://localhost:{PORT}"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Login
try:
    data = urllib.parse.urlencode({"username": "admin", "password": "admin123"}).encode()
    r = opener.open(BASE + "/login", data=data, timeout=10)
    print(f"  [OK] Login as admin -> {r.status} ({r.url})")
except Exception as e:
    print(f"  [FAIL] Login -> {e}")
    server.terminate()
    server.wait()
    sys.exit(1)

all_ok = True

# GET all pages
pages = [
    "/reservations", "/hotels", "/collections",
    "/suppliers/payments", "/treasury", "/expenses",
    "/employees", "/", "/bookings", "/services",
    "/transportations", "/tickets", "/umrah", "/customers",
    "/suppliers", "/accounting/chart", "/accounting/balance-sheet",
]
for p in pages:
    try:
        r = opener.open(BASE + p, timeout=10)
        body = r.read()
        text = body.decode("utf-8", errors="replace")
        has_err = "traceback" in text.lower() or "internal server error" in text.lower()
        if has_err:
            print(f"  [WARN] GET {p:35s} -> {r.status} ({len(body)} bytes) - has error!")
            for line in text.split("\n"):
                if "error" in line.lower():
                    print(f"         {line.strip()[:150]}")
                    break
            all_ok = False
        else:
            print(f"  [OK]  GET {p:35s} -> {r.status} ({len(body)} bytes)")
    except Exception as e:
        print(f"  [FAIL] GET {p:35s} -> {str(e)[:80]}")
        all_ok = False

# Filtered/ID pages
for p in ["/employees/1", "/hotels/1/statement",
          "/reservations?status_filter=open",
          "/reservations?status_filter=paid",
          "/transportations", "/"]:
    try:
        r = opener.open(BASE + p, timeout=10)
        body = r.read()
        text = body.decode("utf-8", errors="replace").lower()
        has_err = "traceback" in text or "500" in text[:200]
        if has_err:
            print(f"  [WARN] GET {p:35s} -> {r.status} ({len(body)} bytes) - has error!")
            all_ok = False
        else:
            print(f"  [OK]  GET {p:35s} -> {r.status} ({len(body)} bytes)")
    except Exception as e:
        print(f"  [FAIL] GET {p:35s} -> {str(e)[:80]}")
        all_ok = False

print()

# POST tests - add data with decimal values
print("--- POST Operations ---")

# 1. Add service
try:
    data = urllib.parse.urlencode({"name": "Decimal Test Svc", "price": "150.75"}).encode()
    r = opener.open(BASE + "/services/add", data=data, timeout=10)
    print(f"  [OK]  POST /services/add -> {r.status}")
except Exception as e:
    print(f"  [FAIL] POST /services/add -> {str(e)[:80]}")
    all_ok = False

# 2. Add expense
try:
    data = urllib.parse.urlencode({"category": "Test", "amount": "99.99", "description": "Decimal Test"}).encode()
    r = opener.open(BASE + "/expenses/add", data=data, timeout=10)
    print(f"  [OK]  POST /expenses/add -> {r.status}")
except Exception as e:
    print(f"  [FAIL] POST /expenses/add -> {str(e)[:80]}")
    all_ok = False

# 3. Add ticket
try:
    ts = int(time.time())
    data = urllib.parse.urlencode({
        "ticket_number": f"TKT-DEC-{ts}",
        "passenger_name": "Decimal Test",
        "airline": "Test", "route": "Test",
        "departure_date": "2026-07-15",
        "cost_price": "200.00", "sale_price": "350.50",
    }).encode()
    r = opener.open(BASE + "/tickets/add", data=data, timeout=10)
    print(f"  [OK]  POST /tickets/add -> {r.status}")
except Exception as e:
    print(f"  [FAIL] POST /tickets/add -> {str(e)[:80]}")
    all_ok = False

# 4. Add transport
try:
    data = urllib.parse.urlencode({
        "transport_type": "Car", "description": "Decimal Test",
        "cost": "100.25", "sale_price": "250.00",
    }).encode()
    r = opener.open(BASE + "/transportations/add", data=data, timeout=10)
    print(f"  [OK]  POST /transportations/add -> {r.status}")
except Exception as e:
    print(f"  [FAIL] POST /transportations/add -> {str(e)[:80]}")
    all_ok = False

# 5. Add hotel
try:
    data = urllib.parse.urlencode({
        "name": f"Decimal Hotel {int(time.time())}",
        "city": "Cairo", "price_per_night": "500.75", "available_rooms": "10",
    }).encode()
    r = opener.open(BASE + "/hotels/add", data=data, timeout=10)
    print(f"  [OK]  POST /hotels/add -> {r.status}")
except Exception as e:
    print(f"  [FAIL] POST /hotels/add -> {str(e)[:80]}")
    all_ok = False

# 6. Add umrah
try:
    data = urllib.parse.urlencode({
        "pilgrim_name": "Decimal Umrah Test",
        "cost_price": "3000.00", "sale_price": "5000.00", "paid_amount": "1000.00",
    }).encode()
    r = opener.open(BASE + "/umrah/add", data=data, timeout=10)
    print(f"  [OK]  POST /umrah/add -> {r.status}")
except Exception as e:
    print(f"  [FAIL] POST /umrah/add -> {str(e)[:80]}")
    all_ok = False

print()
print("=" * 60)
print("FINAL RESULT")
print("=" * 60)
if all_ok:
    print("[ALL TESTS PASSED] Decimal conversion is working correctly!")
else:
    print("[SOME ISSUES] Review warnings above")

server.terminate()
server.wait()
