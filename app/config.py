"""โหลด + validate config จาก .env

ใช้ python-dotenv โหลด .env ที่ root ของโปรเจ็ค
เข้าถึงค่าผ่าน object `settings` (singleton)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# root = โฟลเดอร์ที่มี main.py (parent ของ app/)
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
RAW_DIR = DATA_DIR / "raw"   # เก็บ raw dataset จาก Apify ไว้ replay/debug

load_dotenv(ROOT_DIR / ".env")


def _split_csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


@dataclass
class Settings:
    # Apify
    apify_token: str = field(default_factory=lambda: os.getenv("APIFY_TOKEN", ""))
    actor_groups: str = field(
        default_factory=lambda: os.getenv("APIFY_ACTOR_GROUPS", "apify/facebook-groups-scraper")
    )
    actor_marketplace: str = field(
        default_factory=lambda: os.getenv(
            "APIFY_ACTOR_MARKETPLACE", "apify/facebook-marketplace-scraper"
        )
    )
    fb_group_urls: list[str] = field(
        default_factory=lambda: _split_csv(os.getenv("FB_GROUP_URLS", ""))
    )
    marketplace_search_terms: list[str] = field(
        default_factory=lambda: _split_csv(os.getenv("MARKETPLACE_SEARCH_TERMS", "RTX,Ryzen,DDR5"))
    )
    # location ฝังใน path ของ marketplace URL (เช่น "bangkok" หรือ numeric place id)
    marketplace_location: str = field(
        default_factory=lambda: os.getenv("MARKETPLACE_LOCATION", "bangkok").strip()
    )
    # ถ้าตั้งค่านี้ จะใช้ URL เต็มที่ผู้ใช้ก็อปจาก browser (location+รัศมีตามที่ตั้งไว้) แทนการ build เอง
    marketplace_search_urls: list[str] = field(
        default_factory=lambda: _split_csv(os.getenv("MARKETPLACE_SEARCH_URLS", ""))
    )
    # เปิดหน้า listing ทีละอันเพื่อเอา description/พิกัด — กิน Apify traffic เยอะมาก
    # ปิด (default) = เอาแค่ title/ราคา/จังหวัด จากหน้าค้นหา (พอ parse ได้ + ประหยัด)
    marketplace_listing_details: bool = field(
        default_factory=lambda: os.getenv("MARKETPLACE_LISTING_DETAILS", "0")
        not in ("0", "false", "False", "")
    )
    # กรองเฉพาะโพสใหม่กว่า (เช่น "14 days", "2024-01-01"); ว่าง = ไม่กรอง
    posts_newer_than: str = field(
        default_factory=lambda: os.getenv("POSTS_NEWER_THAN", "").strip()
    )
    max_posts_per_run: int = field(
        default_factory=lambda: int(os.getenv("MAX_POSTS_PER_RUN", "50"))
    )

    # Ollama
    ollama_host: str = field(
        default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    )
    # context window — ตั้งเล็กให้ KV cache เล็ก โมเดลลงครบใน VRAM (RTX 5070 = 12GB)
    # แต่ system prompt + few-shot 4 ชุด + โพสขายกำแพง กินรวม ~5-6k token
    # ถ้าเล็กกว่านั้น context ถูกตัดหัว → โมเดลหลอน/ลืมกฎ → ใช้ 8192 เป็นค่าต่ำสุดที่ปลอดภัย
    ollama_num_ctx: int = field(
        default_factory=lambda: int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    )
    # โมเดล vision สำหรับฟีเจอร์ประเมินราคาจากรูป (app/vision.py)
    # Ollama สลับโมเดลกับตัว text เองใน VRAM — ครั้งแรกหลังสลับช้ากว่าปกติหลายวินาที
    ollama_vision_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_VISION_MODEL", "qwen3-vl:8b")
    )

    # Alert
    alert_threshold: float = field(
        default_factory=lambda: float(os.getenv("ALERT_THRESHOLD", "0.85"))
    )
    location_keywords: list[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv("LOCATION_KEYWORDS", "นนทบุรี,กรุงเทพ,ปทุมธานี,สมุทรปราการ,นครปฐม")
        )
    )

    # Scheduler
    scraper_a_interval_hours: float = field(
        default_factory=lambda: float(os.getenv("SCRAPER_A_INTERVAL_HOURS", "6"))
    )
    scraper_b_interval_hours: float = field(
        default_factory=lambda: float(os.getenv("SCRAPER_B_INTERVAL_HOURS", "1"))
    )

    # Web
    flask_port: int = field(default_factory=lambda: int(os.getenv("FLASK_PORT", "5000")))

    # เก็บ raw dataset จาก Apify ไว้ replay (ปิดได้ด้วย SAVE_RAW=0)
    save_raw: bool = field(
        default_factory=lambda: os.getenv("SAVE_RAW", "1") not in ("0", "false", "False", "")
    )

    # paths
    db_path: Path = field(default_factory=lambda: DATA_DIR / "pcprice.db")
    log_path: Path = field(default_factory=lambda: LOGS_DIR / "app.log")
    raw_dir: Path = field(default_factory=lambda: RAW_DIR)

    def ensure_dirs(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DIR.mkdir(parents=True, exist_ok=True)

    def validate(self, require_apify: bool = False) -> list[str]:
        """คืน list ของปัญหา (empty = ผ่าน). ไม่ throw เพื่อให้รัน init-db ได้แม้ยังไม่เติม token."""
        problems: list[str] = []
        if require_apify and not self.apify_token:
            problems.append("APIFY_TOKEN ว่าง — เติมใน .env ก่อน scrape")
        if not (0 < self.alert_threshold <= 1):
            problems.append(f"ALERT_THRESHOLD ควรอยู่ (0,1] แต่ได้ {self.alert_threshold}")
        return problems


settings = Settings()


def _force_utf8_stdout() -> None:
    """Windows console default = cp1252 พิมพ์ภาษาไทยไม่ได้ → บังคับ UTF-8."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def setup_logging(level: int = logging.INFO) -> None:
    """ตั้ง logging ไปทั้ง console + ไฟล์ logs/app.log"""
    import sys

    _force_utf8_stdout()
    settings.ensure_dirs()
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:  # pythonw ไม่มี console — ข้าม StreamHandler
        handlers.append(logging.StreamHandler())
    try:
        handlers.append(logging.FileHandler(settings.log_path, encoding="utf-8"))
    except OSError:
        pass  # ถ้าเขียนไฟล์ไม่ได้ ใช้ console อย่างเดียว
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    # werkzeug log ทุก HTTP request — หน้า system poll log ทุก 2 วิ จะ spam ไฟล์ตัวเอง
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


if __name__ == "__main__":
    setup_logging()
    settings.ensure_dirs()
    print("ROOT_DIR :", ROOT_DIR)
    print("db_path  :", settings.db_path)
    print("ollama   :", settings.ollama_host, settings.ollama_model)
    print("threshold:", settings.alert_threshold)
    print("locations:", settings.location_keywords)
    probs = settings.validate(require_apify=True)
    print("problems :", probs or "none")
