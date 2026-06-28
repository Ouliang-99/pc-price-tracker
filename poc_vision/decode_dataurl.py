# -*- coding: utf-8 -*-
"""decode dataURL ที่ดึงจาก canvas ในเบราว์เซอร์ → PNG"""
import base64
import sys
from pathlib import Path

src = Path(sys.argv[1])
s = src.read_text().strip().strip('"')
b = base64.b64decode(s.split(",", 1)[1])
out = Path(__file__).parent / "browser_post.png"
out.write_bytes(b)
print("saved", out, len(b))
