"""飞书应用机器人（通过开放 API 发送消息，支持卡片按钮回调）。

与 Webhook 自定义机器人的区别：
    Webhook 机器人（feishu_bot.py）：
        - 只能发消息，不能接收回调
        - 卡片按钮只能用 url 跳转
        - 配置简单（只需 Webhook URL）

    应用机器人（本模块）：
        - 能发消息 + 能接收回调
        - 卡片按钮可用 value 触发回调（card.action.trigger）
        - 配置复杂（需应用凭证 + chat_id + 启用机器人能力 + 事件订阅）

使用场景：
    - 审批卡片（需通过/拒绝按钮触发回调）
    - 其他需要按钮交互的场景

API 文档：
    发送消息: POST https://open.feishu.cn/open-apis/im/v1/messages
    需要 receive_id_type=chat_id 和 Bearer tenant_access_token
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from src.config import settings
from src.feishu.auth import get_tenant_access_token
from src.observability.logger import get_logger

logger = get_logger()


class ApplicationBot:
    """飞书应用机器人（通过开放 API 发送消息）。

    Attributes:
        chat_id: 群聊 ID（机器人所在群）
    """

    def __init__(self, chat_id: str = "") -> None:
        """初始化应用机器人。

        Args:
            chat_id: 群聊 ID（从群设置获取）
        """
        self._chat_id = chat_id or settings.feishu_chat_id
        self._api_base = "https://open.feishu.cn/open-apis/im/v1/messages"

    @property
    def is_configured(self) -> bool:
        """检查应用机器人是否已配置。

        Returns:
            True 表示 chat_id 已配置
        """
        return bool(self._chat_id)

    def send_card(self, card: dict[str, Any]) -> bool:
        """发送交互卡片到群聊。

        卡片中的 value 按钮会触发 card.action.trigger 回调，
        需配合 card_callback.py 服务使用。

        Args:
            card: 飞书卡片 JSON 对象

        Returns:
            True 表示发送成功
        """
        if not self.is_configured:
            logger.warning("应用机器人未配置 chat_id，跳过发送")
            return False

        try:
            token = get_tenant_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
            # 飞书 IM 接口要求 content 是 JSON 字符串（不是 dict 对象）
            # msg_type=interactive 时，content 直接是卡片对象的 JSON 字符串
            # 注意：不要再包一层 {"card": ...}，否则报错 230099
            # 官方文档：https://open.feishu.cn/document/server-docs/im-v1/message/create
            payload = {
                "receive_id": self._chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            }
            params = {"receive_id_type": "chat_id"}

            with httpx.Client(timeout=10) as client:
                response = client.post(
                    self._api_base,
                    headers=headers,
                    params=params,
                    json=payload,
                )
                # 不用 raise_for_status，飞书 4xx 也会返回 JSON 错误信息
                data = response.json()

            if data.get("code") == 0:
                logger.info(
                    f"应用机器人发送卡片成功: chat_id={self._chat_id[:20]}..."
                )
                return True

            # 打印完整响应体便于排查（含飞书错误码、msg、log_id）
            logger.error(
                f"应用机器人发送卡片失败: HTTP {response.status_code}, "
                f"code={data.get('code')}, msg={data.get('msg')}, "
                f"log_id={data.get('error', {}).get('log_id', '')}"
            )
            return False

        except Exception as e:
            logger.error(f"应用机器人发送卡片异常: {e}", exc_info=True)
            return False

    def send_text(self, text: str) -> bool:
        """发送纯文本消息到群聊。

        用于异步回写失败时的告警通知。

        Args:
            text: 文本内容

        Returns:
            True 表示发送成功
        """
        if not self.is_configured:
            logger.warning("应用机器人未配置 chat_id，跳过发送")
            return False

        try:
            token = get_tenant_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
            payload = {
                "receive_id": self._chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            }
            params = {"receive_id_type": "chat_id"}

            with httpx.Client(timeout=10) as client:
                response = client.post(
                    self._api_base,
                    headers=headers,
                    params=params,
                    json=payload,
                )
                data = response.json()

            if data.get("code") == 0:
                logger.info(f"应用机器人发送文本成功: chat_id={self._chat_id[:20]}...")
                return True

            logger.error(
                f"应用机器人发送文本失败: code={data.get('code')}, msg={data.get('msg')}"
            )
            return False

        except Exception as e:
            logger.error(f"应用机器人发送文本异常: {e}", exc_info=True)
            return False


# 全局单例
application_bot = ApplicationBot()
