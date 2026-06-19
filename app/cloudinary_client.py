import os
import time
import hashlib
import uuid
import requests

# Two ways to configure Cloudinary:
#  1) CLOUDINARY_URL = cloudinary://<api_key>:<api_secret>@<cloud_name>
#  2) CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")
CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
UPLOAD_FOLDER = os.getenv("CLOUDINARY_FOLDER", "doteppan-open-check")

if CLOUDINARY_URL.startswith("cloudinary://"):
    # cloudinary://key:secret@cloud
    rest = CLOUDINARY_URL[len("cloudinary://"):]
    creds, CLOUD_NAME = rest.split("@", 1)
    API_KEY, API_SECRET = creds.split(":", 1)

LOCAL_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(LOCAL_DIR, exist_ok=True)


def cloudinary_enabled() -> bool:
    return bool(CLOUD_NAME and API_KEY and API_SECRET)


def _sign(params: dict) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha1((to_sign + API_SECRET).encode()).hexdigest()


def upload_image(filename: str, content: bytes, content_type: str) -> str:
    """Upload one image and return its URL. Falls back to local storage."""
    if cloudinary_enabled():
        timestamp = int(time.time())
        params = {"folder": UPLOAD_FOLDER, "timestamp": timestamp}
        signature = _sign(params)
        resp = requests.post(
            f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/image/upload",
            data={
                "api_key": API_KEY,
                "timestamp": timestamp,
                "folder": UPLOAD_FOLDER,
                "signature": signature,
            },
            files={"file": (filename, content, content_type or "image/jpeg")},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["secure_url"]

    # ---- local fallback (dev / before Cloudinary is configured) ----
    ext = os.path.splitext(filename)[1] or ".jpg"
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(LOCAL_DIR, name), "wb") as f:
        f.write(content)
    return f"/static/uploads/{name}"
