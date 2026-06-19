import os
import requests

LINE_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_ADMIN_USER_ID = os.getenv("LINE_ADMIN_USER_ID", "")


def line_enabled() -> bool:
    return bool(LINE_TOKEN and LINE_ADMIN_USER_ID)


def push_text(text: str) -> bool:
    """Push a text message to the admin (Kento). No-op if not configured."""
    if not line_enabled():
        print(f"[LINE disabled] would push: {text}")
        return False
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"to": LINE_ADMIN_USER_ID, "messages": [{"type": "text", "text": text}]},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"[LINE error] {resp.status_code} {resp.text}")
        return False
    return True
