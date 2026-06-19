const storeId = document.body.dataset.store;
const token = document.body.dataset.token;
const files = { open: [], close: [] };

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
  const overlay = document.getElementById("overlay");
  document.getElementById("overlay-text").textContent =
    kind === "open" ? "オープン報告を送信中…" : "閉店報告を送信中…";
  overlay.classList.add("show");

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
    const res = await fetch(`/s/${storeId}/${token}/${kind}`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "送信に失敗しました");
    window.location.href = data.redirect || `/s/${storeId}/${token}`;
  } catch (e) {
    overlay.classList.remove("show");
    alert(e.message + "\n通信状況を確認して、もう一度お試しください。");
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
