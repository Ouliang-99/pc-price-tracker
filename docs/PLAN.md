# PC Price Tracker — Plan

> Local desktop app ติดตามราคา PC parts มือสองจาก Facebook Groups + Marketplace
> ใช้ตัดสินใจซื้อ-ขายส่วนตัว ไม่ได้ขายต่อ ข้อมูลเก็บ local 100%

อัปเดตล่าสุด: 2026-06-10

---

## 1. เป้าหมาย (Goals)

1. ดึงโพสขาย PC parts มือสองจาก Facebook (Groups + Marketplace) อัตโนมัติ
2. แปลงโพสภาษาไทยเป็นข้อมูลมีโครงสร้าง (ชื่อสินค้า / หมวด / ราคา / สภาพ / จังหวัด) ด้วย Ollama
3. เก็บประวัติราคา แล้วคำนวณราคา avg/min/max/median ต่อสินค้า
4. เตือน (notification) เมื่อเจอของถูกกว่า avg เกิน threshold
5. ดู dashboard ได้ที่ localhost:5000 (หรือ ngrok สำหรับมือถือ)

## 2. ขอบเขต / ข้อจำกัด (Constraints)

- ข้อมูลทั้งหมดเก็บ local (SQLite) — **ไม่มี cloud database**
- เก็บแค่ ราคา / สเปค / จังหวัด / ลิงก์โพส — **ไม่เก็บ ชื่อ/เบอร์/ที่อยู่ของผู้ขาย (PDPA)**
- ไม่ส่งข้อมูลออกนอกเครื่อง ยกเว้น Apify API call และลิงก์โพสต้นทาง
- รันบน Windows + RTX 5070

## 3. Stack

| ส่วน | เทคโนโลยี |
|------|-----------|
| ภาษา | Python 3.11+ |
| Web UI | Flask (localhost:5000) |
| Database | SQLite (`data/pcprice.db`) |
| Scraping | Apify Client |
| AI Parser | Ollama + qwen2.5:14b (`localhost:11434`) |
| Scheduler | APScheduler |
| System tray | pystray |
| Notification | plyer (Windows toast) |

## 4. Architecture

`main.py` รัน 4 อย่างพร้อมกัน:

```
main.py
 ├─ (1) Flask server          → thread แยก, เสิร์ฟ localhost:5000
 ├─ (2) APScheduler jobs      → Scraper A (6h), Scraper B (1h)
 ├─ (3) System tray icon      → pystray, เมนู open/quit
 └─ (4) Auto-open browser     → เปิด dashboard ตอน start
```

Data flow:

```
Apify actor → raw posts → Ollama parser → ParsedItem
   → insert price_history → recompute item_catalog
   → check alert (price < threshold × avg) → alert_log + toast
```

## 5. Phases (ทำทีละส่วน)

ดูสถานะแบบ checkbox ที่ [TASKS.md](TASKS.md)

| Phase | ชื่อ | ผลลัพธ์ |
|-------|------|---------|
| 0 | Scaffold & docs | โครงโปรเจ็ค, planning docs, requirements, .env.example |
| 1 | Config & DB | โหลด env, สร้าง schema (3 ตาราง), helper CRUD |
| 2 | AI Parser | เรียก Ollama แปลงโพสไทย → JSON มีโครงสร้าง |
| 3 | Scrapers | Apify Groups + Marketplace → normalize เป็น raw post |
| 4 | Catalog & Alerts | คำนวณ stats ต่อสินค้า + logic เตือน + toast |
| 5 | Scheduler | APScheduler รัน scraper ตาม interval |
| 6 | Web UI | Flask dashboard: catalog, history, alerts |
| 7 | Tray & main.py | รวมทุกอย่างเข้า entrypoint เดียว |
| 8 | Polish | ngrok, manual run CLI, README, ทดสอบ end-to-end |

## 6. ลำดับการ implement

ทำ Phase 1 → 8 ตามลำดับ แต่ละ phase ต้อง import ได้/รันเดี่ยวได้ก่อนไป phase ถัดไป
แต่ละ module มี `if __name__ == "__main__"` สำหรับทดสอบแยก

## 7. ความเสี่ยง / สิ่งที่ต้องระวัง

- **Apify actor schema** อาจเปลี่ยน → แยก normalize layer ออกมาเพื่อแก้จุดเดียว
- **Ollama parse พลาด** → ถ้า parse ไม่ได้ skip โพสนั้น + log warning (ไม่ทำให้ job ตาย)
- **ราคาซ้ำ** (โพสเดิม scrape หลายรอบ) → dedupe ด้วย source_url
- **PDPA** → parser ต้องไม่ดึง/เก็บ field ที่เป็นข้อมูลส่วนบุคคล
- **Rate limit / cost ของ Apify** → interval ตามสเปค (A=6h, B=1h), มี manual trigger แยก
