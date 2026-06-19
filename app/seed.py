from .database import SessionLocal
from .models import Store
import secrets

# 運営委託型 + 札幌（2026/3開店）の8店。名前は static/mapdata.json のキーと一致。
# 心斎橋・刈谷・向ヶ丘遊園・登戸は対象外。開店時刻は仮で全店11:00（要調整）。
DEFAULT_STORES = [
    {"name": "札幌すすきの店", "open_time": "11:00"},
    {"name": "月島本店",       "open_time": "11:00"},
    {"name": "門前仲町店",     "open_time": "11:00"},
    {"name": "松戸東口店",     "open_time": "11:00"},
    {"name": "日吉駅前店",     "open_time": "11:00"},
    {"name": "前橋店",         "open_time": "11:00"},
    {"name": "京都木屋町店",   "open_time": "11:00"},
    {"name": "石山駅前店",     "open_time": "11:00"},
]


def seed_if_empty():
    db = SessionLocal()
    try:
        if db.query(Store).count() == 0:
            for i, s in enumerate(DEFAULT_STORES, start=1):
                db.add(Store(name=s["name"], open_time=s["open_time"],
                             token=secrets.token_urlsafe(6), passcode=str(i)))
            db.commit()
            print(f"Seeded {len(DEFAULT_STORES)} stores.")
    finally:
        db.close()
