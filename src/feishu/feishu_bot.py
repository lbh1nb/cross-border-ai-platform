"""飞书 Webhook 自定义机器人消息发送模块。

支持三种消息类型：
1. 文本消息（text）：简单纯文本通知
2. 富文本消息（post）：结构化多段落内容，支持加粗/链接
3. 交互卡片消息（interactive）：带按钮和分栏的卡片，用于 08-05 按钮回调

飞书 Webhook 机器人 API 文档：
https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot

消息发送频率限制：单机器人 100 次/分钟，5 次/秒
请求体大小限制：20 KB

用法：
    from src.feishu.feishu_bot import feishu_bot

    # 发送文本消息
    feishu_bot.send_text("库存预警：商品A可售天数不足7天")

    # 发送富文本消息
    feishu_bot.send_rich_text(
        title="库存预警通知",
        content=[["商品A 可售天数：5天，**紧急**"]]
    )

    # 发送交互卡片
    feishu_bot.send_card(card_dict)
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from src.config import settings
from src.observability.logger import get_logger

logger = get_logger()

# 飞书 Webhook 机器人 API 地址前缀
WEBHOOK_BASE_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/"

# 请求超时时间（秒）
REQUEST_TIMEOUT = 10

# 飞书 API 频率限制：5 次/秒，这里保守用 100ms 间隔
RATE_LIMIT_INTERVAL_MS = 100


class FeishuBot:
    """飞书 Webhook 自定义机器人客户端。

    通过 Webhook URL 向指定群聊发送消息，无需 tenant_access_token。
    适合单向通知场景（机器人只能发消息，不能接收消息）。

    若需双向交互（接收用户消息、按钮回调），需使用飞书应用机器人，
    参考 08-05 交互卡片任务。
    """

    def __init__(self, webhook_url: str = "") -> None:
        """初始化机器人客户端。

        Args:
            webhook_url: Webhook 地址，留空则从 settings.feishu_webhook_url 读取
        """
        self._webhook_url = webhook_url or settings.feishu_webhook_url
        if not self._webhook_url:
            logger.warning(
                "Webhook URL 未配置，请在 .env 中设置 FEISHU_WEBHOOK_URL。"
                "消息发送将被跳过。"
            )

    @property
    def is_configured(self) -> bool:
        """检查 Webhook URL 是否已配置。"""
        return bool(self._webhook_url and self._webhook_url.strip())

    def _send(self, payload: dict[str, Any]) -> bool:
        """发送消息到飞书 Webhook（内部方法）。

        Args:
            payload: 飞书消息体，格式参考官方文档

        Returns:
            是否发送成功
        """
        if not self.is_configured:
            logger.warning("Webhook URL 未配置，跳过消息发送")
            return False

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.post(self._webhook_url, json=payload)
                response.raise_for_status()
                data = response.json()

                # 飞书 Webhook 返回格式：{"code": 0, "msg": "success", ...}
                if data.get("code") == 0:
                    logger.debug(f"消息发送成功: msg_type={payload.get('msg_type')}")
                    return True

                # 常见错误：11232 频率限制、9499 安全关键词不匹配
                error_msg = data.get("msg", "未知错误")
                error_code = data.get("code", -1)
                logger.error(
                    f"飞书消息发送失败: code={error_code}, msg={error_msg}, "
                    f"payload={json.dumps(payload, ensure_ascii=False)[:200]}"
                )
                return False

        except httpx.HTTPStatusError as e:
            logger.error(
                f"飞书消息发送 HTTP 错误: status={e.response.status_code}, "
                f"response={e.response.text[:200]}"
            )
            return False
        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}", exc_info=True)
            return False

    def send_text(self, text: str) -> bool:
        """发送纯文本消息。

        最简单的消息类型，适合简短通知。

        Args:
            text: 消息内容（必须包含安全关键词，否则发送失败）

        Returns:
            是否发送成功

        示例：
            feishu_bot.send_text("库存预警：商品A可售天数不足7天")
        """
        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        return self._send(payload)

    def send_rich_text(
        self,
        title: str,
        content: list[list[dict[str, Any]]],
    ) -> bool:
        """发送富文本消息。

        支持多段落、加粗、链接、@用户等。每个段落是一个元素列表。

        Args:
            title: 消息标题
            content: 富文本内容，格式为二维数组
                外层每个元素是一个段落，内层每个元素是一个文本片段
                文本片段格式：{"tag": "text", "text": "普通文字"}
                            {"tag": "a", "text": "链接文字", "href": "https://..."}
                            {"tag": "b", "text": "加粗文字"}

        Returns:
            是否发送成功

        示例：
            feishu_bot.send_rich_text(
                title="库存预警通知",
                content=[
                    [{"tag": "text", "text": "商品A 可售天数：5天，"}],
                    [{"tag": "b", "text": "紧急预警"}]
                ]
            )
        """
        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": content,
                    }
                }
            },
        }
        return self._send(payload)

    def send_card(self, card: dict[str, Any]) -> bool:
        """发送交互卡片消息。

        卡片支持分栏、按钮、图片等复杂布局，按钮可配置回调URL。
        卡片 JSON 结构参考：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN

        Args:
            card: 飞书卡片 JSON 对象，包含 config/header/elements 等字段

        Returns:
            是否发送成功

        示例：
            feishu_bot.send_card({
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "库存预警"},
                    "template": "red"
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "商品A 可售5天"}}
                ]
            })
        """
        payload = {
            "msg_type": "interactive",
            "card": card,
        }
        return self._send(payload)


# 全局单例，import 即用
feishu_bot = FeishuBot()
