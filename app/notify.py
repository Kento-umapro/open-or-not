import os
import requests
from .line_client import push_text, line_enabled

# 既定の送信先（ALERT_EMAILS が未設定のとき使う）
DEFAULT_EMAILS = [
    "kento.nishimura@umapro-jp.com",
    "takashi.morishita@umapro-jp.com",
    "marin.saiki@umapro-jp.com",
    "kazutaka.ota@umapro-jp.com",
    "imoto0116@gmail.com",
]


def recipients():
    raw = os.getenv("ALERT_EMAILS", "").strip()
    if raw:
        seen, out = set(), []
        for e in raw.replace("\n", ",").split(","):
            e = e.strip()
            if e and e not in seen:
                seen.add(e); out.append(e)
        return out
    return DEFAULT_EMAILS


def make_webhook_url():
    return os.getenv("MAKE_WEBHOOK_URL", "").strip()


def make_enabled() -> bool:
    return bool(make_webhook_url())


def send_make_email(subject: str, text: str, to=None):
    """Make.com の Webhook に投げてメール送信させる。戻り値 (ok, detail)。"""
    url = make_webhook_url()
    if not url:
        return False, "未設定：MAKE_WEBHOOK_URL が空です"
    to_list = to or recipients()
    payload = {
        "to": ",".join(to_list),   # カンマ区切り（メール module にそのまま貼れる）
        "to_list": to_list,        # 配列でも使えるように
        "subject": subject,
        "text": text,
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
    except Exception as e:
        return False, f"送信例外: {e}"
    if 200 <= resp.status_code < 300:
        return True, f"OK（{len(to_list)}名宛て / Make Webhook）: {resp.text[:120]}"
    return False, f"Make Webhookエラー {resp.status_code}: {resp.text[:300]}"


def channel_label() -> str:
    if make_enabled():
        return f"email（Make Webhook / {len(recipients())}名）"
    if line_enabled():
        return "LINE"
    return "OFF（MAKE_WEBHOOK_URL も LINE も未設定）"


def notify_alert(subject: str, text: str) -> bool:
    """アラート送信。MAKE_WEBHOOK_URL があればメール(Make)、無ければLINEにフォールバック。"""
    if make_enabled():
        ok, detail = send_make_email(subject, text)
        if not ok:
            print(f"[MAIL] {detail}")
        return ok
    return push_text(text)
