# -*- coding: utf-8 -*-
"""ทดลอง: think:false ถูก apply จริงไหม — ยิง 3 ครั้งติด ดู thinking/content/done_reason"""
import base64
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.vision import VISION_PROMPT, VISION_SCHEMA  # noqa: E402
from app.config import settings  # noqa: E402

img_b64 = base64.b64encode((Path(__file__).parent / "browser_post.png").read_bytes()).decode()

for i in range(3):
    payload = {
        "model": settings.ollama_vision_model,
        "format": VISION_SCHEMA,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 700},
        "messages": [
            {"role": "system", "content": VISION_PROMPT},
            {"role": "user", "content": "แยกรายการชิ้นส่วนจากรูปนี้", "images": [img_b64]},
        ],
    }
    t0 = time.time()
    body = requests.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=300).json()
    msg = body.get("message", {})
    print(f"#{i+1}: {time.time()-t0:5.1f}s done_reason={body.get('done_reason')} "
          f"eval={body.get('eval_count')} "
          f"thinking_len={len(msg.get('thinking') or '')} content_len={len(msg.get('content') or '')}")
