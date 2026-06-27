const storeId = document.body.dataset.store;
const token = document.body.dataset.token;
const files = { open: [], close: [] };

// 通信が固まらないように一定時間で打ち切る（既定20秒）
function fetchT(url, opts = {}, ms = 20000) {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), ms);
  return fetch(url, { ...opts, signal: c.signal }).finally(() => clearTimeout(t));
}
function errMsg(e) {
  return (e && e.name === "AbortError")
    ? "通信に時間がかかっています（時間切れ）。"
    : (e && e.message) ? e.message : "エラーが発生しました。";
}

// オーバーレイ：表示が長引いたら「トップに戻る」を出して必ず脱出できるようにする
let _overlayTimer = null;
function showOverlay(text) {
  const o = document.getElementById("overlay");
  const txt = document.getElementById("overlay-text");
  const home = document.getElementById("overlay-home");
  if (txt) txt.textContent = text;
  if (home) home.style.display = "none";
  if (o) o.classList.add("show");
  clearTimeout(_overlayTimer);
  _overlayTimer = setTimeout(() => { if (home) home.style.display = "inline-block"; }, 8000);
}
function hideOverlay() {
  const o = document.getElementById("overlay");
  if (o) o.classList.remove("show");
  clearTimeout(_overlayTimer);
}

function showSheet(kind) {
  document.getElementById("sheet-" + kind).style.display = "block";
  const action = document.getElementById("openAction");
  if (action) action.style.display = "none";
  document.getElementById("sheet-" + kind).scrollIntoView({ behavior: "smooth", block: "start" });
}
function hideSheet(kind) {
  document.getElementById("sheet-" + kind).style.display = "none";
  const action = document.getElementById("openAction");
  if (action) action.style.display = "block";
}

function wirePhotos(kind) {
  const input = document.getElementById(kind + "-photos");
  if (!input) return;
  input.addEventListener("change", () => {
    for (const f of input.files) files[kind].push(f);
    input.value = "";
    renderThumbs(kind);
  });
}

function renderThumbs(kind) {
  const box = document.getElementById(kind + "-thumbs");
  box.innerHTML = "";
  files[kind].forEach((f, i) => {
    const url = URL.createObjectURL(f);
    const d = document.createElement("div");
    d.className = "thumb";
    d.innerHTML = `<img src="${url}"><button onclick="removePhoto('${kind}',${i})">×</button>`;
    box.appendChild(d);
  });
  if (kind === "open") {
    document.getElementById("open-submit").disabled = files.open.length < 1;
  }
}

function removePhoto(kind, i) {
  files[kind].splice(i, 1);
  renderThumbs(kind);
}

async function submit(kind) {
  if (kind === "open" && files.open.length < 1) {
    alert("写真を最低1枚アップロードしてください");
    return;
  }
  showOverlay(kind === "open" ? "オープン報告を送信中…" : "閉店報告を送信中…");

  const fd = new FormData();
  files[kind].forEach((f) => fd.append("photos", f));
  if (kind === "open") {
    fd.append("reporter", val("open-reporter"));
    fd.append("memo", val("open-memo"));
  } else {
    fd.append("reporter", val("close-reporter"));
    fd.append("handover", val("close-handover"));
  }

  try {
    const res = await fetchT(`/s/${storeId}/${token}/${kind}`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "送信に失敗しました");
    window.location.href = data.redirect || `/s/${storeId}/${token}`;
  } catch (e) {
    hideOverlay();
    showErr(errMsg(e) + "\n通信状況を確認して、もう一度お試しください。\n解決しない場合は「トップに戻る」から選び直してください。");
  }
}

function showErr(msg) {
  const box = document.getElementById("errBox");
  if (!box) { alert(msg); return; }
  document.getElementById("errText").textContent = msg;
  box.style.display = "block";
  box.scrollIntoView({ behavior: "smooth", block: "center" });
}
function hideErr() {
  const box = document.getElementById("errBox");
  if (box) box.style.display = "none";
}

async function undo(kind) {
  const label = kind === "close" ? "閉店報告" : "オープン報告";
  if (!confirm(label + "を取り消しますか？\n（押し間違えた場合の取り消しです）")) return;
  showOverlay(label + "を取り消し中…");
  try {
    const res = await fetchT(`/s/${storeId}/${token}/undo-${kind}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "取り消しに失敗しました");
    window.location.href = data.redirect || `/s/${storeId}/${token}`;
  } catch (e) {
    hideOverlay();
    showErr(errMsg(e) + "\nもう一度お試しください。");
  }
}

async function setStatus(status) {
  const L = { unopened: "未報告", open: "営業中", closed: "閉店" };
  if (!confirm("本日のステータスを「" + L[status] + "」に変更しますか？")) return;
  showOverlay("ステータスを変更中…");
  try {
    const fd = new FormData();
    fd.append("status", status);
    const res = await fetchT(`/s/${storeId}/${token}/set-status`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "変更に失敗しました");
    window.location.href = data.redirect || `/s/${storeId}/${token}`;
  } catch (e) {
    hideOverlay();
    showErr(errMsg(e) + "\nもう一度お試しください。\n解決しない場合は「トップに戻る」から選び直してください。");
  }
}

function val(id) {
  const el = document.getElementById(id);
  return el ? el.value : "";
}

wirePhotos("open");
wirePhotos("close");

// PWA: 軽量サービスワーカー（インストール可能にするだけ。常に最新を取得）
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/sw.js").catch(() => {});
}
