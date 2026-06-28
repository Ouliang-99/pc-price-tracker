# -*- coding: utf-8 -*-
"""สร้างรูปจำลองสกรีนช็อตโพสต์ขายคอมเซ็ต (พื้นเข้ม + ข้อความไทย) ไว้ทดสอบ VL model"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LINES = [
    "คอมเซ็ต จบทุกเกมส์ จบทุกการตัดต่อ",
    " ยกไปพร้อมเล่นเลย",
    "CPU - i9 13900K",
    "GPU - RTX5070 Aero White",
    "MB - TUF Z690 PLUS D4",
    "CASE - ตู้ปลา + Jonsbo D41 พร้อมจอของเคส",
    "RAM - Kingston DDR4 32GB 3200 (16x2)",
    "SSD - Nvme 1TB+ซิงค์ RGB",
    "HDD - Seagate 2TB",
    "Colling - ชุดน้ำปิด CoolerMaster 3 ตอน White",
    "PSU - RM850X+สายถักขาว",
    "รับบัตรเครดิต + 3%",
    "นัดรับ : โชคชัย4 ซอย 32",
    "O87-748-149O ต่อบ ดูน้อยลง",
]

FONT = ImageFont.truetype(r"C:\Windows\Fonts\LeelawUI.ttf", 22)
LINE_H = 34
PAD = 18

img = Image.new("RGB", (466, PAD * 2 + LINE_H * len(LINES)), "#202020")
draw = ImageDraw.Draw(img)
for i, line in enumerate(LINES):
    draw.text((PAD, PAD + i * LINE_H), line, font=FONT, fill="#d9d9d9")

out = Path(__file__).parent / "test_post.png"
img.save(out)
print(f"saved: {out} ({img.size[0]}x{img.size[1]})")
