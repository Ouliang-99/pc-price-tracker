# -*- coding: utf-8 -*-
"""PoC: ทดสอบ qwen3-vl อ่านรูปโพสต์ขายคอม

Test 1 — OCR: ถอดข้อความในรูปทุกบรรทัด เทียบกับ ground truth (path ที่จะส่งต่อเข้า parse_post เดิม)
Test 2 — Structured: ดึงรายการชิ้นส่วนเป็น JSON ตาม schema เลย (path ทางลัด)

ใช้: python poc_vision\\test_vl.py [model]   (default: qwen3-vl:8b)
"""
import base64
import difflib
import json
import sys
import time
from pathlib import Path

import requests

HOST = "http://localhost:11434"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3-vl:8b"
IMAGE = Path(__file__).parent / "test_post.png"

# ground truth = บรรทัดเดียวกับที่ make_test_image.py วาดลงรูป
from make_test_image import LINES  # noqa: E402

CATEGORIES = ["GPU", "CPU", "RAM", "MB", "PSU", "SSD", "HDD",
              "CASE", "COOLER", "MONITOR", "NOTEBOOK", "OTHER"]

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "price": {"type": ["integer", "null"]},
                },
                "required": ["item_name", "category", "price"],
            },
        }
    },
    "required": ["items"],
}


def chat(messages, fmt=None, timeout=300):
    payload = {
        "model": MODEL,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 8192},
        "messages": messages,
    }
    if fmt:
        payload["format"] = fmt
    t0 = time.time()
    resp = requests.post(f"{HOST}/api/chat", json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"], time.time() - t0


img_b64 = base64.b64encode(IMAGE.read_bytes()).decode()

# ---- Test 1: OCR ล้วน ----
print(f"=== Test 1: OCR (model={MODEL}) ===")
ocr_text, dt = chat([
    {"role": "system",
     "content": "ถอดข้อความในรูปออกมาทุกบรรทัด ตรงตามต้นฉบับ ไม่ต้องแปล ไม่ต้องอธิบาย ไม่ต้องสรุป"},
    {"role": "user", "content": "ถอดข้อความในรูปนี้", "images": [img_b64]},
])
print(ocr_text)
print(f"--- ใช้เวลา {dt:.1f}s ---")

truth = "\n".join(line.strip() for line in LINES)
got = "\n".join(line.strip() for line in ocr_text.strip().splitlines() if line.strip())
ratio = difflib.SequenceMatcher(None, truth, got).ratio()
print(f"ความเหมือนกับ ground truth (char-level): {ratio:.1%}")
for d in difflib.unified_diff(truth.splitlines(), got.splitlines(),
                              "ต้นฉบับ", "OCR", lineterm="", n=0):
    print(d)

# ---- Test 2: structured extraction ตรงจากรูป ----
print(f"\n=== Test 2: Structured extraction (model={MODEL}) ===")
content, dt = chat([
    {"role": "system",
     "content": "คุณเป็นตัวช่วยแยกข้อมูลสินค้าคอมพิวเตอร์จากรูปโพสต์ขายภาษาไทย "
                "ดึงรายการชิ้นส่วนทั้งหมดในรูปเป็น JSON ตาม schema\n"
                'item_name = ชื่อรุ่นของชิ้นนั้นตามที่เขียนในรูป เช่น "i9 13900K", '
                '"RTX 5070 Aero White", "Kingston DDR4 32GB 3200" ห้ามตอบเป็นชื่อหมวด\n'
                "price = ราคาที่เขียนกำกับชิ้นนั้นโดยตรงเท่านั้น ถ้าไม่มีให้ null ห้ามเดา"},
    {"role": "user", "content": "แยกรายการชิ้นส่วนจากรูปนี้", "images": [img_b64]},
], fmt=ITEM_SCHEMA)
print(f"--- ใช้เวลา {dt:.1f}s ---")
try:
    items = json.loads(content)["items"]
    for it in items:
        print(f"  [{it['category']:>7}] {it['item_name']}  price={it['price']}")
    prices = [it["price"] for it in items if it["price"] is not None]
    print(f"  รวม {len(items)} ชิ้น, มีราคา {len(prices)} ชิ้น (ที่ถูกคือ 0 — โพสต์นี้ไม่มีราคาเลย)")
except (json.JSONDecodeError, KeyError) as e:
    print(f"  parse ไม่ได้: {e}\n  raw: {content[:500]}")

# ---- Test 3: OCR text → text parser เดิม (qwen2.5:14b + few-shot + schema เต็ม) ----
# หมายเหตุ: เรียก _call_ollama ตรงๆ ไม่ผ่าน parse_post เพราะ parse_post ทิ้งชิ้นที่ price=null
# แต่ฟีเจอร์ประเมินช่วงราคาต้องการ "รายชื่อชิ้น" แม้โพสต์ไม่มีราคา
print("\n=== Test 3: OCR text -> parser เดิม (qwen2.5:14b) ===")
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.parser import _call_ollama  # noqa: E402

t0 = time.time()
result = _call_ollama(ocr_text)
print(f"--- ใช้เวลา {time.time() - t0:.1f}s ---")
if result is None:
    print("  เรียก parser ไม่สำเร็จ")
else:
    for it in result.get("items", []):
        print(f"  [{it['category']:>7}] {it['item_name']}  brand={it['brand']}  "
              f"cap={it['capacity']}  price={it['price']}")
    print(f"  รวม {len(result.get('items', []))} ชิ้น")
