"""Vision parser — อ่าน "รูป" โพสต์ขายคอมเซ็ต → รายการชิ้นส่วน → ช่วงราคาจาก price_history

แยกจาก parser.py โดยเจตนา อย่ารวมกัน:
- parser.py มีหน้าที่เก็บราคาจริงลง price_history จึงตอบ items:[] กับโพสต์ยกเซ็ต
  และทิ้งชิ้นที่ไม่มีราคา — ฟีเจอร์นี้ต้องการตรงข้าม: รายชื่อชิ้นครบแม้ไม่มีราคา
- ช่วงราคา "ห้าม" มาจากโมเดล (โมเดล local เดาราคาตลาดมือสองไทยไม่ได้ หลอนแน่นอน
  — ดูผล PoC ใน poc_vision/) ต้องมาจาก price_history ของเราเท่านั้น

PDPA: prompt สั่งห้ามดึงชื่อ/เบอร์/ที่อยู่ และ response schema ไม่มี field พวกนั้นให้ตอบ
"""
from __future__ import annotations

import base64
import logging
import re
import statistics
from typing import Optional

import requests

from . import db
from .config import settings
from .parser import (
    CATEGORIES,
    SHOP_NAME_TOKENS,
    _clean_field,
    _clean_price,
    _match_taxonomy,
    _normalize_category,
)

log = logging.getLogger(__name__)

# ของแถม/อุปกรณ์เสริมที่โมเดลชอบนับเป็นชิ้นส่วน (เจอใน PoC: "สายถักขาว" กลายเป็น PSU อีกชิ้น)
_ACCESSORY_RE = re.compile(
    r"^(สาย|cable|ของแถม|ฟรี|ซิ[งน]ค์|heatsink|จอของเคส)", re.IGNORECASE
)

# ชุดน้ำ/AIO ที่โมเดลชอบจัดเป็น CPU — pattern หลวมเผื่อตัวสะกดเพี้ยนจากการอ่านรูป
# (เจอจริง: "ชุดน้ำปิด" ถูกอ่านเป็น "ขุดน้ำบีด")
_COOLER_RE = re.compile(r"[ชข]ุดน้ำ|น้ำ[ปบ][ิี]ด|\baio\b|liquid|freezer", re.IGNORECASE)

# RAM ใน price_history เก็บ item_name เป็นชื่อ generation ("DDR4"/"DDR5") + capacity/speed
# แยกต่างหาก (ตาม SYSTEM_PROMPT ของ parser เดิม) — vision ต้อง canonicalize ให้ตรงกัน
_RE_RAM_GEN = re.compile(r"\bddr\s*(\d)\b", re.IGNORECASE)

# schema เล็กกว่าของ parser.py — ไม่มี price บังคับ ไม่มี location/condition
# (รูปคอมเซ็ตส่วนใหญ่ไม่มีข้อมูลพวกนี้ และเป้าหมายคือ "รายชื่อชิ้น" ไม่ใช่เก็บลง DB)
VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "brand": {"type": "string"},
                    "capacity": {"type": "string"},
                    "speed": {"type": "string"},
                    "price": {"type": ["integer", "null"]},
                },
                "required": ["item_name", "category", "brand",
                             "capacity", "speed", "price"],
            },
        }
    },
    "required": ["items"],
}

VISION_PROMPT = """คุณเป็นตัวช่วยอ่านรูปโพสต์ขายคอมพิวเตอร์/ชิ้นส่วนมือสองภาษาไทย
ดึงรายการชิ้นส่วนทุกชิ้นที่ปรากฏในรูปออกมาเป็น JSON ตาม schema

กฎ:
- item_name = ชื่อรุ่นตามที่เขียนในรูป เช่น "i9 13900K", "RTX 5070 Aero White",
  "Kingston DDR4 32GB 3200" ห้ามตอบเป็นชื่อหมวดอย่าง "CPU" หรือ "การ์ดจอ"
- capacity = ความจุ เช่น "32GB", "1TB" / speed = บัสหรือความเร็ว เช่น "3200" ไม่มีให้ "ไม่ระบุ"
- สายไฟ/สายถัก/ของแถม/ซิงค์ระบายความร้อนที่พ่วงกับชิ้นอื่น ไม่ใช่ชิ้นส่วน ห้ามแยกเป็นรายการ
- เคสกับจอ/อุปกรณ์ที่ติดมากับเคส นับเป็น CASE รายการเดียว
- price = ราคาที่เขียนกำกับชิ้นนั้นโดยตรงในรูปเท่านั้น ถ้าไม่มีให้ null
  ห้ามเดา ห้ามเอาราคารวมทั้งเซ็ตมาใส่รายชิ้น
- ห้ามดึงชื่อคน เบอร์โทร ที่อยู่ หรือชื่อร้าน ออกมาเป็นข้อมูล
- ห้ามคิดวิเคราะห์! (DO NOT REASON OR THINK!) ห้ามใช้ <think> tags เด็ดขาด ให้ตอบด้วย ```json ทันทีเป็นบรรทัดแรก"""


def _call_vision(image_b64: str, timeout: int = 300) -> Optional[dict]:
    """เรียกโมเดล vision ผ่าน Ollama chat API. คืน dict หรือ None ถ้าพลาด."""
    import json as _json
    url = f"{settings.ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_vision_model,
        "stream": False,
        "options": {"temperature": 0.4, "num_ctx": settings.ollama_num_ctx, "num_predict": 2048},
        "messages": [
            {"role": "system", "content": VISION_PROMPT + "\n\nต้องตอบกลับเป็น JSON block หุ้มด้วย ```json และ ``` ตาม schema นี้:\n" + _json.dumps(VISION_SCHEMA)},
            {"role": "user", "content": "ตัวอย่างโพสต์: 'ขาย i5 12400f ราคา 3000'"},
            {"role": "assistant", "content": "```json\n{\n  \"items\": [\n    {\n      \"item_name\": \"CORE I5-12400F\",\n      \"category\": \"CPU\",\n      \"brand\": \"INTEL\",\n      \"capacity\": \"\",\n      \"speed\": \"\",\n      \"price\": 3000\n    }\n  ]\n}\n```"},
            {"role": "user", "content": "แยกรายการชิ้นส่วนจากรูปนี้",
             "images": [image_b64]},
        ],
    }
    # บั๊ก Ollama (พบกับ qwen3-vl:8b, มิ.ย. 2026): request แรกหลังโหลดโมเดลเข้า VRAM
    # think:false ไม่ถูก apply → โมเดลคิดจนชน num_predict → content ว่าง (done_reason=length)
    # request ถัดไปปกติ → retry 1 ครั้งแก้ได้ (reproduce ได้ด้วย ollama stop แล้วยิงใหม่)
    for attempt in (1, 2):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("เรียก Ollama vision ไม่สำเร็จ: %s", e)
            return None

        body = resp.json()
        content = body.get("message", {}).get("content", "")
        thinking = body.get("message", {}).get("thinking", "")
        
        if not content and thinking:
            log.warning("Ollama content empty. Thinking length: %d. Tail: %r", len(thinking), thinking[-500:])
            # Fallback: if content is empty, maybe the model put the JSON inside thinking?
            content = thinking
        
        import re
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
        else:
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                content = content[start:end+1]

        try:
            import json as _json
            return _json.loads(content)
        except (ValueError, TypeError):
            log.warning(
                "Ollama vision ตอบไม่ใช่ JSON (attempt %d, done_reason=%s, eval_count=%s): %r",
                attempt, body.get("done_reason"), body.get("eval_count"), content[:200],
            )
    return None


def parse_image(image_bytes: bytes) -> Optional[list[dict]]:
    """รูปโพสต์ขาย → รายการชิ้นส่วน (normalize + ผ่าน guard แล้ว).

    คืน None ถ้าเรียกโมเดลไม่สำเร็จ, [] ถ้าอ่านได้แต่ไม่มีชิ้นส่วน
    """
    data = _call_vision(base64.b64encode(image_bytes).decode())
    if data is None:
        return None

    items: list[dict] = []
    for raw in data.get("items", []):
        name = _clean_field(raw.get("item_name"), default="")
        if not name:
            continue
        # guard ชุดเดียวกับ parser เดิม: ชื่อร้าน + ของแถม/สายไฟที่หลุดมาเป็นชิ้น
        low = name.lower()
        if any(tok in low for tok in SHOP_NAME_TOKENS):
            log.info("vision ข้ามชิ้น: item_name เป็นชื่อร้าน (%r)", name)
            continue
        if _ACCESSORY_RE.search(name):
            log.info("vision ข้ามชิ้น: เป็นของแถม/อุปกรณ์เสริม (%r)", name)
            continue

        category = _normalize_category(raw.get("category"), name)
        if category != "COOLER" and _COOLER_RE.search(name):
            category = "COOLER"

        item_name = _match_taxonomy(category, name, name)
        if category == "RAM":
            m = _RE_RAM_GEN.search(name)
            if m:
                item_name = f"DDR{m.group(1)}"

        items.append({
            "item_name": item_name,
            "raw_name": name,
            "category": category,
            "brand": _clean_field(raw.get("brand")),
            "capacity": _clean_field(raw.get("capacity")),
            "speed": _clean_field(raw.get("speed")),
            "listed_price": _clean_price(raw.get("price")),
        })
    return items


def _price_range(item_name: str, capacity: str) -> Optional[dict]:
    """ช่วงราคาจาก price_history. คืน None ถ้าไม่มีข้อมูลรุ่นนี้เลย."""
    prices, cap_matched = db.get_prices(item_name, capacity)
    if not prices:
        return None
    return {
        "min": min(prices),
        "median": round(statistics.median(prices)),
        "max": max(prices),
        "count": len(prices),
        "capacity_matched": cap_matched,
    }


def estimate_from_image(image_bytes: bytes) -> Optional[dict]:
    """รูป → รายการชิ้นส่วนพร้อมช่วงราคา + ราคารวมของเซ็ต.

    ราคารวมรวมเฉพาะชิ้นที่มีข้อมูลใน price_history — ชิ้นที่ไม่มีข้อมูล
    แสดง range เป็น null ให้ UI บอกผู้ใช้ตรงๆ ดีกว่าให้โมเดลเดา
    """
    items = parse_image(image_bytes)
    if items is None:
        return None

    covered = 0
    total = {"min": 0, "median": 0, "max": 0}
    for it in items:
        rng = _price_range(it["item_name"], it["capacity"])
        it["range"] = rng
        if rng:
            covered += 1
            for k in total:
                total[k] += rng[k]

    return {
        "items": items,
        "total": total if covered else None,
        "covered": covered,
        "total_items": len(items),
        "model": settings.ollama_vision_model,
    }
