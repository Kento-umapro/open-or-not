FROM python:3.12-slim

WORKDIR /app

# 依存だけ先に入れてレイヤキャッシュを効かせる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway は $PORT を渡してくる（ローカルは 8000）
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
