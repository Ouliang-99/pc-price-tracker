"""Data models ที่ใช้ส่งต่อระหว่าง scraper → parser → db.

หลัก PDPA: dataclass พวกนี้ตั้งใจ "ไม่มี" field ชื่อ/เบอร์/ที่อยู่/profile ผู้ขาย
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RawPost:
    """โพสดิบจาก Apify หลัง normalize แล้ว (ก่อนส่งเข้า parser).

    เก็บแค่ข้อความ + metadata ที่ไม่ใช่ข้อมูลส่วนบุคคล
    """

    text: str
    source: str              # "groups" | "marketplace"
    source_url: str
    posted_at: Optional[str] = None      # ISO ถ้า actor ให้มา
    price_hint: Optional[int] = None     # ราคาที่ actor แยกมาให้ (ถ้ามี)
    location_hint: Optional[str] = None  # จังหวัด/พื้นที่ ถ้า actor ให้มา
    scraped_at: str = field(default_factory=_now_iso)


@dataclass
class ParsedItem:
    """ผลลัพธ์จาก AI parser — ข้อมูลมีโครงสร้างพร้อมลง price_history."""

    item_name: str
    category: str
    price: int
    condition: str = "ไม่ระบุ"
    negotiable: bool = False
    location: str = "ไม่ระบุ"

    # taxonomy เพิ่มเติม — แยกหมวด/รุ่น/variant
    brand: str = "ไม่ระบุ"          # ASUS, MSI, Corsair, Kingston, AMD, Intel...
    form_factor: str = "ไม่ระบุ"    # Desktop | Laptop | ไม่ระบุ (สำคัญกับ RAM/SSD/GPU)
    capacity: str = "ไม่ระบุ"       # ความจุ เช่น "16GB", "1TB", "8GB"
    speed: str = "ไม่ระบุ"          # บัส/ความเร็ว เช่น "3200", "6000", "Gen4"
    cl_timing: str = "ไม่ระบุ"      # ค่า CL เช่น "CL30"
    variant: str = "ไม่ระบุ"        # 3 พัดลม / 2 พัดลม / SO-DIMM / DDR5 ฯลฯ

    # carry-over จาก RawPost
    source: str = ""
    source_url: str = ""
    posted_at: Optional[str] = None
    scraped_at: str = field(default_factory=_now_iso)

    def to_row(self) -> dict:
        """แปลงเป็น dict สำหรับ insert ลง price_history."""
        return {
            "item_name": self.item_name,
            "category": self.category,
            "price": int(self.price),
            "condition": self.condition,
            "location": self.location,
            "brand": self.brand,
            "form_factor": self.form_factor,
            "capacity": self.capacity,
            "speed": self.speed,
            "cl_timing": self.cl_timing,
            "variant": self.variant,
            "source": self.source,
            "source_url": self.source_url,
            "negotiable": 1 if self.negotiable else 0,
            "posted_at": self.posted_at,
            "scraped_at": self.scraped_at,
        }
