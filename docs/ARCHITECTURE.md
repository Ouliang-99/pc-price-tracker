# Architecture

อัปเดตล่าสุด: 2026-06-10

## โครงไฟล์

```
pc-price-tracker/
├── main.py                  # entrypoint — รัน 4 อย่างพร้อมกัน
├── run.py                   # CLI: init-db / scrape-once / parse-test
├── requirements.txt
├── .env.example             # คัดลอกเป็น .env แล้วเติมค่า
├── .gitignore
├── README.md
├── data/
│   └── pcprice.db           # SQLite (gitignored)
├── logs/
│   └── app.log              # (gitignored)
├── docs/
│   ├── PLAN.md
│   ├── TASKS.md
│   ├── ARCHITECTURE.md
│   └── SETUP.md
└── app/
    ├── __init__.py
    ├── config.py            # โหลด/validate .env
    ├── db.py                # schema + CRUD helpers
    ├── models.py            # dataclasses: RawPost, ParsedItem
    ├── parser.py            # Ollama parser (ไทย → JSON)
    ├── catalog.py           # stats ต่อสินค้า
    ├── alerts.py            # alert logic + notification
    ├── scheduler.py         # APScheduler jobs
    ├── tray.py              # pystray system tray
    ├── scrapers/
    │   ├── __init__.py
    │   ├── base.py          # interface + pipeline ร่วม
    │   ├── groups.py        # Apify groups scraper
    │   └── marketplace.py   # Apify marketplace scraper
    └── web/
        ├── __init__.py      # Flask app factory
        ├── routes.py
        ├── templates/
        └── static/
```

## Database Schema

### `price_history` (ตารางหลัก เก็บทุกโพส)
| column | type | หมายเหตุ |
|--------|------|---------|
| id | INTEGER PK | |
| item_name | TEXT | ชื่อ normalize เช่น "RTX 4070 Super" |
| category | TEXT | GPU / CPU / RAM / MB / PSU / SSD / ... |
| price | INTEGER | บาท |
| condition | TEXT | มือสอง / มือหนึ่ง / ... |
| location | TEXT | จังหวัด |
| source | TEXT | groups / marketplace |
| source_url | TEXT UNIQUE | ลิงก์โพส (ใช้ dedupe) |
| negotiable | INTEGER | 0/1 |
| posted_at | TEXT | ISO timestamp จากโพส (ถ้ามี) |
| scraped_at | TEXT | ISO timestamp ตอน scrape |

> **PDPA:** ไม่มี column ชื่อ/เบอร์/ที่อยู่/profile ของผู้ขาย

### `item_catalog` — **SQL VIEW** (auto-computed)
คำนวณ on-the-fly จาก `price_history` ไม่ต้อง maintain เอง:
`item_name, category, avg_price, min_price, max_price, median_price, sample_count, last_updated`

### `alert_log`
| column | type |
|--------|------|
| id | INTEGER PK |
| item_name | TEXT |
| price | INTEGER |
| avg_at_time | REAL |
| discount_pct | REAL |
| location | TEXT |
| source_url | TEXT |
| local_pickup | INTEGER (flag "รับมือได้") |
| alerted_at | TEXT |
| is_read | INTEGER default 0 |

## Data Flow

```
┌─────────────┐   raw      ┌──────────┐  ParsedItem  ┌──────────────┐
│ Apify actor │ ─────────▶ │  parser  │ ───────────▶ │ price_history │
│ (A: groups) │   posts    │ (Ollama) │              └──────┬───────┘
│ (B: market) │            └──────────┘                     │ recompute
└─────────────┘                                             ▼
                                                     ┌──────────────┐
                                                     │ item_catalog │ (view)
                                                     └──────┬───────┘
                                          price < th×avg ?  │
                                                            ▼
                                              ┌───────────────────────┐
                                              │ alert_log + toast(plyer)│
                                              └───────────────────────┘
```

## Alert Logic

- **Scraper A (Groups)** — ทุก 6 ชม.
  - เก็บ `price_history` ทุกโพส
  - alert ถ้า `price < ALERT_THRESHOLD × avg` (default 0.85)
  - flag `local_pickup` ถ้า location ตรง `LOCATION_KEYWORDS`
- **Scraper B (Marketplace)** — ทุก 1 ชม.
  - เทียบกับ avg (รวมจาก Groups + Marketplace)
  - alert ด้วย threshold เดียวกัน
- กันเตือนซ้ำ: ถ้า `source_url` มีใน `alert_log` แล้ว ข้าม

## Raw data persistence (debug/replay)

ทุกครั้งที่ scrape สำเร็จ จะเก็บ raw dataset จาก Apify ไว้ที่
`data/raw/{source}_{YYYYMMDD_HHMMSS}.json` (gitignored) **ก่อน** normalize

- **PDPA:** ตัด field ข้อมูลส่วนบุคคลก่อนเก็บ (`user`, `seller`, `topComments`, ฯลฯ — ดู `_PII_FIELDS` ใน [base.py](../app/scrapers/base.py))
- ใช้ debug ตอน normalize/parser มีปัญหา โดยไม่ต้อง scrape ใหม่ (ไม่เปลือง Apify credits)
- `python run.py list-raw` — ดูไฟล์ที่เก็บ
- `python run.py replay data/raw/<file>.json` — re-run pipeline จาก raw
- ปิดการเก็บด้วย `SAVE_RAW=0` ใน `.env`

> ⚠️ raw file เก็บ "ข้อความโพส" ซึ่งบางครั้งผู้ขายพิมพ์เบอร์/ไลน์ไว้ในเนื้อโพสเอง
> ส่วนนี้ sanitize อัตโนมัติไม่ได้ (เป็น free text) — ไฟล์อยู่ local + gitignored เท่านั้น

## Threading model

- Flask รันใน thread แยก (daemon)
- APScheduler `BackgroundScheduler` (มี thread pool ของตัวเอง)
- pystray รันใน main thread (บล็อค) — เป็นตัวคุมอายุ process
- SQLite: เปิด connection ต่อ operation (`check_same_thread`) เพื่อเลี่ยงปัญหา cross-thread
