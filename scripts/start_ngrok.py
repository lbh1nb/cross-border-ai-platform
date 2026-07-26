"""一键启动 ngrok 内网穿透，把本地 8000 端口暴露到公网。

前置条件：
    需要先安装 ngrok（https://ngrok.com/download）
    并用 ngrok authtoken <YOUR_TOKEN> 配置认证 token

启动后：
    ngrok 会给一个公网 URL（如 https://xxxx.ngrok-free.app）
    把这个 URL + /callback 配置到飞书应用回调地址

用法：
    python scripts/start_ngrok.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check_ngrok_installed() -> bool:
    """检查 ngrok 是否已安装。"""
    return shutil.which("ngrok") is not None


def wait_for_ngrok_url(timeout_seconds: int = 10) -> str | None:
    """等待 ngrok 启动并通过本地 API 获取公网 URL。

    ngrok 启动后会在 http://127.0.0.1:4040/api/tunnels 暴露隧道信息。
    """
    import httpx

    url = "http://127.0.0.1:4040/api/tunnels"
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                tunnels = data.get("tunnels", [])
                for tunnel in tunnels:
                    public_url = tunnel.get("public_url", "")
                    if public_url.startswith("https://"):
                        return public_url
        except Exception:
            pass
        time.sleep(1)

    return None


def main() -> None:
    """启动 ngrok 隧道。"""
    print("=" * 60)
    print("  ngrok 内网穿透启动器")
    print("=" * 60)
    print()

    if not check_ngrok_installed():
        print("  [错误] 未检测到 ngrok，请先安装：")
        print()
        print("  方法 1（推荐）：用 winget 安装")
        print("    winget install ngrok.ngrok")
        print()
        print("  方法 2：手动下载")
        print("    1. 访问 https://ngrok.com/download")
        print("    2. 下载 Windows 版并解压")
        print("    3. 把 ngrok.exe 放到 PATH 路径下（如 C:\\Windows\\）")
        print()
        print("  安装后还需要配置认证 token：")
        print("    1. 注册 ngrok 账号（免费）")
        print("    2. 在 https://dashboard.ngrok.com/get-started/your-authtoken 获取 token")
        print("    3. 执行: ngrok authtoken <YOUR_TOKEN>")
        print()
        return

    print("  正在启动 ngrok 隧道（本地 8000 → 公网）...")
    print()

    # 启动 ngrok（非阻塞）
    process = subprocess.Popen(
        ["ngrok", "http", "8000", "--log=stdout"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 等待 ngrok 启动并获取公网 URL
    public_url = wait_for_ngrok_url(timeout_seconds=15)

    if not public_url:
        print("  [错误] 无法获取 ngrok 公网 URL")
        print("  请确认：")
        print("    1. 已执行 ngrok authtoken <YOUR_TOKEN>")
        print("    2. 本地 8000 端口未被占用（FastAPI 回调服务已启动）")
        print()
        process.terminate()
        return

    print("=" * 60)
    print("  ✅ ngrok 隧道已启动")
    print("=" * 60)
    print()
    print(f"  公网 URL: {public_url}")
    print()
    print("  飞书应用回调地址配置：")
    print(f"    {public_url}/callback")
    print()
    print("  配置步骤：")
    print("    1. 打开飞书开放平台 https://open.feishu.cn/app")
    print("    2. 选择你的自建应用")
    print("    3. 左侧菜单 → 事件与回调 → 事件配置")
    print("    4. 请求地址粘贴上面的 URL + /callback")
    print("    5. 添加事件: card.action.trigger（卡片回传交互）")
    print("    6. 左侧菜单 → 应用功能 → 机器人 → 启用机器人能力")
    print("    7. 创建版本并发布，等管理员审核通过")
    print()
    print("  按 Ctrl+C 停止 ngrok 隧道")
    print("=" * 60)

    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n  停止 ngrok 隧道...")
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    main()
