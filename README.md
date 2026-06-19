# どてっぱん オープンチェック

各店のiPad1台で「オープン報告（写真必須・最低1枚）」「閉店報告＋翌日への引き継ぎ」を行い、
本部が全店の開店状況を一覧監視。開店時刻を過ぎても未報告の店は自動でLINE通知する。

- バックエンド: FastAPI / 写真: Cloudinary / DB: Postgres（ローカルはsqlite）
- 通知: LINE Messaging API（LINE Notifyは2025/3終了のため後継のpushを使用）
- 写真は **最低1枚必須・複数OK**。問題がなくても必ずアップが基本ルール。

## 画面

| URL | 用途 |
|-----|------|
| `/` | 店舗選択（初期設定用。各iPadはここから自店を開いてホーム画面に追加） |
| `/s/{店舗ID}` | 各店のiPadアプリ（オープン報告／閉店報告／引き継ぎ表示） |
| `/admin` | 本部ダッシュボード（全店の本日状況・写真・引き継ぎ。60秒ごと自動更新） |

未オープン→営業中→閉店でステータスの色が大きく変わる。開店時刻を過ぎた未オープン店は赤＋点滅。

## ローカルで動かす

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
# http://localhost:8000/  → 店舗選択
# http://localhost:8000/admin → ダッシュボード
```

Cloudinary／LINE未設定でも動く（写真はローカル保存・アラートはログ出力のみ）。

## Railwayへデプロイ

1. このリポジトリをGitHubにpush
2. Railwayで New Project → Deploy from GitHub
3. **Postgres** を追加（`DATABASE_URL` は自動で入る）
4. Variables に以下を設定:
   - `CLOUDINARY_URL` = `cloudinary://<api_key>:<api_secret>@<cloud_name>`
   - （任意）`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_ADMIN_USER_ID`
5. デプロイ後、`/` で12店舗が自動作成される

起動コマンドは `Procfile` 済み（`uvicorn app.main:app --host 0.0.0.0 --port $PORT`）。

## LINE通知のセットアップ（任意）

1. 自分専用の通知用LINE公式アカウントを作成 → Messaging API有効化
2. 自分のLINEでその公式アカウントを友だち追加
3. webhook等で自分の `userId`（U始まりのID）を取得し `LINE_ADMIN_USER_ID` に設定
4. チャネルアクセストークンを `LINE_CHANNEL_ACCESS_TOKEN` に設定

未設定の場合、アラートはサーバーログに出るだけで動作には影響しない。

## 店舗・開店時刻の変更

`app/seed.py` の `DEFAULT_STORES` が初回起動時のみ投入される。
店名・開店時刻はDBで直接編集するか、`seed.py`を直して再投入。
開店時刻は各店ごとに `open_time`（"HH:MM"）。この時刻＋15分で未オープン判定。

## 認識コード（各端末の初回登録）

パスワードではなく「認識コード」。各端末で**初回の1回だけ入力**すれば、以降はCookieで記憶（約60日）して聞かれません。

- **本部**（`/admin` 系）: 認識コード `0`（入力すると全店ステータスマップに入る。環境変数 `ADMIN_PASSCODE` で変更可）
- **各店**: 並び順の番号。札幌すすきの=1／月島本店=2／門前仲町=3／松戸東口=4／日吉駅前=5／前橋=6／京都木屋町=7／石山駅前=8
  （`/admin/setup` に各店のURL・QR・認識コードを表示。`seed.py` の順番で決まる）
- 店舗は「専用URL（トークン）＋認識コード」の二重ロック。他店のURL/コードでは操作できない。
- 本番では `SECRET_KEY` を必ず独自の値に設定（Cookie署名用）。

## 店舗専用URLの配布（初期設定）

本部で `/admin/setup` を開く → 各店のQR/URL/パスワードが出る → 各iPadでQRを読み、Safariの共有→「ホーム画面に追加」。

## 調整ポイント

- 未オープンの猶予分数 / 深夜アラート上限: `app/core.py` の `GRACE_MINUTES`, `ALERT_CUTOFF_HOUR`
- チェック頻度（既定5分おき）: `app/main.py` の scheduler
- 写真の保存先フォルダ: `CLOUDINARY_FOLDER`

## データ構造

- `stores`（店ID, 店名, 開店時刻, アラート送信日）
- `open_reports`（店ID, 日付, オープン時刻, 報告者, メモ, 写真URL[]）
- `close_reports`（店ID, 日付, 閉店時刻, 報告者, 引き継ぎ事項, 写真URL[]）

「本日」はJST基準。日付が変わると各店のステータスはリセットされる。
