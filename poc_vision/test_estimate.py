# -*- coding: utf-8 -*-
"""ทดสอบ end-to-end: รูป → app.vision.estimate_from_image → ช่วงราคาจาก price_history"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.vision import estimate_from_image  # noqa: E402

data = (Path(__file__).parent / "test_post.png").read_bytes()
result = estimate_from_image(data)
if result is None:
    print("FAILED: estimate_from_image คืน None")
    sys.exit(1)

for it in result["items"]:
    r = it["range"]
    rng = (f"{r['min']:,} - {r['max']:,} (med {r['median']:,}, n={r['count']}"
           f"{', เทียบทั้งรุ่น' if not r['capacity_matched'] else ''})") if r else "ไม่มีข้อมูล"
    print(f"  [{it['category']:>7}] {it['item_name']:<28} {rng}")
print("total  :", result["total"])
print(f"covered: {result['covered']}/{result['total_items']}")
