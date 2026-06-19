import os
import io
import json
import hmac
import base64
import hashlib
import secrets
from datetime import datetime

from fastapi import FastAPI, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

from .database import Base, engine, get_db, SessionLocal
from .models import Store, OpenReport, CloseReport
from . import core
from .seed import seed_if_empty
from .cloudinary_client import upload_image, cloudinary_enabled
from .line_client import line_enabled, push_detail

BASE_DIR = os.path.dirname(__file__)
app = FastAPI(title="どてっぱん オープンチェック")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

scheduler = BackgroundScheduler(timezone="Asia/Tokyo")

# ---------- auth ----------
SECRET_KEY = os.getenv("SECRET_KEY", "doteppan-change-this-secret")
ADMIN_PASSCODE = os.getenv("ADMIN_PASSCODE", "0")  # 本部の認識コード
COOKIE_MAX_AGE = 60 * 60 * 24 * 60  # 60日


def _sig(name: str) -> str:
    return hmac.new(SECRET_KEY.encode(), name.encode(), hashlib.sha256).hexdigest()[:24]


def admin_authed(request: Request) -> bool:
    return request.cookies.get("ac") == _sig("admin")


def store_authed(request: Request, sid: int) -> bool:
    return request.cookies.get(f"sc{sid}") == _sig(f"store:{sid}")


def _login_page(request: Request, title: str, subtitle: str, action: str, status=200):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": title, "subtitle": subtitle, "action": action},
        status_code=status,
    )


def _backfill_tokens():
    """token/passcode未設定の店舗に付与（既存DBの移行用）。"""
    db = SessionLocal()
    try:
        changed = False
        stores = db.query(Store).order_by(Store.id).all()
        for i, s in enumerate(stores, start=1):
            if not s.token:
                s.token = secrets.token_urlsafe(6); changed = True
            if not s.passcode:
                s.passcode = str(i); changed = True
        if changed:
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    seed_if_empty()
    _backfill_tokens()
    # 未オープンチェックを5分おきに実行
    scheduler.add_job(core.check_unopened, "interval", minutes=5, id="check_unopened",
                      replace_existing=True)
    scheduler.start()
    print(f"Cloudinary: {'ON' if cloudinary_enabled() else 'local fallback'} | "
          f"LINE alert: {'ON' if line_enabled() else 'OFF'}")


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown(wait=False)


# ---------- store iPad app ----------
def _require_store(db, store_id: int, token: str) -> Store:
    """店舗を取得し、トークンが一致しなければ拒否（他店の操作を防ぐ）。"""
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(404, "店舗が見つかりません")
    if not token or token != store.token:
        raise HTTPException(403, "この店舗を操作する権限がありません")
    return store


@app.get("/logout")
def logout(request: Request):
    """端末の認証（本部・店舗）を解除してトップへ。間違ってログインした時の戻る用。"""
    resp = RedirectResponse("/", status_code=303)
    for k in request.cookies:
        if k == "ac" or k.startswith("sc"):
            resp.delete_cookie(k)
    return resp


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    # 各店の番号付き入口（番号はクッキー切れ時の再入力用の控え）
    stores = [
        {"id": s.id, "name": s.name, "token": s.token, "code": s.passcode}
        for s in db.query(Store).order_by(Store.id).all()
    ]
    return templates.TemplateResponse("home.html", {"request": request, "stores": stores})


# トークン無しでアクセスした場合は施錠画面（店名・トークンは出さない）
@app.get("/s/{store_id}", response_class=HTMLResponse)
def store_locked(store_id: int, request: Request):
    return templates.TemplateResponse("locked.html", {"request": request}, status_code=403)


@app.get("/s/{store_id}/{token}", response_class=HTMLResponse)
def store_app(store_id: int, token: str, request: Request, db: Session = Depends(get_db)):
    store = db.get(Store, store_id)
    if not store or token != store.token:
        return templates.TemplateResponse("locked.html", {"request": request}, status_code=403)
    # パスワード認証（端末ごとに初回のみ）
    if not store_authed(request, store_id):
        return _login_page(request, f"{store.name}", "認識コードを入力（初回のみ）",
                           f"/s/{store_id}/{token}/login")
    open_rep = core.get_today_open(db, store_id)
    close_rep = core.get_today_close(db, store_id)
    status = core.derive_status(open_rep, close_rep)
    handover = None
    if status == "unopened":
        latest = core.get_latest_handover(db, store_id)
        if latest:
            handover = {
                "text": latest.handover,
                "date": latest.closed_at.strftime("%m/%d"),
                "photos": latest.photos,
            }
    ctx = {
        "request": request,
        "store": store,
        "token": token,
        "status": status,
        "today": core.today_jst().strftime("%Y/%m/%d (%a)"),
        "today_open": core.open_time_label(store),
        "opened_at": open_rep.opened_at.strftime("%H:%M") if open_rep else None,
        "closed_at": close_rep.closed_at.strftime("%H:%M") if close_rep else None,
        "handover": handover,
    }
    return templates.TemplateResponse("store.html", ctx)


@app.post("/s/{store_id}/{token}/login")
def store_login(store_id: int, token: str, passcode: str = Form(""),
                db: Session = Depends(get_db)):
    store = db.get(Store, store_id)
    if not store or token != store.token:
        raise HTTPException(403, "権限がありません")
    if passcode.strip() != (store.passcode or ""):
        return JSONResponse({"ok": False}, status_code=200)
    resp = JSONResponse({"ok": True, "redirect": f"/s/{store_id}/{token}"})
    resp.set_cookie("sc%d" % store_id, _sig(f"store:{store_id}"),
                    max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.post("/s/{store_id}/{token}/open")
async def submit_open(
    store_id: int,
    token: str,
    request: Request,
    reporter: str = Form(""),
    memo: str = Form(""),
    photos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    _require_store(db, store_id, token)
    if not store_authed(request, store_id):
        raise HTTPException(403, "ログインが必要です")
    if core.get_today_open(db, store_id):
        return JSONResponse({"ok": True, "message": "本日は報告済みです"}, status_code=200)

    valid = [p for p in photos if p.filename]
    if len(valid) < 1:
        raise HTTPException(400, "写真を1枚以上アップロードしてください")

    urls = []
    for p in valid:
        content = await p.read()
        urls.append(upload_image(p.filename, content, p.content_type))

    rep = OpenReport(
        store_id=store_id,
        report_date=core.today_jst(),
        opened_at=core.now_jst().replace(tzinfo=None),
        reporter=reporter.strip() or None,
        memo=memo.strip() or None,
        photos_json=json.dumps(urls, ensure_ascii=False),
    )
    db.add(rep)
    db.commit()
    return {"ok": True, "redirect": f"/s/{store_id}/{token}"}


@app.post("/s/{store_id}/{token}/close")
async def submit_close(
    store_id: int,
    token: str,
    request: Request,
    reporter: str = Form(""),
    handover: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    _require_store(db, store_id, token)
    if not store_authed(request, store_id):
        raise HTTPException(403, "ログインが必要です")
    if core.get_today_close(db, store_id):
        return JSONResponse({"ok": True, "message": "本日は閉店報告済みです"}, status_code=200)

    urls = []
    for p in [p for p in photos if p.filename]:
        content = await p.read()
        urls.append(upload_image(p.filename, content, p.content_type))

    rep = CloseReport(
        store_id=store_id,
        report_date=core.today_jst(),
        closed_at=core.now_jst().replace(tzinfo=None),
        reporter=reporter.strip() or None,
        handover=handover.strip() or None,
        photos_json=json.dumps(urls, ensure_ascii=False),
    )
    db.add(rep)
    db.commit()
    return {"ok": True, "redirect": f"/s/{store_id}/{token}"}


@app.get("/s/{store_id}/{token}/api/today")
def store_today_api(store_id: int, token: str, request: Request, db: Session = Depends(get_db)):
    """店舗端末向けの全店ステータス（写真・引き継ぎ等の機微情報は含めない）。"""
    store = db.get(Store, store_id)
    if not store or token != store.token:
        raise HTTPException(403, "権限がありません")
    if not store_authed(request, store_id):
        raise HTTPException(403, "ログインが必要です")
    out = []
    for s in db.query(Store).order_by(Store.id).all():
        open_rep = core.get_today_open(db, s.id)
        close_rep = core.get_today_close(db, s.id)
        status = core.derive_status(open_rep, close_rep)
        out.append({
            "id": s.id,
            "name": s.name,
            "open_time": core.open_time_label(s),
            "status": status,
            "overdue": status == "unopened" and core.is_overdue(s),
        })
    return {"date": core.today_jst().strftime("%Y/%m/%d"),
            "now": core.now_jst().strftime("%H:%M"), "stores": out}


# ---------- HQ dashboard (本部・要パスワード) ----------
@app.post("/admin/login")
def admin_login(passcode: str = Form("")):
    if passcode.strip() != ADMIN_PASSCODE:
        return JSONResponse({"ok": False}, status_code=200)
    resp = JSONResponse({"ok": True, "redirect": "/admin"})
    resp.set_cookie("ac", _sig("admin"), max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not admin_authed(request):
        return _login_page(request, "本部 ・ 全店ステータス", "認識コードを入力（初回のみ）", "/admin/login")
    # 本部トップ＝全店ステータスマップ
    return templates.TemplateResponse("map.html", {"request": request})


@app.get("/admin/list", response_class=HTMLResponse)
def admin_list(request: Request, db: Session = Depends(get_db)):
    if not admin_authed(request):
        return _login_page(request, "本部 ・ 全店ステータス", "認識コードを入力（初回のみ）", "/admin/login")
    # 写真・引き継ぎ付きの詳細一覧
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/admin/setup", response_class=HTMLResponse)
def admin_setup(request: Request, db: Session = Depends(get_db)):
    """各店の専用URL＋QR。初回に各iPadでこのURLを開いてホーム画面に追加する。"""
    if not admin_authed(request):
        return _login_page(request, "本部 ・ 全店ステータス", "認識コードを入力（初回のみ）", "/admin/login")
    try:
        import qrcode
        have_qr = True
    except Exception:
        have_qr = False

    base = str(request.base_url).rstrip("/")
    rows = []
    for s in db.query(Store).order_by(Store.id).all():
        url = f"{base}/s/{s.id}/{s.token}"
        qr_data = None
        if have_qr:
            img = qrcode.make(url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qr_data = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        rows.append({"name": s.name, "url": url, "qr": qr_data, "passcode": s.passcode})
    return templates.TemplateResponse("setup.html", {"request": request, "rows": rows})


# 旧 /map は /admin に統合（後方互換でリダイレクト）
@app.get("/map")
def status_map_redirect():
    return RedirectResponse("/admin")


@app.get("/api/admin/today")
def admin_today(request: Request, db: Session = Depends(get_db)):
    if not admin_authed(request):
        raise HTTPException(401, "認証が必要です")
    out = []
    for store in db.query(Store).order_by(Store.id).all():
        open_rep = core.get_today_open(db, store.id)
        close_rep = core.get_today_close(db, store.id)
        status = core.derive_status(open_rep, close_rep)
        out.append({
            "id": store.id,
            "name": store.name,
            "open_time": core.open_time_label(store),
            "status": status,
            "overdue": status == "unopened" and core.is_overdue(store),
            "opened_at": open_rep.opened_at.strftime("%H:%M") if open_rep else None,
            "closed_at": close_rep.closed_at.strftime("%H:%M") if close_rep else None,
            "open_photos": open_rep.photos if open_rep else [],
            "memo": open_rep.memo if open_rep else None,
            "handover": close_rep.handover if close_rep else None,
            "close_photos": close_rep.photos if close_rep else [],
        })
    return {"date": core.today_jst().strftime("%Y/%m/%d"), "now": core.now_jst().strftime("%H:%M"), "stores": out}


# ---------- 診断用（本部・要ログイン） ----------
@app.get("/admin/test-line")
def admin_test_line(request: Request):
    """LINEへテスト通知を1通送って、結果（成功/失敗の理由）をその場で返す。"""
    if not admin_authed(request):
        raise HTTPException(403, "本部ログインが必要です")
    ok, detail = push_detail(
        f"✅ テスト通知（どてっぱん オープンチェック）\n"
        f"この通知が届いていれば設定はOKです。\n（{core.now_jst().strftime('%m/%d %H:%M')}）"
    )
    return JSONResponse({
        "line_enabled": line_enabled(),
        "sent": ok,
        "detail": detail,
        "hint": "sent=true なら西村さんのLINEに届いているはずです。届かない/falseの場合は detail を確認してください。",
    })


@app.get("/admin/run-check")
def admin_run_check(request: Request):
    """未オープンチェックを今すぐ強制実行（当日アラート済み・深夜カットオフを無視）。
    今まさに開店時刻を過ぎて未報告の店があれば、即LINE送信して結果を返す。"""
    if not admin_authed(request):
        raise HTTPException(403, "本部ログインが必要です")
    summary = core.check_unopened(force=True)
    return JSONResponse(summary)


# Railway Cron からも叩けるように（任意）
@app.post("/cron/check-unopened")
def cron_check():
    summary = core.check_unopened()
    return {"ok": True, "summary": summary}


@app.get("/healthz")
def healthz():
    return {"ok": True}
