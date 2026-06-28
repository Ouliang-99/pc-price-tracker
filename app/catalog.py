"""Catalog — สรุป stats ราคาต่อสินค้า (อ่านจาก view item_catalog)."""
from __future__ import annotations

import logging
from typing import Optional

from . import db
from .taxonomy import MODELS_TAXONOMY

log = logging.getLogger(__name__)


# ลำดับหมวดที่อยากให้โชว์ก่อน (นอกนั้นต่อท้าย)
CATEGORY_ORDER = ["GPU", "CPU", "MB", "RAM", "SSD", "HDD", "PSU",
                  "COOLER", "CASE", "MONITOR", "NOTEBOOK", "OTHER"]

def _get_taxonomy_index(cat: str, item_name: str) -> int:
    """หาลำดับชั้นของรุ่นจาก Taxonomy (รุ่นบนๆ/ใหม่ๆ index น้อยจะอยู่บนสุด)"""
    if cat in MODELS_TAXONOMY:
        for idx, model in enumerate(MODELS_TAXONOMY[cat]):
            if model["standard"] == item_name:
                return idx
    return 9999


def get_all() -> list[dict]:
    """ทุก price-line ใน catalog (รุ่น+form_factor+variant) เรียงตาม sample."""
    return db.get_catalog()


def by_category() -> list[tuple[str, list[dict]]]:
    """จัดกลุ่ม catalog ตามหมวด → [(category, [rows...]), ...] ตาม CATEGORY_ORDER."""
    groups: dict[str, list[dict]] = {}
    for row in db.get_catalog():
        groups.setdefault(row["category"], []).append(row)

    def cat_key(cat: str) -> tuple[int, str]:
        return (CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else 99, cat)

    result = []
    for cat in sorted(groups, key=cat_key):
        rows = sorted(
            groups[cat], 
            key=lambda r: (_get_taxonomy_index(r["category"], r["item_name"]), -r["sample_count"], r["item_name"])
        )
        result.append((cat, rows))
    return result


def get_item_variants(item_name: str) -> list[dict]:
    """ทุก variant/form_factor ของรุ่นนี้ (หลาย price-line)."""
    return [r for r in db.get_catalog() if r["item_name"] == item_name]


def get_history(item_name: str, limit: int = 200) -> list[dict]:
    return db.get_history(item_name, limit=limit)


def category_counts() -> list[tuple[str, int]]:
    """จำนวน price-line ต่อหมวด สำหรับ dashboard."""
    return [(cat, len(rows)) for cat, rows in by_category()]


def summary() -> dict:
    """ตัวเลขรวมสำหรับหน้า dashboard."""
    return db.counts()


if __name__ == "__main__":
    from .config import setup_logging

    setup_logging()
    for row in get_all():
        print(row)
    print("summary:", summary())
