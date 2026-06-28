"""Flask routes — dashboard, catalog, item detail, alerts, API."""
from __future__ import annotations

import logging
import threading

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .. import catalog as catalog_mod
from .. import db

log = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


@bp.route("/")
def dashboard():
    return render_template(
        "dashboard.html",
        summary=catalog_mod.summary(),
        category_counts=catalog_mod.category_counts(),
        top_items=catalog_mod.get_all()[:8],
        recent_alerts=db.get_alerts(limit=8),
    )


@bp.route("/catalog")
def catalog():
    return render_template("catalog.html", groups=catalog_mod.by_category())


@bp.route("/item/<path:item_name>")
def item(item_name: str):
    variants = catalog_mod.get_item_variants(item_name)
    if not variants:
        abort(404)
    history = catalog_mod.get_history(item_name, limit=200)
    # จุดสำหรับกราฟ sparkline (ราคาเรียงเก่า→ใหม่)
    points = [
        {"price": h["price"], "at": h["posted_at"] or h["scraped_at"]}
        for h in reversed(history)
    ]
    # สรุประดับรุ่น (รวมทุก variant)
    prices = [h["price"] for h in history]
    overall = {
        "item_name": item_name,
        "category": variants[0]["category"],
        "avg_price": round(sum(prices) / len(prices)) if prices else 0,
        "min_price": min(prices) if prices else 0,
        "max_price": max(prices) if prices else 0,
        "sample_count": len(prices),
    }
    from ..taxonomy import MODELS_TAXONOMY
    return render_template(
        "item.html", overall=overall, variants=variants, history=history, points=points, taxonomy=MODELS_TAXONOMY
    )

@bp.route("/estimate")
def estimate():
    return render_template("estimate.html")


@bp.route("/system")
def system():
    return render_template("system.html")


@bp.route("/alerts")
def alerts():
    return render_template(
        "alerts.html",
        alerts=db.get_alerts(limit=200),
        unread=db.counts()["unread"],
    )


# --- API ------------------------------------------------------------------

@bp.route("/api/history/<int:history_id>/edit", methods=["POST"])
def api_edit_history(history_id: int):
    data = request.json if request.is_json else request.form
    from ..taxonomy import MODELS_TAXONOMY
    
    updates = {}
    item_name = data.get("item_name")
    if item_name:
        updates["item_name"] = item_name
        for cat, models in MODELS_TAXONOMY.items():
            if any(m["standard"] == item_name for m in models):
                updates["category"] = cat
                break
                
    for col in ["capacity", "speed", "form_factor"]:
        if col in data:
            updates[col] = data[col].strip() or "ไม่ระบุ"
            
    if updates:
        db.update_price_history(history_id, updates)
        
    return jsonify({"ok": True})


@bp.route("/api/alerts/<int:alert_id>/read", methods=["POST"])
def api_mark_read(alert_id: int):
    db.mark_alert_read(alert_id)
    return jsonify({"ok": True})

import os
import subprocess
import sys
import time
from pathlib import Path


@bp.route("/api/system/restart", methods=["POST"])
def api_system_restart():
    """รีสตาร์ท process ทั้งตัว (Flask + scheduler + tray) ด้วยคำสั่งเดิมที่ใช้ตอนสตาร์ท."""
    from ..config import ROOT_DIR

    script = Path(sys.argv[0]).resolve()
    cmd = [sys.executable, str(script)] + sys.argv[1:]

    def _do_restart():
        time.sleep(0.8)  # ให้ response ส่งถึง browser ก่อนตาย
        log.info("รีสตาร์ทเซิร์ฟเวอร์: %s", " ".join(cmd))
        # DETACHED: process ใหม่ไม่ผูกกับ console เดิม (ไม่ตายตามตอนเราออก)
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        # process ใหม่ใช้เวลา import python/flask >1s กว่าจะ bind port
        # ส่วนเราตายทันทีหลัง spawn → port 5000 ว่างก่อนแน่นอน
        subprocess.Popen(cmd, cwd=str(ROOT_DIR), creationflags=flags, close_fds=True)
        os._exit(0)  # ออกแรงๆ ข้าม tray/scheduler cleanup (เดี๋ยว process ใหม่สร้างเองหมด)

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True, "message": "กำลังรีสตาร์ท... (รอประมาณ 5-10 วินาที)"})


@bp.route("/api/system/run/<command>", methods=["POST"])
def api_system_run(command):
    if command not in ["scrape", "replay", "init-db", "reset-db"]:
        return jsonify({"error": "Invalid command"}), 400

    if command == "reset-db":
        # รันตรงๆ ใน process นี้เลย — เร็วและได้ผลลัพธ์ confirm กลับทันที
        before = db.counts()
        db.reset_db()
        return jsonify({"ok": True,
                        "message": f"ล้างฐานข้อมูลแล้ว (ลบ {before['price_history']} โพส, "
                                   f"{before['alerts']} alert)"})

    from ..config import ROOT_DIR

    # run.py ไม่มี subcommand ชื่อ scrape — ของจริงคือ scrape-once
    run_args = ["scrape-once"] if command == "scrape" else [command]
    subprocess.Popen([sys.executable, "run.py", *run_args], cwd=str(ROOT_DIR))
    return jsonify({"ok": True, "message": f"เริ่มคำสั่ง {command} แล้ว (ทำงานเบื้องหลัง)"})

@bp.route("/api/system/health")
def api_system_health():
    from ..parser import health_check
    ok = health_check()
    return jsonify({"ok": ok, "status": "Online" if ok else "Offline / Error"})

@bp.route("/api/system/logs")
def api_system_logs():
    from ..config import settings
    log_file = settings.log_path
    if not log_file.exists():
        return jsonify({"logs": "ยังไม่มีไฟล์ Log (รอการทำงานครั้งแรก)"})
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return jsonify({"logs": "".join(lines[-200:])})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {e}"})


@bp.route("/api/scrape", methods=["POST"])
def api_scrape():
    source = request.json.get("source") if request.is_json else request.form.get("source")
    source = source or "groups"
    trigger = current_app.config.get("scrape_trigger")
    if trigger is None:
        return jsonify({"ok": False, "error": "scrape trigger ไม่พร้อม"}), 503
    # รันใน thread แยกไม่ให้ request ค้าง
    threading.Thread(target=trigger, args=(source,), daemon=True).start()
    return jsonify({"ok": True, "source": source, "message": "เริ่ม scrape แล้ว (ดูผลใน log)"})


# magic bytes ของไฟล์รูปที่ Ollama รับ — กันอัปโหลดไฟล์มั่ว/ไฟล์อันตราย
_IMAGE_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"RIFF")  # png, jpeg, webp
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


@bp.route("/api/estimate", methods=["POST"])
def api_estimate():
    """รับรูปโพสต์ขายคอม → รายการชิ้นส่วน + ช่วงราคาจาก price_history.

    ใช้เวลา ~30-90 วินาที (โมเดล vision + อาจต้องสลับโมเดลใน VRAM ก่อน)
    """
    f = request.files.get("image")
    if f is None:
        return jsonify({"ok": False, "error": "ไม่พบไฟล์รูป (field ชื่อ image)"}), 400
    data = f.read()
    if len(data) > _MAX_IMAGE_BYTES:
        return jsonify({"ok": False, "error": "ไฟล์ใหญ่เกิน 10MB"}), 400
    if not data.startswith(_IMAGE_MAGIC):
        return jsonify({"ok": False, "error": "รองรับเฉพาะ PNG / JPEG / WebP"}), 400

    from ..vision import estimate_from_image

    result = estimate_from_image(data)
    if result is None:
        return jsonify({"ok": False,
                        "error": "อ่านรูปไม่สำเร็จ — เช็คว่า Ollama รันอยู่และมีโมเดล vision"}), 502
    result["ok"] = True
    return jsonify(result)


@bp.route("/api/summary")
def api_summary():
    return jsonify(catalog_mod.summary())


@bp.app_template_filter("baht")
def baht(value) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "-"
