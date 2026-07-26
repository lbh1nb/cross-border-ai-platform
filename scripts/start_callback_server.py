"""一键启动飞书卡片回调服务。

启动后：
1. 本地服务监听 http://127.0.0.1:8000
2. 配合 start_ngrok.py 暴露到公网
3. 把公网 URL + /callback 配置到飞书应用回调地址

用法：
    python scripts/start_callback_server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# 把项目根目录加入 sys.path，让 scripts 也能直接双击运行
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import uvicorn

from src.observability.logger import get_logger

logger = get_logger()


def main() -> None:
    """启动 FastAPI 回调服务。"""
    host = "0.0.0.0"
    port = 8000

    print("=" * 60)
    print("  飞书卡片回调服务（FastAPI）")
    print("=" * 60)
    print()
    print(f"  本地地址: http://127.0.0.1:{port}")
    print(f"  回调端点: POST http://127.0.0.1:{port}/callback")
    print(f"  健康检查: GET  http://127.0.0.1:{port}/health")
    print()
    print("  下一步:")
    print("  1. 另开终端运行: python scripts/start_ngrok.py")
    print("  2. 把 ngrok 公网 URL + /callback 配置到飞书应用回调地址")
    print("  3. 在飞书群发送带按钮的卡片，点击按钮即可触发回调")
    print()
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)

    uvicorn.run(
        "src.feishu.card_callback:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
