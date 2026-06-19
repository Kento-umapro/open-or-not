FROM python:3.12-slim

WORKDIR /app

# 依存だけ先に入れてレイヤキャッシュを効かせる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway が注入する $PORT で待ち受ける（未設定のローカルは 8000）
# ※ ENV PORT は設定しない（Railwayのポート検出と衝突して502になるため）
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
