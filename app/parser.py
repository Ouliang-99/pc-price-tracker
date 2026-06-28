"""AI parser — แปลงโพสภาษาไทย → ParsedItem ด้วย Ollama (qwen2.5:14b).

ใช้ Ollama /api/chat แบบ format=json บังคับให้ตอบเป็น JSON
ถ้า parse ไม่ได้ → คืน None + log warning (ไม่ throw เพื่อไม่ให้ job ตาย)

PDPA: prompt สั่งชัดเจน "ห้ามดึงชื่อ/เบอร์/ที่อยู่/ลิงก์ผู้ขาย"
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import requests

from .config import settings
from .models import ParsedItem, RawPost
from .taxonomy import MODELS_TAXONOMY

log = logging.getLogger(__name__)

# หมวดที่ยอมรับ — normalize ให้อยู่ในชุดนี้
CATEGORIES = ["GPU", "CPU", "RAM", "MB", "PSU", "SSD", "HDD", "CASE",
              "COOLER", "MONITOR", "NOTEBOOK", "OTHER"]

# form factor ที่ยอมรับ
FORM_FACTORS = ["Desktop", "Laptop", "ไม่ระบุ"]

# ชื่อร้าน/ตัวแทนจำหน่ายที่ AI ชอบหลงคิดว่าเป็นชื่อสินค้า/ยี่ห้อ
SHOP_NAME_TOKENS = ("ihavecpu", "i have cpu", "i have", "jib ", "advice it", "banana it")

# คำที่บ่งว่าโพสต์พูดถึงโน๊ตบุ๊คจริง (กัน AI เห็นชื่อรุ่นการ์ดจอ เช่น "SHADOW 3X" แล้วหลอนเป็น NOTEBOOK)
_NB_WORDS = re.compile(r"โน[๊้]?[ตด]\s*บุ[๊้]?[คก]|notebook|laptop", re.IGNORECASE)

# JSON Schema สำหรับ Ollama structured outputs (format=schema)
# บังคับ category/form_factor ให้อยู่ใน enum + price เป็น integer หรือ null เท่านั้น
# → ตัดปัญหา AI ตอบหมวดนอกลิสต์ / ราคาเป็นข้อความ ตั้งแต่ตอน generate
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string"},
                    "item_name": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "brand": {"type": "string"},
                    "form_factor": {"type": "string", "enum": FORM_FACTORS},
                    "capacity": {"type": "string"},
                    "speed": {"type": "string"},
                    "cl_timing": {"type": "string"},
                    "variant": {"type": "string"},
                    "price": {"type": ["integer", "null"]},
                    "condition": {"type": "string"},
                    "negotiable": {"type": "boolean"},
                    "location": {"type": "string"},
                },
                "required": ["reasoning", "item_name", "category", "brand",
                             "form_factor", "capacity", "speed", "cl_timing",
                             "variant", "price", "condition", "negotiable", "location"],
            },
        }
    },
    "required": ["items"],
}

SYSTEM_PROMPT = """คุณเป็นตัวช่วยแยกข้อมูลสินค้าคอมพิวเตอร์มือสองจากโพสขายภาษาไทย
ดึงข้อมูลออกมาเป็น JSON เท่านั้น ในรูปแบบ Array ภายใต้ key "items" ตาม schema นี้:
{
  "items": [
    {
      "reasoning": string,   // อธิบายเหตุผลในการแยกประเภทสินค้าและสเปก
      "item_name": string,   // ชื่อรุ่นมาตรฐาน ไม่ใส่ยี่ห้อ/จำนวนพัดลม เช่น "RTX 4070 Super", "Ryzen 5 7600", "DDR5"
      "category": string,    // หนึ่งใน: GPU, CPU, RAM, MB, PSU, SSD, HDD, CASE, COOLER, MONITOR, NOTEBOOK, OTHER
      "brand": string,       // ยี่ห้อ เช่น "ASUS","MSI","Gigabyte","Zotac","Inno3D","Corsair","Kingston","AMD","Intel" ไม่มีให้ "ไม่ระบุ"
      "form_factor": string, // "Desktop" หรือ "Laptop" (RAM/SSD/CPU/GPU ของโน๊ตบุ๊คให้ "Laptop") ไม่ชัดให้ "ไม่ระบุ"
      "capacity": string,    // ความจุ เช่น "16GB", "1TB", "8GB", "500GB" ไม่มีให้ "ไม่ระบุ"
      "speed": string,       // บัส หรือความเร็ว เช่น "3200", "6000", "Gen4" ไม่มีให้ "ไม่ระบุ"
      "cl_timing": string,   // ค่า CL ของ RAM เช่น "CL30", "CL32" ไม่มีให้ "ไม่ระบุ"
      "variant": string,     // จุดที่ทำให้ต่างในรุ่นเดียวกัน เช่น "3 พัดลม","2 พัดลม","SO-DIMM" ไม่มีให้ "ไม่ระบุ"
      "price": number|null,  // ราคาของ "ชิ้นนั้น" เป็นจำนวนเต็มบาท ถ้าชิ้นนั้นไม่มีราคาของตัวเองให้ null
      "condition": string,   // เช่น "มือสอง", "มือหนึ่ง", "ประกันศูนย์", หรือ "ไม่ระบุ"
      "negotiable": boolean, // true ถ้าต่อรองได้/ลดได้
      "location": string     // จังหวัด/พื้นที่ เช่น "นนทบุรี" ถ้าไม่มีให้ "ไม่ระบุ"
    }
  ]
}

กฎเรื่องราคา (สำคัญที่สุด):
- price ของแต่ละชิ้นต้องเป็นราคาที่เขียนกำกับชิ้นนั้นโดยตรงในโพสต์เท่านั้น
- ถ้าชิ้นไหนไม่มีราคาของตัวเอง ให้ price = null ห้ามเดา ห้ามหารเฉลี่ย
- ห้ามนำราคารวมของทั้งโพสต์ไปใส่ให้ชิ้นส่วนย่อยเด็ดขาด
- คอมประกอบครบเครื่อง/ขายยกเซ็ต/ขายเหมามัดรวม ที่มีราคาเดียว → ตอบ {"items": []} ทันที
- โพสรับซื้อ/ประมูล/ตามหาของ → ตอบ {"items": []}

กฎเรื่องโน๊ตบุ๊ค:
- โพสขายโน๊ตบุ๊คทั้งเครื่อง → สร้างแค่ 1 รายการ category = "NOTEBOOK" เท่านั้น
- สเปกข้างในเครื่อง (CPU/GPU/RAM/SSD) ให้สรุปไว้ใน variant ห้ามแยกออกมาเป็นรายการต่างหาก
- ถ้าโพสต์ไม่มีคำว่า โน๊ตบุ๊ค/Notebook/Laptop เลย ห้ามตอบ NOTEBOOK
- ระวัง: SHADOW 3X, VENTUS, GAMING TRIO, DUAL, TUF, ROG STRIX, EAGLE, WINDFORCE, AORUS
  คือชื่อรุ่นย่อยของ "การ์ดจอ" แต่ละยี่ห้อ ไม่ใช่โน๊ตบุ๊ค (เช่น "MSI SHADOW 3X RTX 5070" = การ์ดจอ GPU)

กฎอื่นๆ:
- หากโพสต์ขายสินค้าหลายชิ้นแยกราคากัน (ขายกำแพง, ลิสต์ 1. 2. 3.) ให้แยกแต่ละชิ้นเป็น object
- item_name ต้องเป็นชื่อรุ่นกลางๆ (ยี่ห้อไปไว้ brand, จำนวนพัดลม/สี/ชนิดไปไว้ variant)
- item_name ต้องเป็นชื่อสินค้าจริง — iHAVECPU, JIB, Advice, Banana คือชื่อร้าน ไม่ใช่สินค้า/ยี่ห้อ
- RAM/SSD ของโน๊ตบุ๊คที่ขายแยก (SO-DIMM/แรมโน๊ตบุ๊ค) ให้ form_factor = "Laptop"
- การ์ดจอให้ดูจำนวนพัดลมใส่ใน variant ("3 พัดลม"/"2 พัดลม"/"1 พัดลม") ถ้าระบุ
- MB: เมนบอร์ด มักมีคำว่า Socket, LGA, AM4, AM5, B650, Z790
- PSU: พาวเวอร์ซัพพลาย มักมีคำว่า 80+, 850W, Watt
- SSD: ให้ตั้งชื่อ item_name นำหน้าด้วยคำว่า "SSD" แล้วตามด้วยชนิด (ถ้ามี) เช่น "SSD M.2 NVMe", "SSD SATA" ส่วนความจุให้ใส่ที่ capacity เช่น "500GB", "1TB"
- MONITOR: item_name ใช้ชื่อรุ่นถ้ามี ถ้าไม่มีให้ใช้ "Monitor <ขนาด> <ความละเอียด> <Hz>" เช่น "Monitor 24 FHD 144Hz" (ห้ามใช้คำว่า "Monitor" เฉยๆ)
- ห้ามดึงชื่อคน เบอร์โทร ที่อยู่ หรือลิงก์ติดต่อผู้ขาย (ความเป็นส่วนตัว)
- ตอบเป็น JSON อย่างเดียว ห้ามมีข้อความอื่น"""

FEWSHOT_USER = "ขาย การ์ดจอ ASUS DUAL RTX 4070 Super 2 พัดลม มือสอง สภาพสวย 8,500 บาท ต่อรองได้ อยู่นนทบุรี"
FEWSHOT_ASSISTANT = json.dumps(
    {
        "items": [
            {
                "reasoning": "สินค้าคือ 'RTX 4070 Super' ซึ่งเป็นการ์ดจอ (GPU)",
                "item_name": "RTX 4070 Super",
                "category": "GPU",
                "brand": "ASUS",
                "form_factor": "Desktop",
                "capacity": "ไม่ระบุ",
                "speed": "ไม่ระบุ",
                "cl_timing": "ไม่ระบุ",
                "variant": "2 พัดลม",
                "price": 8500,
                "condition": "มือสอง",
                "negotiable": True,
                "location": "นนทบุรี",
            }
        ]
    },
    ensure_ascii=False,
)
FEWSHOT_USER2 = "ขายเหมา 1. แรมโน๊ตบุ๊ค Kingston DDR4 16GB 450 บาท 2. SSD M.2 NVMe 500GB 500 บาท 3. การ์ดจอ GTX 1650 ทักมาคุยราคาได้ กรุงเทพ"
FEWSHOT_ASSISTANT2 = json.dumps(
    {
        "items": [
            {
                "reasoning": "ชิ้นแรกคือ 'DDR4' แรมโน๊ตบุ๊ค",
                "item_name": "DDR4",
                "category": "RAM",
                "brand": "Kingston",
                "form_factor": "Laptop",
                "capacity": "16GB",
                "speed": "ไม่ระบุ",
                "cl_timing": "ไม่ระบุ",
                "variant": "SO-DIMM",
                "price": 450,
                "condition": "มือสอง",
                "negotiable": False,
                "location": "กรุงเทพ",
            },
            {
                "reasoning": "ชิ้นที่สองคือ 'SSD' แบบ M.2 NVMe ความจุ 500GB",
                "item_name": "SSD M.2 NVMe",
                "category": "SSD",
                "brand": "ไม่ระบุ",
                "form_factor": "ไม่ระบุ",
                "capacity": "500GB",
                "speed": "ไม่ระบุ",
                "cl_timing": "ไม่ระบุ",
                "variant": "ไม่ระบุ",
                "price": 500,
                "condition": "มือสอง",
                "negotiable": False,
                "location": "กรุงเทพ",
            },
            {
                "reasoning": "ชิ้นที่สามคือ 'GTX 1650' แต่ไม่ได้ระบุราคาของตัวเอง (ให้ทักไปคุย) จึงใส่ price = null",
                "item_name": "GTX 1650",
                "category": "GPU",
                "brand": "ไม่ระบุ",
                "form_factor": "Desktop",
                "capacity": "ไม่ระบุ",
                "speed": "ไม่ระบุ",
                "cl_timing": "ไม่ระบุ",
                "variant": "ไม่ระบุ",
                "price": None,
                "condition": "มือสอง",
                "negotiable": True,
                "location": "กรุงเทพ",
            }
        ]
    },
    ensure_ascii=False,
)

FEWSHOT_USER3 = """ขายคอมพร้อมใช้งาน เล่นเกมลื่นๆ
CPU Ryzen 5 5600X
MB A520M
RAM 16GB
SSD 500GB
GPU RTX 3060 12GB
ทั้งหมดนี้ราคา 18500 บาท นัดรับได้"""
FEWSHOT_ASSISTANT3 = json.dumps(
    {
        "items": []
    },
    ensure_ascii=False,
)

FEWSHOT_USER4 = """ขายโน๊ตบุ๊คเกมมิ่ง MSI Katana 15 สภาพนางฟ้า
สเปค i7-13620H / RTX 4060 / RAM 16GB / SSD 512GB / จอ 144Hz
ราคา 21,900 บาท ลดได้นิดหน่อย อยู่เชียงใหม่"""
FEWSHOT_ASSISTANT4 = json.dumps(
    {
        "items": [
            {
                "reasoning": "โพสขายโน๊ตบุ๊คทั้งเครื่อง จึงสร้างรายการเดียวเป็น NOTEBOOK "
                             "สเปกข้างใน (CPU/GPU/RAM/SSD) สรุปไว้ใน variant ไม่แยกเป็นรายการ",
                "item_name": "Katana 15",
                "category": "NOTEBOOK",
                "brand": "MSI",
                "form_factor": "Laptop",
                "capacity": "ไม่ระบุ",
                "speed": "ไม่ระบุ",
                "cl_timing": "ไม่ระบุ",
                "variant": "i7-13620H / RTX 4060 / 16GB / 512GB / 144Hz",
                "price": 21900,
                "condition": "มือสอง",
                "negotiable": True,
                "location": "เชียงใหม่",
            }
        ]
    },
    ensure_ascii=False,
)


def _clean_price(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def _normalize_category(cat: Optional[str], text: str = "") -> str:
    t = text.lower()
    
    # Heuristic Fallbacks (ถ้า AI ตอบมั่ว หรืออยากบังคับให้ตรงเป๊ะ)
    if not cat or cat.strip().upper() not in CATEGORIES:
        if "rtx" in t or "gtx" in t or "rx 6" in t or "rx 7" in t or "vga" in t or "การ์ดจอ" in t:
            return "GPU"
        if "ryzen" in t or "core i" in t:
            return "CPU"
        if "ddr4" in t or "ddr5" in t or "แรม" in t:
            return "RAM"
        if "watt" in t or "80+" in t or "80 plus" in t or "psu" in t:
            return "PSU"
        if "lga" in t or "am4" in t or "am5" in t or "เมนบอร์ด" in t:
            return "MB"
        if "ssd" in t or "nvme" in t or "m.2" in t:
            return "SSD"
        return "OTHER"

    return cat.strip().upper()


def _clean_field(value, default: str = "ไม่ระบุ") -> str:
    """ทำความสะอาด string field (brand/variant) — ตัดช่องว่าง, ค่าว่าง → default."""
    if value is None:
        return default
    s = str(value).strip()
    if not s or s.lower() in ("none", "null", "n/a", "-", "unknown"):
        return default
    return s


def _normalize_form_factor(value) -> str:
    s = _clean_field(value)
    low = s.lower()
    if low in ("desktop", "pc", "คอม", "คอมตั้งโต๊ะ"):
        return "Desktop"
    if low in ("laptop", "notebook", "โน๊ตบุ๊ค", "โน้ตบุ๊ก", "so-dimm", "sodimm"):
        return "Laptop"
    if s in ("Desktop", "Laptop"):
        return s
    return "ไม่ระบุ"


# regex สำหรับ canonicalize ชื่อรุ่นที่หลุด taxonomy (เช่น "i7 9700F", "Rx560", "I7-12700")
# \b หน้า r/i กันชนกับ ddr5, gddr ฯลฯ (ตัวอักษรก่อนหน้าเป็น word char จะไม่ match)
_RE_INTEL = re.compile(r"\bi([3579])[\s\-]*(\d{4,5})\s*(ks|kf|k|f|t)?\b", re.IGNORECASE)
_RE_RYZEN = re.compile(r"\b(?:ryzen\s*|r)([3579])[\s\-]*(\d{4})\s*(x3d|xt|x|gt|ge|g|f)?\b", re.IGNORECASE)
_RE_GPU_NV = re.compile(r"\b(rtx|gtx|gt)\s*(\d{3,4})\s*(ti\s*super|ti|super)?\b", re.IGNORECASE)
_RE_GPU_AMD = re.compile(r"\brx\s*(\d{3,4})\s*(xtx|xt|gre)?\b", re.IGNORECASE)


def _canonical_name(category: str, text: str) -> Optional[str]:
    """แปลงชื่อรุ่น CPU/GPU เป็นรูปแบบมาตรฐานด้วย regex (fallback เมื่อ taxonomy ไม่ match)."""
    if category == "CPU":
        m = _RE_INTEL.search(text)
        if m:
            suffix = (m.group(3) or "").upper()
            return f"Core i{m.group(1)}-{m.group(2)}{suffix}"
        m = _RE_RYZEN.search(text)
        if m:
            suffix = (m.group(3) or "").upper()
            return f"Ryzen {m.group(1)} {m.group(2)}{suffix}"
    elif category == "GPU":
        m = _RE_GPU_NV.search(text)
        if m:
            suffix = re.sub(r"\s+", " ", (m.group(3) or "")).title()
            return f"{m.group(1).upper()} {m.group(2)}{(' ' + suffix) if suffix else ''}"
        m = _RE_GPU_AMD.search(text)
        if m:
            suffix = (m.group(2) or "").upper()
            return f"RX {m.group(1)}{(' ' + suffix) if suffix else ''}"
    return None


def _match_taxonomy(category: str, text: str, ai_item_name: str) -> str:
    """เทียบ text ต้นฉบับและ item_name ที่ AI ได้มากับ Taxonomy เพื่อหาชื่อมาตรฐาน."""
    cat = category.strip().upper()
    if cat not in MODELS_TAXONOMY and cat not in ("CPU", "GPU"):
        return ai_item_name

    t = text.lower()
    ai_name = ai_item_name.lower()

    # กัน keyword ตัวเลขล้วนของ CPU (เช่น "5600", "3600") ไป match ความเร็วแรม
    if cat == "CPU" and re.search(r"\bddr\d", ai_name):
        return ai_item_name

    # 1. เช็คในชื่อที่ AI สกัดมาก่อน (แม่นที่สุด) — ใช้ขอบเขตตัวเลขกัน 4070 ชน 40700
    for model in MODELS_TAXONOMY.get(cat, []):
        for kw in model["keywords"]:
            if re.search(r"(?<!\d)" + re.escape(kw) + r"(?!\d)", ai_name):
                return model["standard"]

    # 2. canonicalize ชื่อจาก AI ด้วย regex (จับรุ่นที่ไม่อยู่ใน taxonomy เช่น i7-12700, RX 560)
    canon = _canonical_name(cat, ai_item_name)
    if canon:
        return canon

    # 3. ถ้าไม่เจอใน AI เลย ค่อยลองหาในข้อความดิบ (เผื่อ AI พลาด)
    for model in MODELS_TAXONOMY.get(cat, []):
        for kw in model["keywords"]:
            # ใช้ (?<!\d) และ (?!\d) เพื่อให้ตัวเลขไม่ไปปนกับตัวเลขอื่น เช่น 4070 ไม่ไป match กับ 40700
            pattern = r'(?<!\d)' + re.escape(kw) + r'(?!\d)'
            if re.search(pattern, t):
                return model["standard"]

    return ai_item_name


def _call_ollama(text: str, timeout: int = 120) -> Optional[dict]:
    """เรียก Ollama chat API. คืน dict ที่ parse แล้ว หรือ None ถ้าพลาด."""
    url = f"{settings.ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_model,
        # structured outputs: ส่ง JSON Schema เต็มแทนคำว่า "json"
        # → Ollama บังคับ grammar ตอน generate เลย หมวด/ชนิดข้อมูลเพี้ยนไม่ได้
        "format": RESPONSE_SCHEMA,
        "stream": False,
        # num_ctx เล็ก → KV cache เล็ก → โมเดลลงครบ VRAM → 100% GPU
        # แต่ต้องพอสำหรับ system prompt + few-shot + โพสขายกำแพงยาวๆ (ดู OLLAMA_NUM_CTX)
        "options": {"temperature": 0, "num_ctx": settings.ollama_num_ctx},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": FEWSHOT_USER},
            {"role": "assistant", "content": FEWSHOT_ASSISTANT},
            {"role": "user", "content": FEWSHOT_USER2},
            {"role": "assistant", "content": FEWSHOT_ASSISTANT2},
            {"role": "user", "content": FEWSHOT_USER3},
            {"role": "assistant", "content": FEWSHOT_ASSISTANT3},
            {"role": "user", "content": FEWSHOT_USER4},
            {"role": "assistant", "content": FEWSHOT_ASSISTANT4},
            {"role": "user", "content": text},
        ],
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("เรียก Ollama ไม่สำเร็จ: %s", e)
        return None

    content = resp.json().get("message", {}).get("content", "")
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        log.warning("Ollama ตอบไม่ใช่ JSON: %r", content[:200])
        return None


def parse_post(post: RawPost) -> list[ParsedItem]:
    """แปลง RawPost → list[ParsedItem] (รองรับโพสต์ที่มีหลายชิ้น)."""
    if not post.text or not post.text.strip():
        log.warning("ข้าม: โพสไม่มีข้อความ (%s)", post.source_url)
        return []

    # แนบราคาและสถานที่จาก metadata เข้าไปใน text เพื่อให้ AI อ่านเจอ
    # ช่วยแก้ปัญหา Facebook Marketplace ที่คนขายมักไม่พิมพ์ราคา/สถานที่ใน Description
    text_to_parse = post.text
    if post.price_hint:
        text_to_parse += f"\nราคาอ้างอิง: {post.price_hint} บาท"
    if post.location_hint:
        text_to_parse += f"\nสถานที่: {post.location_hint}"

    response_data = _call_ollama(text_to_parse)
    if not response_data or not response_data.get("items"):
        log.warning("ข้าม: parse ไม่ได้ หรือไม่มี items (%s)", post.source_url)
        return []

    parsed_items = []
    items = response_data.get("items", [])
    for data in items:
        if not data.get("item_name"):
            continue

        # กรองชื่อร้านที่ AI หลงคิดว่าเป็นสินค้า (เช่น "Ihavecpu", "i have Up2")
        name_low = str(data["item_name"]).strip().lower()
        if any(tok in name_low for tok in SHOP_NAME_TOKENS):
            log.info("ข้ามชิ้น: item_name เป็นชื่อร้าน (%r)", data["item_name"])
            continue

        price = _clean_price(data.get("price"))
        # ถ้าระบุราคาใน array ไม่ได้ ลองใช้ fallback จาก price_hint ของโพสต์หลัก
        if not price or price <= 0:
            if len(items) == 1 and post.price_hint:
                price = post.price_hint
            else:
                continue

        location = (data.get("location") or post.location_hint or "ไม่ระบุ").strip()

        category = _normalize_category(data.get("category"), post.text)

        # AI ชอบเห็นชื่อรุ่นการ์ดจอ (SHADOW 3X, VENTUS ฯลฯ) แล้วหลอนเป็น NOTEBOOK
        # ถ้าโพสต์ไม่มีคำว่าโน๊ตบุ๊ค/laptop เลย → จัดหมวดใหม่จากข้อความดิบ
        if category == "NOTEBOOK" and not _NB_WORDS.search(post.text):
            category = _normalize_category(None, post.text)
            log.info("แก้หมวด NOTEBOOK→%s (โพสต์ไม่มีคำว่าโน๊ตบุ๊ค) %s", category, post.source_url)
        ai_item_name = str(data["item_name"]).strip()
        final_item_name = _match_taxonomy(category, post.text, ai_item_name)

        # บังคับเคลียร์ speed ของ GPU ให้เป็น 'ไม่ระบุ'
        # ส่วน CPU, MB เคลียร์ทั้งคู่ เพื่อลดการสร้างแถวซ้ำซ้อนใน Catalog 
        # (ยอมให้ GPU เก็บ capacity ไว้เพื่อแยกรุ่น 8GB / 16GB)
        capacity = _clean_field(data.get("capacity"))
        speed = _clean_field(data.get("speed"))
        
        if category in ("CPU", "MB"):
            capacity = "ไม่ระบุ"
            speed = "ไม่ระบุ"
        elif category == "GPU":
            speed = "ไม่ระบุ"
            from app.taxonomy import MULTI_VRAM_GPUS
            if final_item_name not in MULTI_VRAM_GPUS:
                capacity = "ไม่ระบุ"

        parsed_items.append(ParsedItem(
            item_name=final_item_name,
            category=category,
            price=price,
            condition=_clean_field(data.get("condition")),
            negotiable=bool(data.get("negotiable", False)),
            location=location or "ไม่ระบุ",
            brand=_clean_field(data.get("brand")),
            form_factor=_normalize_form_factor(data.get("form_factor")),
            capacity=capacity,
            speed=speed,
            cl_timing=_clean_field(data.get("cl_timing")),
            variant=_clean_field(data.get("variant")),
            source=post.source,
            source_url=post.source_url,
            posted_at=post.posted_at,
            scraped_at=post.scraped_at,
        ))

    # --- guard กันหลอน (AI ฝ่าฝืนกฎใน prompt ได้เสมอ ต้องเช็คซ้ำใน code) ---

    # 1) dedup ภายในโพสต์เดียวกัน (AI บางทีตอบชิ้นเดิมซ้ำ)
    seen: set = set()
    unique_items = []
    for p in parsed_items:
        key = (p.item_name.lower(), p.price, p.capacity)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(p)
    parsed_items = unique_items

    # 2) ราคารวมยกเซ็ตรั่วใส่ทุกชิ้น: หลายชิ้น + คนละหมวด + ราคาเดียวกันหมด
    #    = โพสคอมประกอบ/โน๊ตบุ๊คที่ AI แตกสเปกออกมาแล้วก๊อปราคารวมใส่ทุกชิ้น
    if len(parsed_items) >= 2:
        prices = {p.price for p in parsed_items}
        cats = {p.category for p in parsed_items}
        if len(prices) == 1 and len(cats) >= 2:
            notebooks = [p for p in parsed_items if p.category == "NOTEBOOK"]
            if notebooks and _NB_WORDS.search(post.text):
                # โพสขายโน๊ตบุ๊คจริง — เก็บแค่ตัวเครื่อง ทิ้งชิ้นส่วนข้างในที่ AI แตกออกมา
                log.info("ตัดชิ้นส่วนในเครื่องออก เหลือ NOTEBOOK อย่างเดียว (%s)", post.source_url)
                parsed_items = notebooks[:1]
            else:
                log.warning("ข้าม: สงสัยราคารวมยกเซ็ตรั่วใส่ทุกชิ้น (%d ชิ้น ราคา %s เท่ากันหมด) %s",
                            len(parsed_items), parsed_items[0].price, post.source_url)
                return []

    return parsed_items


def health_check() -> bool:
    """เช็คว่า Ollama ออนไลน์ + มี model ที่ตั้งไว้."""
    try:
        resp = requests.get(f"{settings.ollama_host.rstrip('/')}/api/tags", timeout=10)
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        ok = any(settings.ollama_model in m for m in models)
        if not ok:
            log.warning("ไม่พบ model %s ใน Ollama (มี: %s)", settings.ollama_model, models)
        return ok
    except requests.RequestException as e:
        log.warning("Ollama health check ล้มเหลว: %s", e)
        return False


if __name__ == "__main__":
    import sys
    from .config import setup_logging

    setup_logging()
    sample = sys.argv[1] if len(sys.argv) > 1 else FEWSHOT_USER
    print("Ollama online:", health_check())
    result = parse_post(RawPost(text=sample, source="test", source_url="test://1"))
    print(result)
