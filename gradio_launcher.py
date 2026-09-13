"""
Gradio 演示界面启动脚本。

运行后在浏览器打开本地 UI（默认 http://localhost:7861），
通过 HTTP 调用 FastAPI 后端（默认 http://localhost:8000）。
"""

import sys
from pathlib import Path

src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.gradio_app import main

if __name__ == "__main__":
    main()
