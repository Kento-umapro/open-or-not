from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import jpholiday

from .database import SessionLocal
from .models import Store, OpenReport, CloseReport
from .line_client import push_text

JST = ZoneInfo("Asia/Tokyo")
GRACE_MINUTES = 15          # 開店時刻から何分過ぎたらアラートするか
ALERT_CUTOFF_HOUR = 23      # 深夜にアラートを送らないための上限

# ───────────────────────────────────────────────────────────────
# 店舗ごとの開店スケジュール（曜日・祝日で切替）
#   weekday=月〜金 / saturday=土 / sunday=日 / holiday=祝日
#   値は "HH:MM"。None にするとその区分は「休業（アラート対象外）」。
#   ※ 公式サイト・各掲載・上毛新聞・現場情報をもとに設定。要調整は本部で。
# ───────────────────────────────────────────────────────────────
def _all(t):
    return {"weekday": t, "saturday": t, "sunday": t, "holiday": t}

STORE_SCHEDULES = {
    "札幌すすきの店": _all("17:00"),                                   # 17:00〜翌4:00（毎日）
    "月島本店":       _all("11:00"),                                   # 11:00〜23:00
    "門前仲町店":     {"weekday": "17:00", "saturday": "11:00",        # 平日17:00 / 土日祝11:00
                       "sunday": "11:00", "holiday": "11:00"},
    "松戸東口店":     _all("11:00"),                                   # 11:00〜23:00
    "日吉駅前店":     _all("11:00"),                                   # 11:00〜23:00
    "前橋店":         {"weekday": "17:00", "saturday": "11:00",        # 平日17:00 / 土日祝11:00
                       "sunday": "11:00", "holiday": "11:00"},
    "京都木屋町店":   _all("11:00"),                                   # 11:00〜翌4:00（通し）
    "石山駅前店":     {"weekday": "11:30", "saturday": "11:00",        # 平日11:30 / 土日祝11:00
                       "sunday": "11:00", "holiday": "11:00"},
}
_DEFAULT_SCHEDULE = _all("11:00")


def now_jst() -> datetime:
    return datetime.now(JST)


def today_jst() -> date:
    return now_jst().date()


def day_kind(d: date) -> str:
    """その日が weekday / saturday / sunday / holiday のどれか（祝日優先）。"""
    if jpholiday.is_holiday(d):
        return "holiday"
    wd = d.weekday()           # Mon=0 .. Sun=6
    if wd == 5:
        return "saturday"
    if wd == 6:
        return "sunday"
    return "weekday"


def schedule_for(store: Store) -> dict:
    return STORE_SCHEDULES.get(store.name, _DEFAULT_SCHEDULE)


def todays_open_time(store: Store, d: date = None):
    """その日の開店時刻 "HH:MM"。休業日は None。"""
    d = d or today_jst()
    return schedule_for(store).get(day_kind(d))


def open_time_label(store: Store, d: date = None) -> str:
    """画面表示用ラベル。休業日は「本日休業」。"""
    t = todays_open_time(store, d)
    return t if t else "本日休業"


def get_today_open(db, store_id: int):
    return (
        db.query(OpenReport)
        .filter(OpenReport.store_id == store_id, OpenReport.report_date == today_jst())
        .first()
    )


def get_today_close(db, store_id: int):
    return (
        db.query(CloseReport)
        .filter(CloseReport.store_id == store_id, CloseReport.report_date == today_jst())
        .first()
    )


def get_latest_handover(db, store_id: int):
    """直近の閉店報告（＝翌日への引き継ぎ）。今日のオープン前に表示する。"""
    return (
        db.query(CloseReport)
        .filter(CloseReport.store_id == store_id, CloseReport.handover != None)  # noqa: E711
        .order_by(CloseReport.closed_at.desc())
        .first()
    )


def derive_status(open_rep, close_rep) -> str:
    if close_rep:
        return "closed"      # 閉店
    if open_rep:
        return "open"        # 営業中
    return "unopened"        # 未オープン


def is_overdue(store: Store, d: date = None) -> bool:
    """その日の開店時刻＋猶予を過ぎているか（まだ未オープンの店の判定用）。
    休業日や開店前は False。"""
    t = todays_open_time(store, d)
    if not t:
        return False          # 本日休業 → アラート対象外
    try:
        hh, mm = [int(x) for x in t.split(":")]
    except Exception:
        return False
    n = now_jst()
    deadline = n.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(minutes=GRACE_MINUTES)
    return n >= deadline


def check_unopened():
    """開店時刻＋猶予を過ぎても未オープンの店を見つけて、1日1回だけ管理者へLINE通知。"""
    db = SessionLocal()
    try:
        n = now_jst()
        if n.hour >= ALERT_CUTOFF_HOUR:
            return
        td = n.date()
        overdue = []
        for store in db.query(Store).all():
            if store.alerted_on == td:
                continue
            if todays_open_time(store, td) is None:   # 本日休業はスキップ
                continue
            if get_today_open(db, store.id):
                continue
            if is_overdue(store, td):
                overdue.append(store)

        for store in overdue:
            ot = todays_open_time(store, td) or ""
            ok = push_text(
                f"🔴 未オープンアラート\n{store.name} が開店予定 {ot} を"
                f"{GRACE_MINUTES}分過ぎても報告がありません。\n（{n.strftime('%m/%d %H:%M')} 時点）"
            )
            # 通知できた／LINE未設定どちらでも当日フラグは立てて重複連投を防ぐ
            store.alerted_on = td
            db.add(store)
        if overdue:
            db.commit()
    finally:
        db.close()
