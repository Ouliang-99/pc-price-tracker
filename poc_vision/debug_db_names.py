# -*- coding: utf-8 -*-
"""debug: ดูชื่อ item_name ที่เก็บจริงในหมวดที่ไม่มี taxonomy"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import db  # noqa: E402

conn = db.connect()
sql = ("SELECT category, item_name, capacity, speed, COUNT(*) c FROM price_history "
       "WHERE category IN ('RAM','COOLER','PSU','SSD','HDD','CASE') "
       "GROUP BY category, item_name, capacity, speed ORDER BY category, c DESC LIMIT 40")
for r in conn.execute(sql):
    print(f"{r['category']:>7} | {r['item_name']:<30} | {r['capacity']:<8} | {r['speed']:<6} | n={r['c']}")
conn.close()
