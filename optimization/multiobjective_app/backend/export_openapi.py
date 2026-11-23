"""API の OpenAPI 定義（openapi.json）をファイルに書き出す

サーバーを起動しなくても、FastAPI のアプリから定義を取り出せる。
API（main.py）を変えたら、もう一度実行して更新する。

    python export_openapi.py            # backend/openapi.json に書き出す
    python export_openapi.py out.json   # 書き出し先を指定する
"""

import json
import sys
from pathlib import Path

from main import app

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "openapi.json"
out.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"書き出しました: {out}")
