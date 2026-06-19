from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from .database import SessionLocal
from .models import Store, OpenReport, CloseReport
from .line_client import push_text

JST = ZoneInfo("Asia/Tokyo")
GRACE_MINUTES = 15          # 開店時刻から何分過ぎたらアラートするか
ALERT_CUTOFF_HOUR = 23      # 深夜にアラートを送らないための上限


def now_jst() -> datetime:
    return datetime.now(JST)


def today_jst() -> date:
    return now_jst().date()


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


def is_overdue(store: Store) -> bool:
    """開店時刻＋猶予を過ぎているか（まだ未オープンの店の判定用）。"""
    try:
        hh, mm = [int(x) for x in store.open_time.split(":")]
    except Exception:
        hh, mm = 11, 0
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
            if get_today_open(db, store.id):
                continue
            if is_overdue(store):
                overdue.append(store)

        for store in overdue:
            ok = push_text(
                f"🔴 未オープンアラート\n{store.name} が開店予定 {store.open_time} を"
                f"{GRACE_MINUTES}分過ぎても報告がありません。\n（{n.strftime('%m/%d %H:%M')} 時点）"
            )
            # 通知できた／LINE未設定どちらでも当日フラグは立てて重複連投を防ぐ
            store.alerted_on = td
            db.add(store)
        if overdue:
            db.commit()
    finally:
        db.close()
