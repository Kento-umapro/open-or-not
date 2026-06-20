import os
import requests

PUSH_URL = "https://api.line.me/v2/bot/message/push"
MULTICAST_URL = "https://api.line.me/v2/bot/message/multicast"
BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def _token():
    return os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()


def _broadcast_on() -> bool:
    return os.getenv("LINE_BROADCAST", "").strip().lower() in ("1", "true", "yes", "on")


def _user_ids():
    # カンマ区切りで複数指定も可
    raw = os.getenv("LINE_ADMIN_USER_ID", "")
    return [u.strip() for u in raw.replace("\n", ",").split(",") if u.strip()]


def line_enabled() -> bool:
    if not _token():
        return False
    return _broadcast_on() or bool(_user_ids())


def push_detail(text: str):
    """LINEへ送信。戻り値 (ok, detail)。
    モード:
      LINE_BROADCAST=1            → 友だち全員に送信（broadcast）
      LINE_ADMIN_USER_ID=複数     → 指定ユーザー全員に送信（multicast）
      LINE_ADMIN_USER_ID=1人      → その人だけに送信（push）
    """
    tok = _token()
    if not tok:
        return False, "未設定：LINE_CHANNEL_ACCESS_TOKEN が空です"

    messages = [{"type": "text", "text": text}]

    if _broadcast_on():
        url, payload, mode = BROADCAST_URL, {"messages": messages}, "broadcast（友だち全員）"
    else:
        ids = _user_ids()
        if not ids:
            return False, "未設定：LINE_ADMIN_USER_ID が空です（全員に送るなら LINE_BROADCAST=1 を設定）"
        if len(ids) == 1:
            url, payload, mode = PUSH_URL, {"to": ids[0], "messages": messages}, "push（1人）"
        else:
            url, payload, mode = MULTICAST_URL, {"to": ids, "messages": messages}, f"multicast（{len(ids)}人）"

    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json=payload, timeout=30,
        )
    except Exception as e:
        return False, f"送信例外: {e}"

    if resp.status_code == 200:
        return True, f"OK（{mode}）"

    hint = ""
    if resp.status_code == 403:
        hint = "（権限不足。broadcastは『Messaging APIのプラン/設定』で許可が必要な場合あり。pushなら友だち未追加が原因）"
    elif resp.status_code == 401:
        hint = "（チャネルアクセストークンが無効。発行し直して再設定）"
    elif resp.status_code == 400:
        hint = "（宛先や本文の形式エラー。ユーザーIDはUで始まる33文字）"
    elif resp.status_code == 429:
        hint = "（送信上限に到達。LINEの無料プランは月の送信数に上限あり）"
    return False, f"LINE APIエラー {resp.status_code}: {resp.text} {hint}"


def push_text(text: str) -> bool:
    ok, detail = push_detail(text)
    if not ok:
        print(f"[LINE] {detail} | text={text[:50]}")
    return ok


def mode_label() -> str:
    if not _token():
        return "OFF（トークン未設定）"
    if _broadcast_on():
        return "ON / broadcast（友だち全員）"
    ids = _user_ids()
    if not ids:
        return "OFF（宛先未設定）"
    return f"ON / {len(ids)}人へ送信" if len(ids) > 1 else "ON / 1人へ送信"
