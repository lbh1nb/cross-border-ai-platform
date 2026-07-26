"""cloudflared 自动下载服务。

业务用户机器上没有 cloudflared 时，自动从 Cloudflare 官方下载
对应平台的 cloudflared 二进制文件，放到 exe 同目录（或项目根目录）。

这样业务用户无需去 GitHub 下载、无需配置环境变量，
点"启动公网隧道"时会自动完成下载和启动。

下载地址：
- Windows: https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
- macOS:   https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz
- Linux:   https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64

注意：下载源是 GitHub Releases，国内访问可能较慢，
如果下载失败会提示用户手动下载。
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

from src.observability.logger import get_logger

logger = get_logger()

# cloudflared 二进制文件在本地存放的路径（exe 同目录或项目根目录）
def _get_cloudflared_path() -> Path:
    """获取 cloudflared 可执行文件的本地存放路径。

    打包模式：exe 同目录
    开发模式：项目根目录
    """
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent

    if platform.system() == "Windows":
        return base_dir / "cloudflared.exe"
    return base_dir / "cloudflared"


# 各平台下载地址
_DOWNLOAD_URLS = {
    "Windows": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    "Darwin": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz",
    "Linux": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
}

# 下载超时（秒），GitHub 国内访问慢，给足时间
_DOWNLOAD_TIMEOUT = 120


def is_cloudflared_available() -> bool:
    """检查 cloudflared 是否可用（PATH 中或本地目录）。

    Returns:
        可用返回 True，否则 False
    """
    # 1. 检查 PATH
    if shutil.which("cloudflared"):
        return True

    # 2. 检查本地目录
    local_path = _get_cloudflared_path()
    if local_path.exists():
        # 确保可执行（非 Windows 平台需要 chmod +x）
        if platform.system() != "Windows":
            try:
                os.chmod(local_path, 0o755)
            except Exception:
                pass
        return True

    return False


def get_cloudflared_executable() -> str:
    """获取 cloudflared 可执行文件路径。

    优先用 PATH 中的，其次用本地目录的。

    Returns:
        可执行文件路径字符串，未找到返回空字符串
    """
    path_in_path = shutil.which("cloudflared")
    if path_in_path:
        return path_in_path

    local_path = _get_cloudflared_path()
    if local_path.exists():
        if platform.system() != "Windows":
            try:
                os.chmod(local_path, 0o755)
            except Exception:
                pass
        return str(local_path)

    return ""


def download_cloudflared() -> tuple[bool, str]:
    """自动下载 cloudflared 到本地目录。

    Returns:
        (success, message): 成功与否 + 描述信息
    """
    system = platform.system()
    url = _DOWNLOAD_URLS.get(system)
    if not url:
        return False, f"不支持的平台：{system}，请手动下载 cloudflared"

    target_path = _get_cloudflared_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"开始下载 cloudflared: {url}")
    logger.info(f"保存到: {target_path}")

    try:
        # 流式下载，避免大文件占满内存
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()

                total = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(target_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = downloaded * 100 // total
                            # 每 10% 打一次日志
                            if pct % 10 == 0:
                                logger.info(f"下载进度: {pct}% ({downloaded // 1024}KB / {total // 1024}KB)")

        # 设置可执行权限（非 Windows）
        if system != "Windows":
            os.chmod(target_path, 0o755)

        # 验证文件大小（cloudflared 约 50MB，小于 1MB 肯定是错误页面）
        size_mb = target_path.stat().st_size / (1024 * 1024)
        if size_mb < 1:
            target_path.unlink(missing_ok=True)
            return False, f"下载的文件太小（{size_mb:.1f}MB），可能下载失败"

        logger.info(f"cloudflared 下载完成: {target_path} ({size_mb:.1f}MB)")
        return True, f"下载完成：{target_path}（{size_mb:.1f}MB）"

    except httpx.HTTPError as e:
        logger.error(f"下载 cloudflared 网络错误: {e}", exc_info=True)
        # 清理不完整的文件
        target_path.unlink(missing_ok=True)
        return False, (
            f"下载失败（网络错误）：{e}\n\n"
            "可能原因：国内访问 GitHub 较慢或被墙。\n"
            "解决方法：\n"
            "1. 用 VPN/代理后重试\n"
            "2. 手动下载 cloudflared 并放到程序同目录\n"
            f"   下载地址：{url}\n"
            f"   放到：{target_path.parent}"
        )
    except Exception as e:
        logger.error(f"下载 cloudflared 异常: {e}", exc_info=True)
        target_path.unlink(missing_ok=True)
        return False, f"下载异常：{e}"


def ensure_cloudflared() -> tuple[bool, str]:
    """确保 cloudflared 可用：已安装直接返回，未安装则自动下载。

    Returns:
        (success, message): 成功与否 + 描述信息
    """
    if is_cloudflared_available():
        exe = get_cloudflared_executable()
        return True, f"cloudflared 已就绪：{exe}"

    # 未安装，自动下载
    logger.info("cloudflared 未安装，开始自动下载...")
    return download_cloudflared()
