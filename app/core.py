from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import jpholiday

from .database import SessionLocal
from .models import Store, OpenReport, CloseReport
from .line_client import push_text, line_enabled

JST = ZoneInfo("Asia/Tokyo")
GRACE_MINUTES = 0           # 0=開店時刻ちょうどで判定（猶予なし・ジャストタイム）
ALERT_CUTOFF_HOUR = 23      # 深夜にアラートを送らないための上限
RESET_HOUR = 9              # 毎朝この時刻に全店「未報告」へ戻す（＝営業日の境目）

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


def business_date(dt: datetime = None) -> date:
    """営業日の日付。朝9時(RESET_HOUR)を境にする＝9時前は前日扱い。
    これにより毎朝9時に全店が自動で「未報告」に戻り、
    翌4時閉店などの深夜営業も0時で勝手にリセットされない。"""
    n = dt or now_jst()
    d = n.date()
    if n.hour < RESET_HOUR:
        d = d - timedelta(days=1)
    return d


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
    d = d or business_date()
    return schedule_for(store).get(day_kind(d))


def open_time_label(store: Store, d: date = None) -> str:
    """画面表示用ラベル。休業日は「本日休業」。"""
    t = todays_open_time(store, d)
    return t if t else "本日休業"


def get_today_open(db, store_id: int):
    return (
        db.query(OpenReport)
        .filter(OpenReport.store_id == store_id, OpenReport.report_date == business_date())
        .first()
    )


def get_today_close(db, store_id: int):
    return (
        db.query(CloseReport)
        .filter(CloseReport.store_id == store_id, CloseReport.report_date == business_date())
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


def check_unopened(force: bool = False):
    """開店時刻＋猶予を過ぎても未オープンの店を見つけて管理者へLINE通知。
    送信に成功した時だけ当日フラグを立てる（鍵未設定/失敗時は次回再送される）。
    force=True で「当日アラート済み」「深夜カットオフ」を無視して即実行（テスト用）。
    結果サマリを返す。"""
    db = SessionLocal()
    summary = {"now": "", "line": line_enabled(),
               "overdue": [], "sent": [], "failed": [], "skipped_cutoff": False}
    try:
        n = now_jst()
        summary["now"] = n.strftime("%m/%d %H:%M")
        if not force and n.hour >= ALERT_CUTOFF_HOUR:
            summary["skipped_cutoff"] = True
            return summary
        td = business_date(n)
        for store in db.query(Store).all():
            if not force and store.alerted_on == td:
                continue
            if todays_open_time(store, td) is None:   # 本日休業はスキップ
                continue
            if get_today_open(db, store.id):           # もう報告済み
                continue
            if not is_overdue(store, td):              # まだ開店前 or 猶予内
                continue
            summary["overdue"].append(store.name)
            ot = todays_open_time(store, td) or ""
            ok = push_text(
                f"🔴 未オープンアラート\n{store.name} が開店時刻 {ot} になりましたが、"
                f"まだオープン報告がありません。\n（{n.strftime('%m/%d %H:%M')} 時点）"
            )
            if ok:
                summary["sent"].append(store.name)
                store.alerted_on = td               # 成功時のみ重複防止フラグ
                db.add(store)
            else:
                summary["failed"].append(store.name)
        db.commit()
        return summary
    finally:
        db.close()
