"""CLI utility — งานย่อยสำหรับ dev/ทดสอบ (ไม่ต้องเปิด tray/Flask เต็ม).

ตัวอย่าง:
  python run.py init-db
  python run.py parse-test "ขาย RTX 4070 Super มือสอง 8500 ต่อรองได้ นนทบุรี"
  python run.py scrape-once --source groups
  python run.py serve
  python run.py stats
  python run.py seed-mock        # ใส่ข้อมูลตัวอย่างไว้ลองหน้าเว็บ (ไม่ต้องมี Apify/Ollama)
"""
from __future__ import annotations

import argparse
import logging

from app.config import settings, setup_logging

log = logging.getLogger(__name__)


def cmd_init_db(args):
    from app.db import init_db

    init_db()
    print("init-db เสร็จ →", settings.db_path)


def cmd_reset_db(args):
    from app.db import counts, reset_db

    before = counts()
    reset_db()
    print(f"reset-db เสร็จ: ลบ {before['price_history']} โพส + {before['alerts']} alert →",
          settings.db_path)


def cmd_parse_test(args):
    from app.models import RawPost
    from app.parser import health_check, parse_post

    print("Ollama online:", health_check())
    post = RawPost(text=args.text, source="cli", source_url="cli://test")
    print(parse_post(post))


def cmd_scrape_once(args):
    from app import triggers

    result = triggers.scrape(args.source)
    print(result or "ไม่สำเร็จ (ดู log)")


def cmd_serve(args):
    from app import triggers
    from app.web import create_app

    create_app(scrape_trigger=triggers.scrape).run(
        host="127.0.0.1", port=settings.flask_port, debug=args.debug
    )


def cmd_stats(args):
    from app.db import counts

    print(counts())


def cmd_replay(args):
    """re-run pipeline จาก raw file ที่เก็บไว้ (ไม่เรียก Apify).

    ไม่ระบุ path = replay ทุกไฟล์ใน data/raw/ (ใช้หลังปรับ parser/taxonomy)
    """
    from app.scrapers import replay_raw

    if args.path:
        print(replay_raw(args.path))
        return
    files = sorted(settings.raw_dir.glob("*.json")) if settings.raw_dir.exists() else []
    if not files:
        print("ยังไม่มี raw file ใน", settings.raw_dir)
        return
    for f in files:
        print(f"--- replay {f.name} ---")
        try:
            print(replay_raw(str(f)))
        except Exception as e:  # ไฟล์เสียไฟล์เดียวไม่ควรหยุดทั้งชุด
            log.warning("replay %s ล้มเหลว: %s", f.name, e)


def cmd_list_raw(args):
    """ดู raw files ที่เก็บไว้."""
    from app.config import settings

    if not settings.raw_dir.exists():
        print("ยังไม่มี raw file")
        return
    files = sorted(settings.raw_dir.glob("*.json"), reverse=True)
    if not files:
        print("ยังไม่มี raw file ใน", settings.raw_dir)
        return
    for f in files:
        print(f"{f.name:40} {f.stat().st_size // 1024:>6} KB")


def cmd_seed_mock(args):
    """ใส่ข้อมูลตัวอย่างเพื่อลองหน้าเว็บ (ไม่ต้องมี Apify/Ollama)."""
    import random
    from datetime import datetime, timedelta, timezone

    from app.db import init_db, insert_price
    from app.models import ParsedItem

    init_db()
    base = {
        "RTX 4070 Super": ("GPU", 18000),
        "RTX 4060 Ti": ("GPU", 12000),
        "Ryzen 5 7600": ("CPU", 7000),
        "Ryzen 7 7800X3D": ("CPU", 13000),
        "DDR5 32GB 6000": ("RAM", 3200),
        "Samsung 990 Pro 2TB": ("SSD", 5200),
    }
    locs = ["นนทบุรี", "กรุงเทพ", "ปทุมธานี", "เชียงใหม่", "ขอนแก่น", "ชลบุรี"]
    n = 0
    for name, (cat, mid) in base.items():
        for i in range(random.randint(6, 12)):
            price = int(mid * random.uniform(0.78, 1.15))
            at = (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 40))).isoformat(
                timespec="seconds"
            )
            item = ParsedItem(
                item_name=name,
                category=cat,
                price=price,
                condition=random.choice(["มือสอง", "มือหนึ่ง", "ประกันศูนย์"]),
                negotiable=random.random() < 0.5,
                location=random.choice(locs),
                source=random.choice(["groups", "marketplace"]),
                source_url=f"mock://{name}/{i}".replace(" ", "_"),
                posted_at=at,
                scraped_at=at,
            )
            if insert_price(item.to_row()):
                n += 1
    print(f"seed-mock: ใส่ {n} โพส แล้วลองเปิด `python run.py serve`")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PC Price Tracker CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    sub.add_parser("reset-db", help="ล้างข้อมูลทั้งหมด (price_history + alert_log)").set_defaults(
        func=cmd_reset_db
    )

    pt = sub.add_parser("parse-test")
    pt.add_argument("text")
    pt.set_defaults(func=cmd_parse_test)

    so = sub.add_parser("scrape-once")
    so.add_argument("--source", choices=["groups", "marketplace"], default="groups")
    so.set_defaults(func=cmd_scrape_once)

    sv = sub.add_parser("serve")
    sv.add_argument("--debug", action="store_true")
    sv.set_defaults(func=cmd_serve)

    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("seed-mock").set_defaults(func=cmd_seed_mock)

    rp = sub.add_parser("replay", help="re-run pipeline จาก raw file (ไม่เรียก Apify)")
    rp.add_argument("path", nargs="?", default=None,
                    help="path ของ raw json ใน data/raw/ (ไม่ระบุ = ทุกไฟล์)")
    rp.set_defaults(func=cmd_replay)

    sub.add_parser("list-raw", help="ดู raw files ที่เก็บไว้").set_defaults(func=cmd_list_raw)
    return p


def main():
    setup_logging()
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
