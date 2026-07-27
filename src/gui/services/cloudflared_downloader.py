"""cloudflared 自动下载服务。

业务用户机器上没有 cloudflared 时，自动从多个镜像源下载
对应平台的 cloudflared 二进制文件，放到 exe 同目录（或项目根目录）。

这样业务用户无需去 GitHub 下载、无需配置环境变量，
点"启动公网隧道"时会自动完成下载和启动。

下载源（按优先级顺序尝试，避免国内访问 GitHub 超时）：
- Cloudflare 官方 CDN（pkg.cloudflareclient.com，国内可访问）
- GitHub Releases（官方源，国内可能超时）
- ghproxy 加速（国内 GitHub 镜像）
- jsdelivr 镜像（CDN 加速）

注意：所有源都失败时会提示用户手动下载。
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


# 各平台下载源（多镜像，按优先级排序）
# 实测 2026-07：GitHub 直连国内常超时，ghfast.top 和 gh-proxy.com 稳定可访问
# 第 1 优先级：ghfast.top（国内 GitHub 加速镜像，实测稳定）
# 第 2 优先级：gh-proxy.com（国内 GitHub 加速镜像，实测稳定）
# 第 3 优先级：GitHub Releases（官方源，国内可能超时，作为兜底）
_PLATFORM_FILES = {
    "Windows": "cloudflared-windows-amd64.exe",
    "Darwin": "cloudflared-darwin-amd64.tgz",
    "Linux": "cloudflared-linux-amd64",
}


def _get_download_urls(system: str) -> list[str]:
    """获取指定平台的多个下载源 URL（按优先级排序）。

    Args:
        system: 操作系统名（Windows/Darwin/Linux）

    Returns:
        下载 URL 列表，按优先级排序
    """
    filename = _PLATFORM_FILES.get(system)
    if not filename:
        return []

    # cloudflared 版本（固定使用 2024.12.2，避免 latest 链接可能的跳转问题）
    version = "2024.12.2"
    github_url = f"https://github.com/cloudflare/cloudflared/releases/download/{version}/{filename}"

    return [
        # 1. ghfast.top（国内 GitHub 加速镜像，实测稳定，200 OK 62MB）
        f"https://ghfast.top/{github_url}",
        # 2. gh-proxy.com（国内 GitHub 加速镜像，实测稳定，200 OK 62MB）
        f"https://gh-proxy.com/{github_url}",
        # 3. GitHub Releases（官方源，国内可能超时，作为兜底）
        github_url,
    ]


# 连接超时（秒）—— 连不上就快速换下一个源
_CONNECT_TIMEOUT = 15
# 读取超时（秒）—— cloudflared 约 50MB，给足下载时间
_READ_TIMEOUT = 300
# 下载重试次数（每个源）
_MAX_RETRIES_PER_URL = 1


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


def _try_download_from_url(url: str, target_path: Path) -> tuple[bool, str]:
    """从单个 URL 下载 cloudflared。

    Args:
        url: 下载 URL
        target_path: 本地保存路径

    Returns:
        (success, message): 成功与否 + 描述信息
    """
    logger.info(f"尝试从: {url}")

    try:
        # 流式下载，避免大文件占满内存
        # 连接超时 15 秒（连不上就快速换下一个源）
        # 读取超时 300 秒（cloudflared 约 50MB，给足下载时间）
        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=_READ_TIMEOUT,
            write=_CONNECT_TIMEOUT,
            pool=_CONNECT_TIMEOUT,
        )
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()

                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                last_pct = -1

                with open(target_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = downloaded * 100 // total
                            # 每 10% 打一次日志
                            if pct // 10 != last_pct // 10:
                                last_pct = pct
                                logger.info(
                                    f"下载进度: {pct}% "
                                    f"({downloaded // 1024}KB / {total // 1024}KB)"
                                )

        # 设置可执行权限（非 Windows）
        if platform.system() != "Windows":
            os.chmod(target_path, 0o755)

        # 验证文件大小（cloudflared 约 50MB，小于 1MB 肯定是错误页面）
        size_mb = target_path.stat().st_size / (1024 * 1024)
        if size_mb < 1:
            target_path.unlink(missing_ok=True)
            return False, f"下载的文件太小（{size_mb:.1f}MB），可能下载失败"

        logger.info(f"下载完成: {target_path} ({size_mb:.1f}MB)")
        return True, f"下载完成：{target_path}（{size_mb:.1f}MB）"

    except httpx.ConnectTimeout:
        logger.warning(f"连接超时: {url}")
        target_path.unlink(missing_ok=True)
        return False, f"连接超时: {url}"
    except httpx.ReadTimeout:
        logger.warning(f"读取超时: {url}")
        target_path.unlink(missing_ok=True)
        return False, f"读取超时: {url}"
    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP 错误: {url} -> {e.response.status_code}")
        target_path.unlink(missing_ok=True)
        return False, f"HTTP 错误 {e.response.status_code}: {url}"
    except httpx.HTTPError as e:
        logger.warning(f"网络错误: {url} -> {e}")
        target_path.unlink(missing_ok=True)
        return False, f"网络错误: {e}"


def download_cloudflared() -> tuple[bool, str]:
    """自动下载 cloudflared 到本地目录（多镜像源重试）。

    按优先级顺序尝试多个下载源，第一个成功就用，全部失败才返回错误。

    Returns:
        (success, message): 成功与否 + 描述信息
    """
    system = platform.system()
    urls = _get_download_urls(system)

    if not urls:
        return False, f"不支持的平台：{system}，请手动下载 cloudflared"

    target_path = _get_cloudflared_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"开始下载 cloudflared（{len(urls)} 个镜像源）")
    logger.info(f"保存到: {target_path}")

    # 按优先级顺序尝试每个 URL
    failed_urls: list[str] = []
    for i, url in enumerate(urls, 1):
        logger.info(f"--- 第 {i}/{len(urls)} 个源 ---")
        ok, msg = _try_download_from_url(url, target_path)
        if ok:
            return True, msg
        failed_urls.append(url)

    # 所有源都失败
    error_msg = (
        f"所有下载源都失败（共 {len(failed_urls)} 个）：\n\n"
        + "\n".join(f"  - {url}" for url in failed_urls)
        + "\n\n可能原因：网络不通或被防火墙拦截。\n\n"
        "解决方法（任选其一）：\n"
        "1. 开启 VPN/代理后重试\n"
        "2. 手动下载 cloudflared 并放到程序同目录：\n"
        f"   下载地址（任选其一，浏览器打开即可）：\n"
        f"   - https://ghfast.top/https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/{_PLATFORM_FILES.get(system, '')}\n"
        f"   - https://gh-proxy.com/https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/{_PLATFORM_FILES.get(system, '')}\n"
        f"   - https://github.com/cloudflare/cloudflared/releases\n"
        f"   放到：{target_path.parent}\n"
        "3. 使用 ngrok 替代（需自行注册 ngrok 账号）"
    )
    logger.error(error_msg)
    return False, error_msg


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
