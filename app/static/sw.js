// インストール可能にするだけの最小SW。キャッシュせず常に最新を取得（ステータスを古くしない）。
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
