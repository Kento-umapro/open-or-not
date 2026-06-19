import os
import uvicorn

# Railway は環境変数 PORT を注入する。コマンド行に $PORT を書くとシェル展開されず
# 落ちることがあるので、ここで Python が直接 os.environ から読む（展開不要）。
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
