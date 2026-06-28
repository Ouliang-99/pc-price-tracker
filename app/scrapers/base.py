"""Base scraper + pipeline ร่วม (scrape → parse → insert → alert).

แยก normalize layer ออกมาเพื่อรองรับการที่ Apify actor เปลี่ยน schema —
ถ้า field เปลี่ยน แก้แค่ method `normalize()` ของ scraper นั้น

PDPA: normalize ดึงเฉพาะ text/url/เวลา/พื้นที่ ไม่แตะ field ผู้ขาย
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apify_client import ApifyClient

from ..config import settings
from ..models import RawPost

log = logging.getLogger(__name__)

# field ที่อาจเป็นข้อมูลส่วนบุคคลของผู้ขาย/คนคอมเมนต์ — ตัดทิ้งก่อนเก็บ raw (PDPA)
_PII_FIELDS = {"user", "seller", "author", "owner", "profile", "phone",
               "phoneNumber", "contact", "email", "userId", "ownerId",
               "topComments", "comments", "commenters", "reactions"}


def _sanitize(item: dict) -> dict:
    """ลบ field ข้อมูลส่วนบุคคลของผู้ขายออกก่อนเก็บ raw."""
    return {k: v for k, v in item.items() if k not in _PII_FIELDS}


def _save_raw(source: str, items: list[dict]) -> Optional[str]:
    """เก็บ raw dataset (sanitize แล้ว) ไว้ replay/debug. คืน path หรือ None."""
    if not settings.save_raw or not items:
        return None
    settings.ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = settings.raw_dir / f"{source}_{ts}.json"
    payload = {
        "source": source,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(items),
        "items": [_sanitize(it) for it in items],
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("[%s] เก็บ raw %d รายการ → %s", source, len(items), path.name)
        return str(path)
    except OSError as e:
        log.warning("[%s] เก็บ raw ไม่สำเร็จ: %s", source, e)
        return None


@dataclass
class ScrapeResult:
    source: str
    fetched: int = 0       # โพสที่ดึงมา
    parsed: int = 0        # parse สำเร็จ
    inserted: int = 0      # ลง db ใหม่ (ไม่ซ้ำ)
    alerted: int = 0       # ยิง alert
    skipped: int = 0       # parse ไม่ได้/ซ้ำ

    def __str__(self) -> str:
        return (
            f"[{self.source}] fetched={self.fetched} parsed={self.parsed} "
            f"inserted={self.inserted} alerted={self.alerted} skipped={self.skipped}"
        )


class BaseScraper(ABC):
    source: str = ""
    actor_id: str = ""

    def __init__(self, client: Optional[ApifyClient] = None):
        self._client = client

    @property
    def client(self) -> ApifyClient:
        if self._client is None:
            if not settings.apify_token:
                raise RuntimeError("APIFY_TOKEN ว่าง — เติมใน .env ก่อน scrape")
            self._client = ApifyClient(settings.apify_token)
        return self._client

    @abstractmethod
    def build_input(self) -> dict:
        """สร้าง input payload สำหรับ actor."""

    @abstractmethod
    def normalize(self, item: dict) -> Optional[RawPost]:
        """แปลง 1 item จาก actor → RawPost (หรือ None ถ้าใช้ไม่ได้)."""

    def fetch(self) -> list[RawPost]:
        """รัน actor แล้วคืน list[RawPost]."""
        run_input = self.build_input()
        log.info("[%s] เรียก actor %s", self.source, self.actor_id)
        run = self.client.actor(self.actor_id).call(run_input=run_input)
        # apify-client 3.x คืน pydantic Run object (ไม่ใช่ dict)
        dataset_id = getattr(run, "default_dataset_id", None) if run else None
        if not dataset_id:
            log.warning("[%s] ไม่มี dataset กลับมา (run=%s)", self.source, run)
            return []

        raw_items = list(self.client.dataset(dataset_id).iterate_items())
        _save_raw(self.source, raw_items)  # เก็บ raw ไว้ replay/debug ก่อน normalize

        posts = self.normalize_many(raw_items)
        log.info("[%s] ได้ %d โพสหลัง normalize (จาก %d รายการ)",
                 self.source, len(posts), len(raw_items))
        return posts

    def normalize_many(self, raw_items: list[dict]) -> list[RawPost]:
        """normalize ทั้ง batch (ใช้ทั้งตอน fetch และตอน replay)."""
        posts: list[RawPost] = []
        for item in raw_items:
            try:
                post = self.normalize(item)
            except Exception as e:  # actor schema เปลี่ยน → กันพังทั้ง job
                log.warning("[%s] normalize ล้มเหลว: %s", self.source, e)
                post = None
            if post:
                posts.append(post)
        return posts


def _extract_first(item: dict, keys: list[str]) -> Optional[str]:
    """หา value แรกที่ไม่ว่างจาก key หลายแบบ (รองรับ schema ต่างกัน)."""
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _process_posts(posts: list[RawPost], source: str) -> ScrapeResult:
    """parse → insert → alert สำหรับ RawPost ที่ normalize แล้ว."""
    from .. import alerts as alerts_mod
    from .. import db
    from ..parser import parse_post

    result = ScrapeResult(source=source)
    result.fetched = len(posts)
    for post in posts:
        items = parse_post(post)
        if not items:
            result.skipped += 1
            continue
        
        for item in items:
            result.parsed += 1
            if not db.insert_price(item.to_row()):
                result.skipped += 1
                continue
            result.inserted += 1

            if alerts_mod.maybe_alert(item):
                result.alerted += 1
    log.info("pipeline เสร็จ: %s", result)
    return result


def run_pipeline(scraper: BaseScraper) -> ScrapeResult:
    """scrape → parse → insert → alert. แยกจาก fetch เพื่อ test ได้ง่าย."""
    posts = scraper.fetch()
    return _process_posts(posts, scraper.source)


def replay_raw(path: str) -> ScrapeResult:
    """อ่าน raw file ที่เก็บไว้ → normalize → parse → insert (ไม่เรียก Apify).

    ใช้ debug ตอน normalize/parser มีปัญหา โดยไม่เปลือง credits
    """
    from .groups import GroupsScraper
    from .marketplace import MarketplaceScraper

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    source = data.get("source", "")
    items = data.get("items", [])
    scraper = {"groups": GroupsScraper, "marketplace": MarketplaceScraper}.get(source)
    if scraper is None:
        raise ValueError(f"ไม่รู้จัก source ใน raw file: {source!r}")

    log.info("replay %d รายการจาก %s (source=%s)", len(items), path, source)
    posts = scraper().normalize_many(items)
    log.info("normalize ได้ %d/%d", len(posts), len(items))
    return _process_posts(posts, source)
