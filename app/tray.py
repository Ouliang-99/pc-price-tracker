"""System tray icon (pystray).

เมนู: Open dashboard / Scrape Groups / Scrape Marketplace / Quit
รันใน main thread (บล็อค) — เป็นตัวคุมอายุ process
"""
from __future__ import annotations

import logging
import webbrowser
from typing import Callable

from .config import settings

log = logging.getLogger(__name__)


def _make_icon_image():
    """สร้างไอคอนสี่เหลี่ยมง่ายๆ ด้วย Pillow."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), "#0f1115")
    d = ImageDraw.Draw(img)
    d.rectangle([10, 14, 54, 44], outline="#4f8cff", width=3)
    d.rectangle([26, 44, 38, 52], fill="#4f8cff")
    d.line([18, 52, 46, 52], fill="#4f8cff", width=3)
    return img


def run_tray(scrape_trigger: Callable[[str], None], on_quit: Callable[[], None]) -> None:
    """สร้าง + รัน tray icon (บล็อคจนกว่าจะ Quit)."""
    import pystray
    from pystray import MenuItem as Item

    url = f"http://localhost:{settings.flask_port}"

    def _open(icon, item):
        webbrowser.open(url)

    def _scrape_groups(icon, item):
        scrape_trigger("groups")

    def _scrape_market(icon, item):
        scrape_trigger("marketplace")

    def _quit(icon, item):
        log.info("tray: quit")
        icon.stop()
        on_quit()

    menu = pystray.Menu(
        Item("เปิด Dashboard", _open, default=True),
        Item("Scrape Groups ตอนนี้", _scrape_groups),
        Item("Scrape Marketplace ตอนนี้", _scrape_market),
        pystray.Menu.SEPARATOR,
        Item("ออก", _quit),
    )
    icon = pystray.Icon("pc_price_tracker", _make_icon_image(), "PC Price Tracker", menu)
    log.info("tray เริ่มแล้ว")
    icon.run()
