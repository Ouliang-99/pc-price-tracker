# -*- coding: utf-8 -*-
"""debug: ดู response ดิบจาก Ollama vision call"""
import base64
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.vision import VISION_PROMPT, VISION_SCHEMA  # noqa: E402
from app.config import settings  # noqa: E402

img_name = sys.argv[1] if len(sys.argv) > 1 else "test_post.png"
img_b64 = base64.b64encode((Path(__file__).parent / img_name).read_bytes()).decode()
payload = {
    "model": settings.ollama_vision_model,
    "format": VISION_SCHEMA,
    "stream": False,
    "think": False,
    "options": {"temperature": 0, "num_ctx": settings.ollama_num_ctx},
    "messages": [
        {"role": "system", "content": VISION_PROMPT},
        {"role": "user", "content": "แยกรายการชิ้นส่วนจากรูปนี้", "images": [img_b64]},
    ],
}
resp = requests.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=300)
print("HTTP", resp.status_code)
body = resp.json()
print(json.dumps({k: v for k, v in body.items() if k != "message"}, indent=2))
print("content:", repr(body.get("message", {}).get("content", ""))[:2000])
