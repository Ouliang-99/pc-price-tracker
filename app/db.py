"""SQLite layer — schema, connection, CRUD helpers.

- price_history : ตารางหลัก เก็บทุกโพส (dedupe ด้วย source_url)
- item_catalog  : VIEW auto-computed (avg/min/max/median/count ต่อสินค้า)
- alert_log     : ประวัติการเตือน

เปิด connection ต่อ operation (check_same_thread=False ปลอดภัยเพราะไม่ share conn ข้าม thread)
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .config import settings

log = logging.getLogger(__name__)


# --- schema ---------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name   TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    price       INTEGER NOT NULL,
    condition   TEXT    DEFAULT 'ไม่ระบุ',
    location    TEXT    DEFAULT 'ไม่ระบุ',
    brand       TEXT    DEFAULT 'ไม่ระบุ',
    form_factor TEXT    DEFAULT 'ไม่ระบุ',      -- Desktop | Laptop | ไม่ระบุ
    capacity    TEXT    DEFAULT 'ไม่ระบุ',      -- 16GB, 1TB, 500GB ...
    speed       TEXT    DEFAULT 'ไม่ระบุ',      -- 3200, 6000, Gen4 ...
    cl_timing   TEXT    DEFAULT 'ไม่ระบุ',      -- CL30 ...
    variant     TEXT    DEFAULT 'ไม่ระบุ',      -- 3 พัดลม / SO-DIMM / DDR5 ...
    source      TEXT    NOT NULL,              -- groups | marketplace
    source_url  TEXT    NOT NULL,              -- dedupe key (ไม่ใส่ UNIQUE เดี่ยวแล้ว เพราะ 1 URL อาจมีหลายชิ้น)
    negotiable  INTEGER DEFAULT 0,
    posted_at   TEXT,
    scraped_at  TEXT    NOT NULL,
    UNIQUE(source_url, item_name, price)       -- ป้องกันซ้ำเวลารัน replay สำหรับโพสต์เหมาขายหลายชิ้น
);

CREATE INDEX IF NOT EXISTS idx_ph_item   ON price_history(item_name);
CREATE INDEX IF NOT EXISTS idx_ph_cat    ON price_history(category);
CREATE INDEX IF NOT EXISTS idx_ph_source ON price_history(source);

CREATE TABLE IF NOT EXISTS alert_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name    TEXT    NOT NULL,
    price        INTEGER NOT NULL,
    avg_at_time  REAL    NOT NULL,
    discount_pct REAL    NOT NULL,
    location     TEXT,
    source_url   TEXT    NOT NULL,
    local_pickup INTEGER DEFAULT 0,           -- flag "รับมือได้"
    alerted_at   TEXT    NOT NULL,
    is_read      INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alert_read ON alert_log(is_read);

-- catalog จัดกลุ่มตาม (รุ่น + form_factor + capacity + speed) → ไม่แยก variant แล้วเพื่อความสะอาดตา
-- median คำนวณด้วย window function (SQLite 3.25+) ผ่าน CTE
CREATE VIEW IF NOT EXISTS item_catalog AS
WITH ranked AS (
    SELECT
        item_name, form_factor, capacity, speed, price,
        ROW_NUMBER() OVER (PARTITION BY item_name, form_factor, capacity, speed ORDER BY price) AS rn,
        COUNT(*)     OVER (PARTITION BY item_name, form_factor, capacity, speed)               AS cnt
    FROM price_history
)
SELECT
    p.item_name                                   AS item_name,
    MAX(p.category)                               AS category,
    p.form_factor                                 AS form_factor,
    p.capacity                                    AS capacity,
    p.speed                                       AS speed,
    ''                                            AS variant,
    ROUND(AVG(p.price), 0)                        AS avg_price,
    MIN(p.price)                                  AS min_price,
    MAX(p.price)                                  AS max_price,
    (SELECT ROUND(AVG(price), 0) FROM ranked r
       WHERE r.item_name = p.item_name
         AND r.form_factor = p.form_factor
         AND r.capacity = p.capacity
         AND r.speed = p.speed
         AND r.rn IN ((r.cnt + 1) / 2, (r.cnt + 2) / 2)) AS median_price,
    COUNT(*)                                       AS sample_count,
    MAX(p.scraped_at)                              AS last_updated
FROM price_history p
GROUP BY p.item_name, p.form_factor, p.capacity, p.speed;
"""


# --- connection -----------------------------------------------------------

def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_conn(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """เพิ่ม column ใหม่ให้ db เก่า + รีเฟรช view (CREATE VIEW IF NOT EXISTS ไม่ replace ของเดิม)."""
    table_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'").fetchone()
    if not table_exists:
        return
        
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(price_history)")}
    for col in ("brand", "form_factor", "capacity", "speed", "cl_timing", "variant"):
        if col not in existing:
            conn.execute(f"ALTER TABLE price_history ADD COLUMN {col} TEXT DEFAULT 'ไม่ระบุ'")
            log.info("migrate: เพิ่ม column %s", col)
    # drop view เก่าแล้วให้ SCHEMA สร้างใหม่ (กันกรณี view definition เปลี่ยน)
    conn.execute("DROP VIEW IF EXISTS item_catalog")


def init_db(db_path: Optional[Path] = None) -> None:
    """สร้างตาราง + view (idempotent) + migrate db เก่า."""
    with get_conn(db_path) as conn:
        _migrate(conn)
        conn.executescript(SCHEMA)
    log.info("init_db เสร็จ: %s", db_path or settings.db_path)


def reset_db(db_path: Optional[Path] = None) -> None:
    """ล้างข้อมูลทั้งหมด (price_history + alert_log) แล้ว VACUUM.

    ใช้ DELETE แทนลบไฟล์ เพราะไฟล์ .db อาจถูก process อื่นเปิดค้างอยู่ (WAL บน Windows)
    """
    init_db(db_path)  # กันกรณีตารางยังไม่มี
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM price_history")
        conn.execute("DELETE FROM alert_log")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('price_history', 'alert_log')")
    # VACUUM ต้องรันนอก transaction เลยเปิด connection แยก
    conn = connect(db_path)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()
    log.info("reset_db เสร็จ: ล้างข้อมูลทั้งหมดแล้ว (%s)", db_path or settings.db_path)


# --- writes ---------------------------------------------------------------

def insert_price(row: dict, db_path: Optional[Path] = None) -> bool:
    """insert 1 โพส. คืน True ถ้า insert ใหม่, False ถ้าซ้ำ (source_url เดิม)."""
    cols = ["item_name", "category", "price", "condition", "location",
            "brand", "form_factor", "capacity", "speed", "cl_timing", "variant",
            "source", "source_url", "negotiable", "posted_at", "scraped_at"]
    placeholders = ", ".join("?" for _ in cols)
    sql = (
        f"INSERT OR IGNORE INTO price_history ({', '.join(cols)}) "
        f"VALUES ({placeholders})"
    )
    with get_conn(db_path) as conn:
        cur = conn.execute(sql, [row.get(c) for c in cols])
        return cur.rowcount > 0


def update_price_history(history_id: int, updates: dict, db_path: Optional[Path] = None) -> bool:
    """อัปเดตข้อมูลของโพส (เช่น ย้ายหมวด/แก้ชื่อรุ่น)."""
    allowed_cols = {"item_name", "category", "capacity", "speed", "form_factor", "variant"}
    set_clauses = []
    values = []
    for k, v in updates.items():
        if k in allowed_cols:
            set_clauses.append(f"{k} = ?")
            values.append(v)
            
    if not set_clauses:
        return False
        
    values.append(history_id)
    sql = f"UPDATE price_history SET {', '.join(set_clauses)} WHERE id = ?"
    
    with get_conn(db_path) as conn:
        cur = conn.execute(sql, values)
        return cur.rowcount > 0


def insert_alert(row: dict, db_path: Optional[Path] = None) -> int:
    cols = ["item_name", "price", "avg_at_time", "discount_pct", "location",
            "source_url", "local_pickup", "alerted_at"]
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO alert_log ({', '.join(cols)}) VALUES ({placeholders})"
    with get_conn(db_path) as conn:
        cur = conn.execute(sql, [row.get(c) for c in cols])
        return int(cur.lastrowid)


def mark_alert_read(alert_id: int, db_path: Optional[Path] = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute("UPDATE alert_log SET is_read = 1 WHERE id = ?", (alert_id,))


# --- reads ----------------------------------------------------------------

def already_alerted(source_url: str, db_path: Optional[Path] = None) -> bool:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM alert_log WHERE source_url = ? LIMIT 1", (source_url,)
        ).fetchone()
        return row is not None


def get_price_stats(item_name: str, form_factor: str = "ไม่ระบุ",
                    capacity: str = "ไม่ระบุ", speed: str = "ไม่ระบุ",
                    db_path: Optional[Path] = None) -> Optional[tuple[float, int]]:
    """(avg_price, sample_count) ของกลุ่มเดียวกับ item_catalog
    (item_name + form_factor + capacity + speed) — กันเทียบข้าม spec
    เช่น SSD 1TB ไปเทียบ avg ที่รวม 120GB. คืน None ถ้าไม่มีข้อมูลในกลุ่ม."""
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT AVG(price) AS avg, COUNT(*) AS cnt FROM price_history "
            "WHERE item_name = ? AND form_factor = ? AND capacity = ? AND speed = ?",
            (item_name, form_factor, capacity, speed),
        ).fetchone()
        if row is None or row["avg"] is None:
            return None
        return float(row["avg"]), int(row["cnt"])


def get_prices(item_name: str, capacity: str = "ไม่ระบุ",
               db_path: Optional[Path] = None) -> tuple[list[int], bool]:
    """ราคาทั้งหมดของรุ่นนี้ใน price_history สำหรับคำนวณช่วงราคา.

    ถ้าระบุ capacity จะลองกรองก่อน (กัน SSD 1TB ไปปนช่วงราคา 500GB)
    ไม่เจอค่อย fallback เป็นทั้งรุ่น. คืน (prices, capacity_matched)
    """
    with get_conn(db_path) as conn:
        if capacity and capacity != "ไม่ระบุ":
            rows = conn.execute(
                "SELECT price FROM price_history WHERE item_name = ? AND capacity = ?",
                (item_name, capacity),
            ).fetchall()
            if rows:
                return [r["price"] for r in rows], True
        rows = conn.execute(
            "SELECT price FROM price_history WHERE item_name = ?", (item_name,)
        ).fetchall()
        return [r["price"] for r in rows], False


def get_catalog(db_path: Optional[Path] = None) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM item_catalog ORDER BY sample_count DESC, item_name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_date(source: str, db_path: Optional[Path] = None) -> Optional[str]:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(COALESCE(posted_at, scraped_at)) as max_dt "
            "FROM price_history WHERE source = ?",
            (source,)
        ).fetchone()
        return row["max_dt"] if row else None


def get_history(item_name: str, limit: int = 100, db_path: Optional[Path] = None) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM price_history WHERE item_name = ? "
            "ORDER BY COALESCE(posted_at, scraped_at) DESC LIMIT ?",
            (item_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_alerts(unread_only: bool = False, limit: int = 100,
               db_path: Optional[Path] = None) -> list[dict]:
    sql = """
        SELECT a.*, p.capacity, p.speed, p.form_factor, p.variant
        FROM alert_log a
        LEFT JOIN price_history p 
          ON a.source_url = p.source_url 
         AND a.item_name = p.item_name 
         AND a.price = p.price
    """
    if unread_only:
        sql += " WHERE a.is_read = 0"
    sql += " GROUP BY a.id ORDER BY a.alerted_at DESC LIMIT ?"
    with get_conn(db_path) as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]


def counts(db_path: Optional[Path] = None) -> dict:
    with get_conn(db_path) as conn:
        ph = conn.execute("SELECT COUNT(*) c FROM price_history").fetchone()["c"]
        al = conn.execute("SELECT COUNT(*) c FROM alert_log").fetchone()["c"]
        items = conn.execute("SELECT COUNT(*) c FROM item_catalog").fetchone()["c"]
        unread = conn.execute(
            "SELECT COUNT(*) c FROM alert_log WHERE is_read = 0"
        ).fetchone()["c"]
        return {"price_history": ph, "alerts": al, "items": items, "unread": unread}


if __name__ == "__main__":
    from .config import setup_logging

    setup_logging()
    init_db()
    print("counts:", counts())
