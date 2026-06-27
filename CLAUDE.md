# CLAUDE.md — どてっぱん オープンチェック（開発引き継ぎ）

このリポジトリは、飲食フランチャイズ「どてっぱん」（東京もんじゃ・全8店）の
**開店/閉店 報告 & 本部監視 PWA**。FastAPI + 素のHTML/JS。各店 iPad 1台で運用。

- 本番URL: https://web-production-ecf59.up.railway.app
- リポジトリ: Kento-umapro/open-or-not（main ブランチ）
- デプロイ: Railway（Dockerfile）。main に push すると自動再デプロイ。
- ローカル起動: `python start.py`（PORT環境変数を読む。/healthz が 200 ならOK）

## 連携ルール（重要）
- **GitHub の main が唯一の正（source of truth）**。
- 変更は**ファイル単位の編集**で行い、「全ファイル置換」はしない（過去に全置換で履歴が分断された）。
- 大きめの変更後はこの CLAUDE.md の「機能一覧」「環境変数」も更新する。

## ディレクトリ
app/
  main.py              ルーティング/認証/スケジューラ起動/診断API
  core.py              時刻・営業日・ステータス・開店時刻表・アラート判定 (check_unopened)
  models.py            Store / OpenReport / CloseReport
  database.py          SQLAlchemy（DATABASE_URL があれば Postgres、無ければ sqlite）
  seed.py              初回シード（8店）
  notify.py            アラート送信。Make Webhook(メール) 優先、無ければ LINE
  line_client.py       LINE送信（push/multicast/broadcast）※現在はフォールバック扱い
  cloudinary_client.py 画像アップロード（CLOUDINARY_URL があれば Cloudinary）
  templates/           home/store/map/admin/setup/login/locked .html
  static/              app.js(報告/取消/エラー) style.css mapdata.json sw.js manifest.json
start.py  Dockerfile  Procfile  requirements.txt

## 店舗と認識コード
本部=0、店舗=1〜8（seed順）。1札幌すすきの 2月島本店 3門前仲町 4松戸東口 5日吉駅前 6前橋 7京都木屋町 8石山駅前。
店名は app/static/mapdata.json のキーと一致必須。

## 開店時刻（アラート判定の基準・core.py STORE_SCHEDULES）
| 店 | 平日 | 土 | 日祝 |
|---|---|---|---|
| 札幌すすきの | 17:00 | 17:00 | 17:00 |
| 月島本店 | 11:00 | 11:00 | 11:00 |
| 門前仲町 | 17:00 | 11:00 | 11:00 |
| 松戸東口 | 11:00 | 11:00 | 11:00 |
| 日吉駅前 | 11:00 | 11:00 | 11:00 |
| 前橋 | 17:00 | 11:00 | 11:00 |
| 京都木屋町 | 11:00 | 11:00 | 11:00 |
| 石山駅前 | 11:30 | 11:00 | 11:00 |
祝日は jpholiday で判定し日曜扱い。

## 機能一覧（実装済み）
- 店舗ページ（トークン+コード認証）：オープン報告（写真≥1必須・カメラロール可）→営業中、
  閉店報告（写真任意+引き継ぎ）→閉店。写真は撮影/ライブラリ両対応（input に capture を付けない）。
- 取り消し：営業中で「オープン報告を取り消す」、閉店で「閉店を取り消す」。当日分のレコード削除で前状態へ。
  閉店済みのままオープンだけ取り消すのは不可（先に閉店取消）。POST /s/{id}/{tok}/undo-open|undo-close。
- エラー時UI：送信失敗で赤いバナー表示＋「トップに戻る」ボタン（app.js showErr/hideErr）。
- 本部：日本地図ステータス /admin、一覧 /admin/list、QR/URL /admin/setup。
- 営業日リセット：毎朝9:00で全店「未報告」に戻る（core.business_date／RESET_HOUR=9）。
  深夜営業（翌4:00閉店等）も0時で切れず同一営業日に属する。
- 前日からの引き継ぎ：前営業日(=business_date-1)の閉店引き継ぎだけ翌日表示（2日後は出さない）。
  core.get_carryover_handover。本部一覧・店舗ページ両方に表示。
- 未オープンアラート：開店時刻ちょうど（GRACE_MINUTES=0）で判定、スケジューラ1分間隔、23時以降は抑制(ALERT_CUTOFF_HOUR=23)。
  送信成功時のみ当日フラグ(alerted_on)を立て重複防止。
- オープン通知：オープン報告時にも通知（NOTIFY_ON_OPEN=0 で無効化可）。

## アラート送信経路（notify.py）
- MAKE_WEBHOOK_URL があれば Make.com Webhook にPOST → メール送信（LINE通数制限回避のため現行はこれ）。
  payload: {to: "カンマ区切り", to_list: [...], subject, text}。
  Make側シナリオ「どてっぱん オープンチェック メールアラート」(team 1546046, scenario 6349497) が
  Webhook→Email(SMTP「お名前メール_送信」)で送信。webhook: https://hook.eu1.make.com/nc2i2nwlchocz995fq5wtpewho3881eu
- 無ければ LINE（push/multicast/broadcast）にフォールバック。
- 宛先は ALERT_EMAILS（カンマ区切り）。未設定時は notify.py の DEFAULT_EMAILS（5名）。

## 環境変数（Railway）
- SECRET_KEY 署名Cookie用（必須）
- MAKE_WEBHOOK_URL メールアラート用Webhook（現行の主経路）
- ALERT_EMAILS 宛先（カンマ区切り。未設定なら既定5名）
- NOTIFY_ON_OPEN 既定ON。0でオープン通知のみOFF
- CLOUDINARY_URL 画像保存（無ければローカル保存）
- DATABASE_URL 任意（無ければ sqlite ./app.db）
- LINE_CHANNEL_ACCESS_TOKEN / LINE_ADMIN_USER_ID / LINE_BROADCAST 任意（フォールバック用）

## 診断/運用エンドポイント（本部ログイン要）
- GET /admin/test-mail Make経由でテストメール送信、結果JSON
- GET /admin/run-check 未オープンチェックを今すぐ強制実行（当日フラグ/深夜抑制を無視）
- GET /admin/test-line LINE単体テスト（フォールバック確認用）
- POST /cron/check-unopened 外部cronからも叩ける

## 注意
- 起動ログに Alert channel: ... と出る（email(Make) / LINE / OFF）。
- ステータスは保存ではなく「当日の Open/Close レポートから導出」。リセットは business_date の境界で自然に起きる。
