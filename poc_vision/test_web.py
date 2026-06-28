# -*- coding: utf-8 -*-
"""ทดสอบ route /estimate และ /api/estimate ผ่าน Flask test client"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.web import create_app  # noqa: E402

app = create_app()
client = app.test_client()

# หน้า estimate โหลดได้
r = client.get("/estimate")
print("GET /estimate:", r.status_code)
assert r.status_code == 200 and "ประเมินราคาจากรูป".encode() in r.data

# validation: ไม่มีไฟล์
r = client.post("/api/estimate", data={})
print("POST no file:", r.status_code, r.get_json()["error"])
assert r.status_code == 400

# validation: ไฟล์ไม่ใช่รูป
r = client.post("/api/estimate",
                data={"image": (io.BytesIO(b"hello not an image"), "x.png")})
print("POST bad file:", r.status_code, r.get_json()["error"])
assert r.status_code == 400

# ของจริง
img = (Path(__file__).parent / "test_post.png").read_bytes()
r = client.post("/api/estimate", data={"image": (io.BytesIO(img), "post.png")})
data = r.get_json()
print("POST real image:", r.status_code, "ok =", data.get("ok"))
assert r.status_code == 200 and data["ok"]
print(f"  items={data['total_items']} covered={data['covered']} total={data['total']}")
print("ALL PASS")
