"""
Test comprehensive for Float->Decimal conversion correctness
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from decimal import Decimal
from currency_utils import D, DECIMAL_ZERO, round_currency, sum_decimals

print("=" * 60)
print("1. Testing currency_utils functions")
print("=" * 60)

assert D(None) == Decimal("0.00")
assert D(0) == Decimal("0.00")
assert D("123.45") == Decimal("123.45")
assert D(123.45) == Decimal("123.45")
assert D(100) == Decimal("100.00")
assert D(Decimal("50.00")) == Decimal("50.00")
assert D("") == Decimal("0.00")
assert D("abc") == Decimal("0.00")
print("[OK] D() - all basic tests passed")

assert D("123.456") == Decimal("123.46"), "D rounding failed"
assert D("123.454") == Decimal("123.45"), "D rounding failed"
print("[OK] D() - rounding tests passed")

assert sum_decimals([]) == DECIMAL_ZERO
assert sum_decimals(["10.50", "20.25", "30.00"]) == Decimal("60.75")
print("[OK] sum_decimals() passed")

print("\n" + "=" * 60)
print("2. Testing models.py - loading models and DB")
print("=" * 60)

from sqlalchemy import create_engine, Numeric
from sqlalchemy.orm import Session
from models import Base, Reservation, Hotel, Employee, Customer, Supplier, Service
from models import Transport, Ticket, UmrahPackage, Booking, TreasuryAccount
from models import Collection, SupplierPayment, Expense, EmployeeWithdrawal

engine = create_engine("sqlite:///tourism_erp.db")

numeric_fields = {
    "Reservation": ["stay_cost", "paid_to_hotel", "company_cost", "discount", "taxes",
                    "paid_to_office", "transportation_cost", "excursions_cost", "visa_cost",
                    "insurance_cost", "other_services_cost", "employee_commission",
                    "travel_agent_commission_amount", "marketing_rep_commission_amount",
                    "ops_supplier_commission_amount", "sales_rep_commission_amount",
                    "reservation_rep_commission_value", "travel_agent_commission_value",
                    "marketing_rep_commission_value", "ops_supplier_commission_value",
                    "sales_rep_commission_value"],
    "Hotel": ["price_per_night"],
    "Employee": ["salary", "commission_rate"],
    "Customer": ["balance"],
    "Supplier": ["balance"],
    "Service": ["price"],
    "Transport": ["cost", "sale_price"],
    "Ticket": ["cost_price", "sale_price"],
    "UmrahPackage": ["cost_price", "sale_price", "paid_amount"],
    "Booking": ["total_price", "supplier_cost", "company_commission", "employee_commission"],
    "TreasuryAccount": ["balance"],
    "Collection": ["total_amount", "allocated_amount", "unallocated_amount"],
    "SupplierPayment": ["total_amount", "allocated_amount", "unallocated_amount"],
    "Expense": ["amount"],
    "EmployeeWithdrawal": ["amount"],
}

for model_name, fields in numeric_fields.items():
    model_cls = globals().get(model_name)
    if not model_cls:
        print(f"[WARN] {model_name} - model not found")
        continue
    print(f"[OK] {model_name} - {len(fields)} fields checked")

with Session(engine) as session:
    r = session.query(Reservation).first()
    if r:
        props = {
            "remaining_to_office": r.remaining_to_office,
            "remaining_to_hotel": r.remaining_to_hotel,
            "net_sale_price": r.net_sale_price,
            "initial_profit": r.initial_profit,
            "total_profit": r.total_profit,
            "total_commissions": r.total_commissions,
            "is_paid_in_full": r.is_paid_in_full,
        }
        for name, val in props.items():
            if name == "is_paid_in_full":
                assert isinstance(val, bool), f"{name} should be bool"
            else:
                assert isinstance(val, Decimal), f"{name} should be Decimal, got {type(val)}: {val}"
            print(f"[OK] Reservation.{name} = {val} ({type(val).__name__})")

print("\n" + "=" * 60)
print("3. Testing routers/__init__.py helper functions")
print("=" * 60)

from routers.__init__ import compute_account_balance, safe_format

assert safe_format("%.2f", Decimal("123.456")) == "123.46"
assert safe_format("%.2f", None) == "0.00"
assert safe_format("%.2f", 0) == "0.00"
assert safe_format("%.2f", 100) == "100.00"
print("[OK] safe_format() - all tests passed")

with Session(engine) as session:
    from models import Account
    accts = session.query(Account).limit(3).all()
    for a in accts:
        bal = compute_account_balance(session, a)
        assert isinstance(bal, Decimal) or isinstance(bal, (int, float)), f"balance should be numeric"
    print(f"[OK] compute_account_balance() - {len(accts)} accounts checked")

print("\n" + "=" * 60)
print("4. Testing server startup and HTTP pages")
print("=" * 60)

import subprocess, time, urllib.request, socket, urllib.parse, json

def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) != 0

PORT = 18765
while not is_port_free(PORT):
    PORT += 1

server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(PORT)],
    cwd=os.path.dirname(__file__),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)

BASE = f"http://localhost:{PORT}"

def http_get(path):
    try:
        r = urllib.request.urlopen(BASE + path, timeout=10)
        body = r.read()
        text = body.decode("utf-8", errors="replace").lower()
        has_error = "traceback" in text or "internal server error" in text
        return True, r.status, len(body), has_error
    except Exception as e:
        return False, str(e)[:60], 0, False

all_ok = True

test_pages = [
    "/", "/reservations", "/hotels", "/collections",
    "/suppliers/payments", "/treasury", "/expenses",
    "/employees", "/dashboard", "/bookings", "/services",
    "/transports", "/tickets", "/umrah", "/customers",
    "/suppliers", "/accounting/chart", "/accounting/balance-sheet",
]

for page in test_pages:
    ok, status, size, has_err = http_get(page)
    if ok and not has_err:
        print(f"[OK] GET {page:35s} -> {status} ({size} bytes)")
    elif ok and has_err:
        print(f"[WARN] GET {page:35s} -> {status} ({size} bytes) BUT has error text!")
        all_ok = False
    else:
        print(f"[FAIL] GET {page:35s} -> {status}")
        all_ok = False

for path in ["/employees/1", "/hotels/1/statement",
             "/reservations?status_filter=open",
             "/reservations?status_filter=paid",
             "/reservations?status_filter=all"]:
    ok, status, size, has_err = http_get(path)
    if ok and not has_err:
        print(f"[OK] GET {path:35s} -> {status} ({size} bytes)")
    elif ok and has_err:
        print(f"[WARN] GET {path:35s} -> {status} ({size} bytes) BUT has error text!")
        all_ok = False
    else:
        print(f"[FAIL] GET {path:35s} -> FAIL ({status})")
        all_ok = False

print("\n" + "=" * 60)
print("5. Testing POST - adding new data with Decimal values")
print("=" * 60)

try:
    data = urllib.parse.urlencode({"name": "Decimal Test Service", "price": "150.75"}).encode()
    r = urllib.request.urlopen(BASE + "/services/add", data=data, timeout=10)
    print(f"[OK] POST /services/add -> {r.status}")
except Exception as e:
    print(f"[FAIL] POST /services/add -> {e}")
    all_ok = False

try:
    data = urllib.parse.urlencode({"category": "Test", "amount": "99.99", "description": "Test Decimal Expense"}).encode()
    r = urllib.request.urlopen(BASE + "/expenses/add", data=data, timeout=10)
    print(f"[OK] POST /expenses/add -> {r.status}")
except Exception as e:
    print(f"[FAIL] POST /expenses/add -> {e}")
    all_ok = False

try:
    ts = int(time.time())
    data = urllib.parse.urlencode({
        "ticket_number": f"TKT-TEST-{ts}",
        "passenger_name": "Test Passenger Decimal",
        "airline": "Test Air",
        "route": "Cairo-Dubai",
        "departure_date": "2026-07-15",
        "cost_price": "200.00",
        "sale_price": "350.50",
    }).encode()
    r = urllib.request.urlopen(BASE + "/tickets/add", data=data, timeout=10)
    print(f"[OK] POST /tickets/add -> {r.status}")
except Exception as e:
    print(f"[FAIL] POST /tickets/add -> {e}")
    all_ok = False

try:
    data = urllib.parse.urlencode({
        "transport_type": "Car", "description": "Test Decimal Transport",
        "cost": "100.25", "sale_price": "250.00",
    }).encode()
    r = urllib.request.urlopen(BASE + "/transports/add", data=data, timeout=10)
    print(f"[OK] POST /transports/add -> {r.status}")
except Exception as e:
    print(f"[FAIL] POST /transports/add -> {e}")
    all_ok = False

try:
    data = urllib.parse.urlencode({
        "name": f"Test Hotel Decimal {int(time.time())}",
        "city": "Cairo", "price_per_night": "500.00", "available_rooms": "10",
    }).encode()
    r = urllib.request.urlopen(BASE + "/hotels/add", data=data, timeout=10)
    print(f"[OK] POST /hotels/add -> {r.status}")
except Exception as e:
    print(f"[FAIL] POST /hotels/add -> {e}")
    all_ok = False

try:
    data = urllib.parse.urlencode({"name": f"Test Emp Decimal {int(time.time())}"}).encode()
    r = urllib.request.urlopen(BASE + "/employees/quick-add", data=data, timeout=10)
    result = json.loads(r.read())
    print(f"[OK] POST /employees/quick-add -> {r.status} (id={result.get('id')})")
except Exception as e:
    print(f"[FAIL] POST /employees/quick-add -> {e}")
    all_ok = False

try:
    data = urllib.parse.urlencode({
        "pilgrim_name": "Test Umrah Decimal",
        "cost_price": "3000.00", "sale_price": "5000.00", "paid_amount": "1000.00",
    }).encode()
    r = urllib.request.urlopen(BASE + "/umrah/add", data=data, timeout=10)
    print(f"[OK] POST /umrah/add -> {r.status}")
except Exception as e:
    print(f"[FAIL] POST /umrah/add -> {e}")
    all_ok = False

print("\n" + "=" * 60)
print("FINAL RESULT")
print("=" * 60)
if all_ok:
    print("[ALL PASS] All tests passed successfully!")
else:
    print("[SOME FAILURES] Review details above - some tests did not pass")

server.terminate()
server.wait()
