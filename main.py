"""Entrypoint — รัน 4 อย่างพร้อมกัน:
  1. Flask server (thread แยก)
  2. APScheduler background jobs
  3. System tray icon (main thread)
  4. เปิด browser อัตโนมัติ
"""
from __future__ import annotations

import logging
import threading
import time
import webbrowser

from app import triggers
from app.config import settings, setup_logging
from app.db import init_db
from app.parser import health_check
from app.scheduler import build_scheduler
from app.tray import run_tray
from app.web import create_app

log = logging.getLogger(__name__)


def _start_flask() -> None:
    app = create_app(scrape_trigger=triggers.scrape)
    # debug=False, ปิด reloader (จะ spawn process ซ้ำ)
    # threaded=True จำเป็น: /api/estimate ใช้เวลาเป็นนาที ถ้า single-thread ทั้งเว็บจะค้างตาม
    app.run(host="127.0.0.1", port=settings.flask_port, debug=False,
            use_reloader=False, threaded=True)


def main() -> None:
    setup_logging()
    settings.ensure_dirs()

    problems = settings.validate(require_apify=False)
    for p in problems:
        log.warning("config: %s", p)
    if not settings.apify_token:
        log.warning("APIFY_TOKEN ว่าง — scheduler จะรันแต่ scrape จะ error จนกว่าจะเติม .env")

    # 0. database
    init_db()

    # ตรวจ Ollama (ไม่บล็อค ถ้าไม่พร้อมแค่เตือน)
    if not health_check():
        log.warning("Ollama ยังไม่พร้อม (%s / %s) — parser จะ skip โพสจนกว่าจะออนไลน์",
                    settings.ollama_host, settings.ollama_model)

    # 1. Flask (daemon thread)
    threading.Thread(target=_start_flask, daemon=True, name="flask").start()
    log.info("Flask: http://localhost:%d", settings.flask_port)

    # 2. scheduler
    scheduler = build_scheduler(run_now=bool(settings.apify_token))
    scheduler.start()
    for job in scheduler.get_jobs():
        log.info("job %s → next: %s", job.id, job.next_run_time)

    # 4. เปิด browser (รอ Flask ตื่นก่อนนิดนึง)
    def _open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{settings.flask_port}")

    threading.Thread(target=_open_browser, daemon=True).start()

    # 3. tray (บล็อค main thread จนกว่าจะ Quit)
    def _on_quit():
        log.info("กำลังปิด...")
        scheduler.shutdown(wait=False)

    try:
        run_tray(scrape_trigger=triggers.scrape, on_quit=_on_quit)
    except Exception as e:
        # ถ้าไม่มี GUI/tray ใช้ไม่ได้ → fallback รันค้างไว้ด้วย scheduler อย่างเดียว
        log.warning("tray ใช้ไม่ได้ (%s) — รันแบบ headless, Ctrl+C เพื่อหยุด", e)
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
