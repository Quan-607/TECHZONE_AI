import json
from pathlib import Path
from google.api_core.exceptions import AlreadyExists
from backend.firebase_config import db

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / 'data' / 'products.json'

with DATA_FILE.open('r', encoding='utf-8') as f:
    products = json.load(f)

if not isinstance(products, list):
    raise ValueError('products.json phai la mot danh sach san pham')

inserted = 0
skipped = 0
for item in products:
    product_id = item.get('id')
    if not product_id or not item.get('name') or not item.get('category'):
        raise ValueError(f'San pham thieu id/name/category: {item}')
    doc = {k: v for k, v in item.items() if k != 'id'}
    try:
        db.collection('products').document(product_id).create(doc)
        inserted += 1
        print(f'+ {product_id}: {item["name"]}')
    except AlreadyExists:
        skipped += 1
        print(f'= Bo qua {product_id} (da ton tai)')

print(f'Hoan tat: them {inserted}, bo qua {skipped}.')
