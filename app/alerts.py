"""Alert logic + notification.

เงื่อนไข: ราคาของโพส < ALERT_THRESHOLD × avg ของกลุ่มเดียวกับ item_catalog
(item_name + form_factor + capacity + speed) — ไม่เทียบข้าม spec
- ต้องมี sample ในกลุ่มอย่างน้อย MIN_SAMPLES_FOR_ALERT ถึงจะเทียบได้
- กันเตือนซ้ำด้วย source_url
- flag local_pickup ("รับมือได้") ถ้า location ตรง LOCATION_KEYWORDS
- ส่ง Windows toast ด้วย plyer (พังเงียบได้ถ้า notification ใช้ไม่ได้)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import db
from .config import settings
from .models import ParsedItem

log = logging.getLogger(__name__)

# ต้องมีอย่างน้อยกี่ sample ถึงจะเชื่อ avg (กัน alert จาก sample เดียว)
MIN_SAMPLES_FOR_ALERT = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_local(location: str) -> bool:
    """โพสอยู่ในพื้นที่รับเองได้ไหม."""
    if not location:
        return False
    return any(kw in location for kw in settings.location_keywords)


def send_toast(title: str, message: str) -> None:
    """ส่ง Windows notification (พังเงียบถ้าใช้ไม่ได้ เช่นไม่มี GUI)."""
    try:
        from plyer import notification

        notification.notify(title=title, message=message, app_name="PC Price Tracker", timeout=10)
    except Exception as e:  # plyer มีปัญหาได้หลายแบบบน headless
        log.warning("ส่ง toast ไม่สำเร็จ: %s", e)


def maybe_alert(item: ParsedItem) -> bool:
    """ตรวจ + ยิง alert ถ้าเข้าเงื่อนไข. คืน True ถ้ายิง."""
    if db.already_alerted(item.source_url):
        return False

    stats = db.get_price_stats(item.item_name, item.form_factor, item.capacity, item.speed)
    if stats is None:
        return False
    avg, sample_count = stats
    if sample_count < MIN_SAMPLES_FOR_ALERT:
        return False

    threshold_price = settings.alert_threshold * avg
    if item.price >= threshold_price:
        return False

    discount_pct = round((1 - item.price / avg) * 100, 1)
    local = is_local(item.location)

    db.insert_alert(
        {
            "item_name": item.item_name,
            "price": item.price,
            "avg_at_time": round(avg, 2),
            "discount_pct": discount_pct,
            "location": item.location,
            "source_url": item.source_url,
            "local_pickup": 1 if local else 0,
            "alerted_at": _now_iso(),
        }
    )

    tag = " 🏠รับมือได้" if local else ""
    title = f"💸 {item.item_name} ถูกกว่าตลาด {discount_pct}%"
    message = (
        f"{item.price:,} บาท (avg {avg:,.0f}) · {item.location}{tag}\n{item.source_url}"
    )
    send_toast(title, message)
    log.info("ALERT: %s @ %d (-%.1f%%)%s", item.item_name, item.price, discount_pct, tag)
    return True


if __name__ == "__main__":
    from .config import setup_logging

    setup_logging()
    send_toast("PC Price Tracker", "ทดสอบ notification ✅")
    print("ส่ง test toast แล้ว")
