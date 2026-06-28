"""ทดสอบ parser กับโพสต์จริงที่เคยทำให้หลอน — รันแล้วลบได้ (ไม่ใช่ unit test ถาวร)"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from app.config import setup_logging
from app.models import RawPost
from app.parser import parse_post, health_check

setup_logging()

BUNDLE_POST = """ขายชุดคอมพร้อมใช้ จอ+เครื่อง
-จอ LG ultra gear 24” 144 Hz ประกันเหลือ 2ปี 10 เดือน อุปกรณ์/กล่องครบ
-CPU AMD Ryzen5 5600X
-MB ASUS PRIME A520M-K
-RAM KINGSTON HyperX FURY RGB 16GB 8*2 DDR4 Bus 3200
-SSD Sata 500 GB
-HDD 1 TB
-VGA Nvidia GeForce RTX 3060 12GB 🚨  RGB  (มีกล่อง)
-PSU 750W 80+ (มีกล่อง)
-Case AEROCOOL SHARD TEMPERED GLASS (BLACK) (ATX) (SHARD-G-BK-V2)
-เล่นเกมส์ VALO PUBG FIVEM และอื่นๆสบาย ตัดต่อ สตรีม ทำงานได้ปกติลื่นๆ
-ราคา 18500 บาท  ของอยู่ กทม รามคำแหงมารับมือเองได้"""

SHADOW_POST = """MSI SHADOW 3X / 12 GB

RTX 5070 OC

ประกันพึ่งเดินมา 5 เดือน

ราคา 19,500 บาท"""

TRAP_POST = """💥 พี่ไมตรีขอเสนอ GIGGABYTE  RX7600XT 16G GAMING OC  3 พัดลม ประกัน Advice ยาวๆ

      *** เขาว่ารุ่นนี้เกิดมาเพื่อฆ่า  4060Ti ***

💥 ประกันมหาเทพ  ADVICE  ยาวๆ 05/2028    ประกันยาวครบกล่องสภาพดีมากๆ

🐸 ความพิเศษของสินค้า :::  " นานๆ จะเจอ RX 7600xt3 พัดลม  ประกันเยอะขนาดนี้หลุดมาซะที"

💥 ราคาเพียง   8,390 บาทคับ"""

WALL_POST = """เคลียร์ของหลายรายการ นัดรับ BTS แบริ่ง หรือส่งได้
1. การ์ดจอ MSI RTX 3070 VENTUS 2 พัดลม 6,500.-
2. CPU i5 12400 พร้อมซิงค์เดิม 3,200.-
3. แรม Kingston Fury DDR4 16GB (8x2) bus 3200 900.-
4. เมนบอร์ด ASUS B660M-A D4 2,500.-
5. SSD m.2 nvme WD Blue 500GB 690.-
6. PSU Corsair CV650 650W 80+ bronze 1,100.-
7. การ์ดจอ GT 1030 เก่าหน่อย ทักมาคุยราคาได้"""

NOTEBOOK_POST = """ขายโน๊ตบุ๊ค Lenovo Legion 5 Ryzen 7 5800H RTX 3060 RAM 16GB SSD 512GB
จอ 165Hz สภาพ 90% แบตดี ราคา 17,900 บาท ต่อรองได้ อยู่บางนา"""

print("Ollama online:", health_check())
for name, text in [("BUNDLE (คาดหวัง: [])", BUNDLE_POST),
                   ("SHADOW 3X (คาดหวัง: GPU RTX 5070 รายการเดียว)", SHADOW_POST),
                   ("TRAP RX7600XT (คาดหวัง: RX 7600 XT ไม่ใช่ 4060 Ti)", TRAP_POST),
                   ("WALL 7 ชิ้น (คาดหวัง: 6 ชิ้นมีราคา, GT 1030 โดนตัดเพราะไม่มีราคา)", WALL_POST),
                   ("NOTEBOOK จริง (คาดหวัง: NOTEBOOK 1 รายการ)", NOTEBOOK_POST)]:
    print("\n" + "=" * 70)
    print("TEST:", name)
    items = parse_post(RawPost(text=text, source="test", source_url=f"test://{name[:10]}"))
    for it in items:
        print(f"  - [{it.category}] {it.item_name} | {it.price} บาท | brand={it.brand} "
              f"| ff={it.form_factor} | cap={it.capacity} | variant={it.variant}")
    if not items:
        print("  (ไม่มีรายการ)")
