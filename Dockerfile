FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# $PORT をコマンド行に書かず、start.py が os.environ から読む（シェル展開不要）
CMD ["python", "start.py"]
