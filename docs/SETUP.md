# Setup

อัปเดตล่าสุด: 2026-06-10

## สถานะการติดตั้งบนเครื่องนี้ (อัปเดต 2026-06-10)

| สิ่งที่ต้องมี | สถานะ |
|--------------|-------|
| Python 3.12.10 | ✅ ติดตั้งแล้ว (`%LOCALAPPDATA%\Programs\Python\Python312`) |
| venv + dependencies | ✅ ติดตั้งแล้วใน `.venv` |
| Database + mock data | ✅ สร้างแล้ว (52 โพสตัวอย่าง) |
| Ollama 0.30.6 + qwen2.5:14b (9GB) | ✅ ติดตั้งแล้ว — parser ทดสอบผ่าน 7/7 |
| ไฟล์ .env | ✅ สร้างแล้ว (ยังต้องเติม APIFY_TOKEN + FB_GROUP_URLS) |
| APIFY_TOKEN + FB_GROUP_URLS | ❌ ยังไม่เติม — scrape จริงยังไม่ได้ |

> **Ollama server:** ตอนนี้รันอยู่ (`ollama serve`). ปกติแอป Ollama จะ auto-start ตอนเปิดเครื่อง
> ถ้า API ไม่ตอบ (`localhost:11434`) เปิดแอป Ollama หรือสั่ง `ollama serve` เอง

### ⚡ GPU ไม่เต็ม / parse ช้า? (สำคัญสำหรับ RTX 5070 12GB)
เช็คด้วย `ollama ps` — ดูคอลัมน์ `PROCESSOR`:
- `100% GPU` = ดี ✅
- `XX%/YY% CPU/GPU` = โมเดลล้น VRAM ดันบางส่วนไป CPU → ช้า + GPU util ต่ำ (18%)

สาเหตุหลักคือ **context (num_ctx) ใหญ่ → KV cache บวม**. qwen2.5:14b (9GB) + ctx 32k = ~15GB > 12GB
แก้ด้วย `OLLAMA_NUM_CTX=4096` ใน `.env` (งาน parse ใช้แค่ ~2k ก็พอ) → โมเดลเหลือ 9.5GB ลงครบ → 100% GPU

> ตั้งไปแล้วในโปรเจ็คนี้ ยืนยัน `ollama ps` = `9.5 GB · 100% GPU`

> ลองหน้าเว็บได้เลยตอนนี้ (ใช้ mock data): `.\.venv\Scripts\python.exe run.py serve`

## Prerequisites

### 1. Python 3.11+  ✅ (ติดตั้งแล้วบนเครื่องนี้)
ถ้าต้องติดตั้งเครื่องใหม่: `winget install Python.Python.3.12`
หรือดาวน์โหลดจาก https://www.python.org/downloads/ (เลือก "Add python.exe to PATH")

> ถ้า `python` เด้งไป Microsoft Store: ปิด App execution alias ที่
> Settings → Apps → Advanced app settings → App execution aliases → ปิด python.exe / python3.exe

### 2. Ollama + qwen2.5:14b
ดาวน์โหลด Ollama: https://ollama.com/download

```powershell
ollama --version
ollama pull qwen2.5:14b      # ~9 GB
ollama list                  # ยืนยันว่ามี qwen2.5:14b
```

Ollama จะเปิด server ที่ `http://localhost:11434` อัตโนมัติ

### 3. Apify account + token
- สมัครที่ https://apify.com
- เอา API token จาก Settings → Integrations → API tokens
- เติมลงไฟล์ `.env` (ดูข้างล่าง)

### 4. (optional) ngrok — สำหรับเปิดดูบนมือถือ
https://ngrok.com/download

---

## ติดตั้งโปรเจ็ค

```powershell
cd C:\Repository\pc-price-tracker

# สร้าง virtual env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# ถ้าโดน ExecutionPolicy บล็อค:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# ติดตั้ง dependencies
pip install -r requirements.txt

# ตั้งค่า env
Copy-Item .env.example .env
# แก้ .env → เติม APIFY_TOKEN
```

## รัน

```powershell
# สร้าง database (ครั้งแรก)
python run.py init-db

# ทดสอบ parser กับข้อความตัวอย่าง
python run.py parse-test "ขาย RTX 4070 Super มือสอง 8500 ต่อรองได้ นนทบุรี"

# scrape ครั้งเดียว (ทดสอบ)
python run.py scrape-once --source groups

# รันแบบเต็ม (Flask + scheduler + tray + เปิด browser)
python main.py
```

เปิด dashboard: http://localhost:5000

## โครงสร้าง .env

ดู `.env.example` — ค่าที่ต้องเติมเองคือ `APIFY_TOKEN`
