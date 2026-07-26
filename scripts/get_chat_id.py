"""获取飞书应用机器人所在的所有群列表及其 chat_id。

用途：
    当飞书桌面端群设置不显示"群 ID"时，用此脚本通过 API 自动获取。

前置条件：
    1. 飞书应用已启用机器人能力（应用功能 → 机器人 → 启用）
    2. 应用已发布新版本并通过审核
    3. 机器人已被加入至少一个群聊
    4. .env 已配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET

用法：
    python scripts/get_chat_id.py

输出示例：
    找到 2 个群聊：
      [1] AI 运营告警群
          chat_id: oc_a0553eda9014c201e6969b478895c230
      [2] 产品讨论组
          chat_id: oc_b1234567890abcdef1234567890abcdef
"""

from __future__ import annotations

import sys
from pathlib import Path

# 把项目根目录加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx

from src.config import settings
from src.feishu.auth import get_tenant_access_token
from src.observability.logger import get_logger

logger = get_logger()


def list_bot_chats() -> list[dict]:
    """获取应用机器人所在的所有群列表。

    API 文档：GET /open-apis/im/v1/chats
    需要权限：im:chat:readonly

    Returns:
        群列表，每项含 chat_id / name / description 等字段
    """
    token = get_tenant_access_token()
    if not token:
        logger.error("无法获取 tenant_access_token，请检查应用凭证")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    all_chats: list[dict] = []
    page_token = ""
    page_size = 50

    # 分页拉取所有群
    while True:
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token

        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    "https://open.feishu.cn/open-apis/im/v1/chats",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.error(f"调用飞书 API 失败: {e}", exc_info=True)
            return all_chats

        if data.get("code") != 0:
            logger.error(
                f"飞书 API 返回错误: code={data.get('code')}, "
                f"msg={data.get('msg')}"
            )
            print()
            print("  常见原因：")
            print("  1. 应用未启用机器人能力（开放平台 → 应用功能 → 机器人）")
            print("  2. 应用未发布新版本（修改后需创建版本并发布）")
            print("  3. 缺少权限 im:chat:readonly（权限管理 → 添加权限 → 重新发布）")
            print("  4. 机器人未被加入任何群聊（在飞书桌面端把机器人加入群）")
            return all_chats

        items = data.get("data", {}).get("items", [])
        all_chats.extend(items)

        # 检查是否有下一页
        page_token = data.get("data", {}).get("page_token", "")
        has_more = data.get("data", {}).get("has_more", False)
        if not has_more or not page_token:
            break

    return all_chats


def main() -> None:
    """主函数：列出所有群并显示 chat_id。"""
    print("=" * 60)
    print("  飞书应用机器人所在群列表")
    print("=" * 60)
    print()
    print(f"  应用 App ID: {settings.feishu_app_id}")
    print()
    print("  正在调用飞书 API 获取群列表...")
    print()

    chats = list_bot_chats()

    if not chats:
        print("  [未找到任何群聊]")
        print()
        print("  可能原因：")
        print("  1. 机器人未被加入任何群聊")
        print("     解决：飞书桌面端 → 进入告警群 → 设置 → 群机器人 → 添加机器人")
        print("  2. 应用未启用机器人能力")
        print("     解决：开放平台 → 应用功能 → 机器人 → 启用 → 创建版本发布")
        print("  3. 应用缺少权限 im:chat:readonly")
        print("     解决：权限管理 → 搜索 im:chat:readonly → 开通 → 重新发布版本")
        print()
        return

    print(f"  找到 {len(chats)} 个群聊：")
    print()
    for i, chat in enumerate(chats, 1):
        chat_id = chat.get("chat_id", "N/A")
        name = chat.get("name", "未命名群聊")
        description = chat.get("description", "")
        chat_mode = chat.get("chat_mode", "")
        chat_type = chat.get("chat_type", "")

        print(f"  [{i}] {name}")
        print(f"      chat_id: {chat_id}")
        if description:
            print(f"      描述: {description}")
        if chat_type:
            print(f"      类型: {chat_type}")
        print()

    print("=" * 60)
    print("  下一步")
    print("=" * 60)
    print()
    print("  从上面列表找到你的告警通知群，复制对应的 chat_id")
    print("  （oc_ 开头的字符串）")
    print()
    print("  然后告诉我 chat_id，我帮你填到 .env 文件")
    print()
    print("  或手动编辑 .env 文件，添加一行：")
    print("    FEISHU_CHAT_ID=oc_xxxxxxxxxxxxxxxx")


if __name__ == "__main__":
    main()
