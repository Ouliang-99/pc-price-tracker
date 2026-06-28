# PC Price Tracker — Tasks

สถานะ: `[ ]` ยังไม่ทำ · `[~]` กำลังทำ · `[x]` เสร็จ · `[!]` ติด/รอ

อัปเดตล่าสุด: 2026-06-10

---

## Phase 0 — Scaffold & Docs
- [x] สร้างโครงโฟลเดอร์
- [x] PLAN.md
- [x] TASKS.md
- [x] ARCHITECTURE.md
- [x] SETUP.md
- [x] requirements.txt
- [x] .env.example
- [x] .gitignore
- [x] README.md

## Phase 1 — Config & DB
- [x] `app/config.py` — โหลด .env, validate, ค่า default
- [x] `app/models.py` — dataclass RawPost / ParsedItem (ไม่มี field PDPA)
- [x] `app/db.py` — connection, schema (price_history, alert_log), migrations
- [x] `item_catalog` เป็น SQL VIEW (auto-computed avg/min/max/median/count)
- [x] helper: insert_price (dedupe source_url), query catalog/history/alerts
- [x] รัน `python -m app.db` แล้วสร้างไฟล์ db + ตารางได้ ✔ ทดสอบแล้ว
- [x] median view ตรงกับ `statistics.median` ✔ verify ทุกสินค้า

## Phase 2 — AI Parser
- [x] `app/parser.py` — เรียก Ollama `/api/chat` format=json
- [x] prompt ภาษาไทย + few-shot, บังคับ output schema
- [x] map หมวด (GPU/CPU/RAM/...) + normalize ราคา (ตัด "บาท", คอมมา)
- [x] parse ไม่ได้ → return None + log warning (ไม่ throw)
- [x] `health_check()` เช็ค Ollama + model
- [x] ทดสอบกับโพสจริง 7 อัน ✔ 7/7 ถูก (ขาย 4 + skip รับซื้อ/ไม่มีราคา/ยกชุด 3)

## Phase 3 — Scrapers
- [x] `app/scrapers/base.py` — BaseScraper + RawPost + run_pipeline
- [x] `app/scrapers/groups.py` — Apify `apify/facebook-groups-scraper`
- [x] `app/scrapers/marketplace.py` — Apify `apify/facebook-marketplace-scraper`
- [x] normalize ผล actor → RawPost (กรอง field PDPA ออก, defensive multi-key)
- [x] pipeline: scrape → parse → insert → alert (ต่อ scraper)
- [x] แก้ apify-client 3.x: Run เป็น pydantic object ใช้ `.default_dataset_id`
- [x] groups.py: เพิ่ม viewOption + onlyPostsNewerThan
- [x] marketplace.py: รื้อ build_input ให้ตรง schema จริง (location ฝังใน URL)
- [x] **ทดสอบ Apify จริงผ่าน** ✔ groups scrape 50 โพส → parse 22 → ลง db 22
- [x] ยืนยัน field จริงตรงกับ normalize() + PDPA (ไม่ดึง field `user`/ชื่อผู้ขาย)

## Phase 4 — Catalog & Alerts
- [x] `app/catalog.py` — อ่าน stats จาก view, helper avg ต่อ item
- [x] `app/alerts.py` — logic: price < ALERT_THRESHOLD × avg ✔ verify
- [x] flag "รับมือได้" ตาม LOCATION_KEYWORDS ✔ verify
- [x] เขียน alert_log + ส่ง toast (plyer)
- [x] กันเตือนซ้ำ (source_url เดิม) ✔ verify
- [x] กัน alert จาก sample น้อย (MIN_SAMPLES_FOR_ALERT=3)

## Phase 5 — Scheduler
- [x] `app/scheduler.py` — APScheduler BackgroundScheduler (tz Asia/Bangkok)
- [x] job A: Groups ทุก SCRAPER_A_INTERVAL_HOURS
- [x] job B: Marketplace ทุก SCRAPER_B_INTERVAL_HOURS
- [x] error handling ต่อ job (try/except, job ตายไม่ล้ม process)
- [x] run_now option ยิงครั้งแรกหลัง start

## Phase 6 — Web UI
- [x] `app/web/__init__.py` — Flask app factory
- [x] `app/web/routes.py` — /, /catalog, /item/<name>, /alerts, /api/*
- [x] templates: dashboard, catalog (+filter), item (SVG chart), alerts
- [x] mark alert read (AJAX)
- [x] manual "scrape now" button → trigger
- [x] ทุก route ตอบ 200 ✔ ทดสอบด้วย mock data

## Phase 7 — Tray & main.py
- [x] `app/tray.py` — pystray icon + เมนู (Open / Scrape / Quit)
- [x] `app/triggers.py` — manual scrape ใช้ร่วม tray/web/CLI
- [x] `main.py` — Flask thread + scheduler + tray + auto-open browser
- [x] graceful shutdown + fallback headless ถ้าไม่มี GUI

## Phase 8 — Polish
- [x] `run.py` CLI: init-db / parse-test / scrape-once / serve / stats / seed-mock
- [x] `seed-mock` ใส่ข้อมูลตัวอย่าง (ลองเว็บได้ไม่ต้องมี Apify/Ollama)
- [x] เติม README + SETUP วิธีรัน
- [x] ทดสอบ end-to-end ด้วย mock data ✔
- [x] แก้ UTF-8 stdout (Windows console ภาษาไทย)
- [ ] ngrok helper (optional, สำหรับมือถือ) — ค้างไว้ ทำเมื่อต้องใช้มือถือ

---

## External setup
- [x] ติดตั้ง Ollama 0.30.6 + `qwen2.5:14b` (9.0 GB) → ✔ ทดสอบ parser จริงผ่าน
- [x] สร้าง `.env` (actor IDs / search terms / location ตั้งครบ)
- [x] เติม `APIFY_TOKEN` + `FB_GROUP_URLS` → ✔ scrape จริงผ่าน (groups)
- [x] ตั้ง `MARKETPLACE_LOCATION` = place id ปากเกร็ด/นนทบุรี
- [x] ทดสอบ marketplace scrape จริง → field ต่างจาก groups, แก้ normalize → 228/228 ✔
- [ ] รัน `python main.py` เต็มระบบ (tray + scheduler + web) ครั้งแรก

## Phase 10 — GPU performance fix
- [x] เจอ: qwen2.5:14b + ctx 32k = 15GB > VRAM 12GB → แบ่ง 34% ไป CPU (ช้า, GPU 18%)
- [x] เพิ่ม `OLLAMA_NUM_CTX=4096` → KV cache เล็ก → 9.5GB ลงครบ → **100% GPU**
- [x] ยืนยัน `ollama ps` = `9.5 GB · 100% GPU` + note ใน SETUP.md

## Phase 11 — Taxonomy (แยกหมวด → รุ่น → variant)
- [x] models: เพิ่ม brand / form_factor / variant ใน ParsedItem
- [x] parser: prompt + 2 few-shot ใหม่ (แยกยี่ห้อ/พัดลม/SO-DIMM) + normalize
- [x] db: เพิ่ม column + migration (ALTER) + view group by (รุ่น+form_factor+variant)
- [x] catalog.py: by_category(), get_item_variants(), category_counts()
- [x] web: catalog จัดกลุ่มตามหมวด + nav, item แสดง variant breakdown, dashboard chips
- [x] ทดสอบ parser: "ASUS RTX 4070 Super 3 พัดลม" → brand=ASUS, variant=3 พัดลม ✔
- [ ] re-replay marketplace ด้วย parser ใหม่ (กำลังรัน) → ดูผลจริง

## Phase 9 — Raw data persistence (เพิ่มตามคำขอ)
- [x] เก็บ raw dataset จาก Apify → `data/raw/{source}_{ts}.json` (ทุกครั้งที่ fetch)
- [x] sanitize PII ก่อนเก็บ (ตัด user/seller/topComments ฯลฯ) — ยืนยันแล้ว
- [x] `run.py replay <file>` — re-run pipeline จาก raw (ไม่เปลือง credits)
- [x] `run.py list-raw` — ดู raw files
- [x] `SAVE_RAW=0` ปิดได้ + `data/raw/` gitignored
- [ ] (optional) replay marketplace_*.json (228 รายการ) เพื่อโหลดข้อมูล marketplace
