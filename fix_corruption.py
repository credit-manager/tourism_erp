"""Check for corrupted Arabic strings in Python route files."""
import re, os

files = [
    'routers/collection_routes.py',
    'routers/supplier_payment_routes.py',
    'routers/treasury_routes.py',
    'routers/employee_routes.py',
]

for fname in files:
    with open(fname, 'rb') as f:
        raw = f.read()
    try:
        text = raw.decode('utf-8')
        # Look for high-byte chars that might be corrupted
        for i, ch in enumerate(text):
            if ord(ch) > 127:
                # Check if this is a valid Arabic char
                if not (0x0600 <= ord(ch) <= 0x06FF or 0x0750 <= ord(ch) <= 0x077F or 0xFE70 <= ord(ch) <= 0xFEFF):
                    if ord(ch) not in [0x2018, 0x2019, 0x201C, 0x201D, 0x200E, 0x200F]:
                        # Print surrounding context
                        start = max(0, i-10)
                        end = min(len(text), i+10)
                        context = text[start:end]
                        print(f'{fname}: Suspicious char U+{ord(ch):04X} at pos {i}: ...{repr(context)}...')
    except Exception as e:
        print(f'{fname}: Cannot decode as UTF-8: {e}')
