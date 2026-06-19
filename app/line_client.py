import os
import requests


def _creds():
    # 毎回 環境変数から読む（再デプロイ後の値を確実に反映）
    return os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip(), os.getenv("LINE_ADMIN_USER_ID", "").strip()


def line_enabled() -> bool:
    tok, uid = _creds()
    return bool(tok and uid)


def push_detail(text: str):
    """LINEへpush。戻り値 (ok: bool, detail: str)。詳細メッセージで原因を特定できる。"""
    tok, uid = _creds()
    if not tok and not uid:
        return False, "未設定：LINE_CHANNEL_ACCESS_TOKEN と LINE_ADMIN_USER_ID の両方が空です"
    if not tok:
        return False, "未設定：LINE_CHANNEL_ACCESS_TOKEN が空です"
    if not uid:
        return False, "未設定：LINE_ADMIN_USER_ID が空です"
    try:
        resp = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"to": uid, "messages": [{"type": "text", "text": text}]},
            timeout=30,
        )
    except Exception as e:
        return False, f"送信例外: {e}"
    if resp.status_code == 200:
        return True, "OK"
    # よくあるエラーをわかりやすく
    body = resp.text
    hint = ""
    if resp.status_code == 403:
        hint = "（多くは『Botを友だち追加していない』か『ユーザーIDが別人』。スマホでそのMessaging APIのOAを友だち追加してください）"
    elif resp.status_code == 401:
        hint = "（チャネルアクセストークンが無効。発行し直して再設定してください）"
    elif resp.status_code == 400:
        hint = "（宛先ユーザーIDの形式が不正な可能性。Uで始まる33文字のIDか確認してください）"
    return False, f"LINE APIエラー {resp.status_code}: {body} {hint}"


def push_text(text: str) -> bool:
    ok, detail = push_detail(text)
    if not ok:
        print(f"[LINE] {detail} | text={text[:50]}")
    return ok
