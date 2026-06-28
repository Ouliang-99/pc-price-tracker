"""Scraper B — Facebook Marketplace (apify/facebook-marketplace-scraper).

รันทุก SCRAPER_B_INTERVAL_HOURS (default 1 ชม.) เทียบกับ avg รวม
Marketplace actor มักให้ราคา/พื้นที่มาแล้ว → ใช้เป็น hint
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote

from ..config import settings
from ..models import RawPost
from .base import BaseScraper, _extract_first

log = logging.getLogger(__name__)


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    # ตัดทศนิยมก่อน (เช่น "6500.00") แล้วเก็บเฉพาะตัวเลข
    s = str(value).split(".")[0]
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else None


def _dig_text(value) -> str:
    """marketplace ห่อ string ไว้ใน {'text': ...} บ่อย — ดึงออกมาให้เป็น str."""
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


class MarketplaceScraper(BaseScraper):
    source = "marketplace"

    def __init__(self, client=None):
        super().__init__(client)
        self.actor_id = settings.actor_marketplace

    def build_input(self) -> dict:
        # actor รับ location ผ่าน path ของ marketplace URL ไม่ใช่ param แยก
        # โหมด 1: ผู้ใช้ใส่ URL เต็มเอง (location+รัศมีตามที่ตั้งใน browser)
        if settings.marketplace_search_urls:
            urls = settings.marketplace_search_urls
        # โหมด 2: build จาก location + คำค้น
        else:
            loc = quote(settings.marketplace_location, safe="")
            urls = [
                f"https://www.facebook.com/marketplace/{loc}/search?query={quote(term)}"
                for term in settings.marketplace_search_terms
            ]
        return {
            "startUrls": [{"url": u} for u in urls],
            "resultsLimit": settings.max_posts_per_run,
            # True = เปิดทุก listing (กิน traffic เยอะ); default False ประหยัดกว่ามาก
            "includeListingDetails": settings.marketplace_listing_details,
        }

    def normalize(self, item: dict) -> Optional[RawPost]:
        # ข้ามของที่ขายไปแล้ว/ซ่อน
        if item.get("isSold") in (True, "True") or item.get("isHidden") in (True, "True"):
            return None

        # title + description (description เป็น dict {'text': ...})
        title = _extract_first(item, ["listingTitle", "title", "marketplaceTitle", "name"]) or ""
        desc = _dig_text(item.get("description"))
        text = (title + "\n" + desc).strip()

        # ต้องใช้ itemUrl (ลิงก์ listing จริง) ไม่ใช่ facebookUrl (URL ค้นหา → ซ้ำกันหมด)
        url = _extract_first(item, ["itemUrl", "listingUrl", "url"])
        if not text or not url:
            return None

        # listingPrice เป็น dict {'amount': '6500.00', ...}
        price = item.get("listingPrice")
        price_hint = None
        if isinstance(price, dict):
            price_hint = _to_int(price.get("amount") or price.get("amount_with_offset_in_currency"))
        else:
            price_hint = _to_int(price)

        # locationText เป็น dict {'text': 'กรุงเทพมหานคร, ประเทศไทย'}
        location = _dig_text(item.get("locationText")) or None
        posted_at = _extract_first(item, ["timestamp", "creationTime", "time", "date"])

        return RawPost(
            text=text,
            source=self.source,
            source_url=url,
            posted_at=posted_at,
            price_hint=price_hint,
            location_hint=location,
        )


if __name__ == "__main__":
    from ..config import setup_logging
    from .base import run_pipeline

    setup_logging()
    print(run_pipeline(MarketplaceScraper()))
