"""飞书审批流 API 客户端。

调飞书官方审批流 API 创建真实审批实例（非卡片模拟审批），
与 08-05 的卡片审批（card_callback.py）形成完整闭环：

    业务触发 → 创建审批实例（本模块）→ 主管在飞书审批中心审批
    → 审批状态变更事件 → card_callback.py 回写多维表格

API 文档：
    创建审批实例: POST /open-apis/approval/v4/instances
    查询审批实例: GET  /open-apis/approval/v4/instances/{instance_code}
    查询审批定义: GET  /open-apis/approval/v4/approvals/{approval_code}

所需权限：approval:approval

使用场景：
    - 选品池金额 > 5000 美金自动触发采购审批
    - 库存紧急补货审批
    - 其他需多级审批的业务场景
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from src.config import settings
from src.feishu.auth import get_tenant_access_token
from src.observability.logger import get_logger

logger = get_logger()


# ============ 审批定义表单字段 ID 常量 ============
# 这些 ID 是飞书自动生成的，通过 query_approval_definition.py 脚本查询得到
# 如果审批定义被重建，需重新查询并更新这些常量
FIELD_ID_ASIN = "widget17850667532920001"
FIELD_ID_PRODUCT_NAME = "widget17850667792080001"
FIELD_ID_AMOUNT = "widget17850668021870001"
FIELD_ID_BIZ_TYPE = "widget17850668453390001"
FIELD_ID_DESCRIPTION = "widget17850668729890001"


# ============ 审批状态映射 ============
# 飞书审批状态码 → 中文描述
APPROVAL_STATUS_MAP = {
    "PENDING": "审批中",
    "APPROVED": "已通过",
    "REJECTED": "已驳回",
    "CANCELED": "已撤销",
    "DELETED": "已删除",
    "COMPLETED": "已完成",
}


class ApprovalClient:
    """飞书审批流 API 客户端。

    封装审批实例的创建和查询操作。

    Attributes:
        approval_code: 审批定义 Code
        approver_open_id: 默认审批人 open_id
        node_id: 审批节点 ID（用于指定审批人）
    """

    def __init__(
        self,
        approval_code: str = "",
        approver_open_id: str = "",
        node_id: str = "",
    ) -> None:
        """初始化审批客户端。

        Args:
            approval_code: 审批定义 Code（从 .env 读取）
            approver_open_id: 默认审批人 open_id（从 .env 读取）
            node_id: 审批节点 ID（从 .env 读取）
        """
        self._approval_code = approval_code or settings.feishu_approval_code
        self._approver_open_id = approver_open_id or settings.feishu_approval_approver_open_id
        self._node_id = node_id or settings.feishu_approval_node_id
        self._api_base = "https://open.feishu.cn/open-apis/approval/v4"

    @property
    def is_configured(self) -> bool:
        """检查审批流是否已完整配置。

        Returns:
            True 表示 approval_code / approver_open_id / node_id 三项均已配置
        """
        return bool(
            self._approval_code
            and self._approver_open_id
            and self._node_id
        )

    def _build_form(
        self,
        asin: str,
        product_name: str,
        amount: float,
        biz_type: str,
        description: str = "",
    ) -> str:
        """构建审批表单 JSON 字符串。

        飞书 API 要求 form 参数是 JSON 数组字符串，每项含 id/type/value。
        字段 ID 必须与审批定义中的字段 ID 完全一致。

        Args:
            asin: 商品 ASIN
            product_name: 商品名称
            amount: 采购金额（美金）
            biz_type: 业务类型（如"选品采购"）
            description: 补充说明

        Returns:
            JSON 字符串，例如 [{"id":"widget_xxx","type":"input","value":"B08X"}, ...]
        """
        fields = [
            {"id": FIELD_ID_ASIN, "type": "input", "value": asin},
            {"id": FIELD_ID_PRODUCT_NAME, "type": "input", "value": product_name},
            # amount 类型字段的 value 是字符串形式数字
            {"id": FIELD_ID_AMOUNT, "type": "amount", "value": str(amount)},
            {"id": FIELD_ID_BIZ_TYPE, "type": "input", "value": biz_type},
            {"id": FIELD_ID_DESCRIPTION, "type": "textarea", "value": description},
        ]
        # ensure_ascii=False 避免中文被转义成 \uXXXX
        return json.dumps(fields, ensure_ascii=False)

    def create_approval_instance(
        self,
        asin: str,
        product_name: str,
        amount: float,
        biz_type: str = "选品采购",
        description: str = "",
        approver_open_id: str = "",
    ) -> str:
        """创建审批实例。

        业务调用入口：传入商品信息，创建飞书审批实例，
        主管会在飞书审批中心收到审批通知。

        Args:
            asin: 商品 ASIN（用于回写多维表格定位记录）
            product_name: 商品名称
            amount: 采购金额（美金）
            biz_type: 业务类型，默认"选品采购"
            description: 补充说明，默认空
            approver_open_id: 指定审批人 open_id，默认用 .env 配置的默认审批人

        Returns:
            审批实例 instance_code（UUID 格式），失败返回空字符串

        示例：
            client = ApprovalClient()
            code = client.create_approval_instance(
                asin="B08X4ABC",
                product_name="户外折叠椅",
                amount=8500.0,
                biz_type="选品采购",
                description="单笔采购金额超过 5000 美金",
            )
            if code:
                print(f"审批已创建: {code}")
        """
        if not self.is_configured:
            logger.error(
                "审批流未完整配置，请在 .env 中设置 FEISHU_APPROVAL_CODE / "
                "FEISHU_APPROVAL_APPROVER_OPEN_ID / FEISHU_APPROVAL_NODE_ID"
            )
            return ""

        # 优先使用传入的 approver_open_id，否则用默认审批人
        final_approver = approver_open_id or self._approver_open_id

        # 生成幂等 uuid，防止重复创建同一审批
        # 格式必须是 XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
        instance_uuid = str(uuid.uuid4())

        form_str = self._build_form(
            asin=asin,
            product_name=product_name,
            amount=amount,
            biz_type=biz_type,
            description=description,
        )

        payload = {
            "approval_code": self._approval_code,
            "open_id": final_approver,  # 发起人 open_id（这里用审批人自己发起便于测试）
            "form": form_str,
            "node_approver_open_id_list": [
                {
                    "key": self._node_id,
                    "value": [final_approver],
                }
            ],
            "uuid": instance_uuid,
        }

        try:
            token = get_tenant_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }

            with httpx.Client(timeout=15) as client:
                response = client.post(
                    f"{self._api_base}/instances",
                    headers=headers,
                    json=payload,
                )
                data = response.json()

            if data.get("code") == 0:
                instance_code = data.get("data", {}).get("instance_code", "")
                logger.info(
                    f"审批实例创建成功: ASIN={asin}, 金额=${amount:,.2f}, "
                    f"instance_code={instance_code}"
                )
                return instance_code

            logger.error(
                f"审批实例创建失败: code={data.get('code')}, "
                f"msg={data.get('msg')}, ASIN={asin}"
            )
            return ""

        except Exception as e:
            logger.error(
                f"创建审批实例异常: ASIN={asin}, error={e}", exc_info=True
            )
            return ""

    def query_approval_status(self, instance_code: str) -> dict[str, Any]:
        """查询审批实例状态。

        Args:
            instance_code: 审批实例 Code（创建时返回的 instance_code）

        Returns:
            审批实例详情，含以下关键字段：
            - status: 审批状态（PENDING/APPROVED/REJECTED/CANCELED）
            - form: 表单内容
            - applicant: 发起人
            失败返回空 dict
        """
        if not instance_code:
            logger.warning("instance_code 为空，无法查询审批状态")
            return {}

        try:
            token = get_tenant_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }

            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"{self._api_base}/instances/{instance_code}",
                    headers=headers,
                )
                data = response.json()

            if data.get("code") == 0:
                return data.get("data", {})

            logger.error(
                f"查询审批状态失败: code={data.get('code')}, "
                f"msg={data.get('msg')}, instance_code={instance_code}"
            )
            return {}

        except Exception as e:
            logger.error(
                f"查询审批状态异常: instance_code={instance_code}, error={e}",
                exc_info=True,
            )
            return {}

    def get_approval_status_text(self, instance_code: str) -> str:
        """查询审批状态并返回中文描述。

        Args:
            instance_code: 审批实例 Code

        Returns:
            中文状态描述（审批中/已通过/已驳回/已撤销/已删除/已完成/未知）
        """
        detail = self.query_approval_status(instance_code)
        if not detail:
            return "未知"

        status_code = detail.get("status", "")
        return APPROVAL_STATUS_MAP.get(status_code, "未知")


# 全局单例
approval_client = ApprovalClient()
