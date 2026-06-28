# PC Price Tracker

Local desktop app ติดตามราคา PC parts มือสองจาก **Facebook Groups + Marketplace**
แปลงโพสภาษาไทยด้วย Ollama → เก็บประวัติราคา → เตือนเมื่อเจอของถูกกว่าตลาด
ข้อมูลเก็บ local 100% ใช้ตัดสินใจซื้อ-ขายส่วนตัว

## ฟีเจอร์
- ดึงโพสอัตโนมัติด้วย Apify (Groups ทุก 6 ชม. / Marketplace ทุก 1 ชม.)
- AI parser (qwen2.5:14b) แปลงข้อความไทย → ราคา/สเปค/จังหวัด
- Dashboard ราคา avg/min/max/median ต่อสินค้า ที่ `localhost:5000`
- แจ้งเตือน (Windows toast) เมื่อราคา < 85% ของ avg + flag "รับมือได้"
- System tray + เปิด browser อัตโนมัติ

## เริ่มใช้งาน
ดูขั้นตอนเต็มที่ [docs/SETUP.md](docs/SETUP.md)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # แล้วเติม APIFY_TOKEN
python run.py init-db
python main.py
```

## เอกสาร
- [docs/PLAN.md](docs/PLAN.md) — เป้าหมาย, phases, ความเสี่ยง
- [docs/TASKS.md](docs/TASKS.md) — checklist ความคืบหน้า
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — โครงไฟล์, schema, data flow
- [docs/SETUP.md](docs/SETUP.md) — prerequisites + วิธีติดตั้ง

## ความเป็นส่วนตัว (PDPA)
เก็บเฉพาะ ราคา / สเปค / จังหวัด / ลิงก์โพส — **ไม่เก็บ ชื่อ/เบอร์/ที่อยู่ของผู้ขาย**
ไม่ส่งข้อมูลออกนอกเครื่อง ยกเว้น Apify API call และลิงก์โพสต้นทาง
