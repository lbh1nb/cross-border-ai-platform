"""飞书云文档权限管理：设置多维表格的协作权限。

飞书多维表格由应用（机器人）创建后，应用是表的所有者。
其他用户（包括管理员本人）默认只有"可查看"权限，无法编辑。

本模块通过飞书云文档 API 自动设置表格权限：
1. 设置为"组织内获得链接的人可编辑"——企业内部所有人可编辑
2. 添加指定用户为协作者——精确授权

API 文档：
- https://open.feishu.cn/document/server-docs/docs/permission/permission-public
- https://open.feishu.cn/document/server-docs/docs/permission/permission-member
"""

from __future__ import annotations

from src.feishu.auth import FEISHU_BASE_URL, feishu_auth
from src.observability.logger import get_logger

logger = get_logger()


class PermissionManager:
    """飞书云文档权限管理器。

    封装云文档权限 API，支持设置公开权限和添加协作者。
    """

    def _headers(self) -> dict[str, str]:
        """构建请求头。"""
        return {
            "Authorization": f"Bearer {feishu_auth.get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def set_tenant_editable(self, token: str) -> bool:
        """设置文档为"组织内获得链接的人可编辑"。

        Args:
            token: 多维表格的 app_token

        Returns:
            True 表示成功

        Raises:
            RuntimeError: API 调用失败
        """
        import httpx

        url = f"{FEISHU_BASE_URL}/drive/v1/permissions/{token}/public"
        payload = {
            "link_share_entity": "tenant_editable",  # 组织内可编辑
            "external_access_entity": "tenant_editable",  # 允许组织内访问
        }

        try:
            response = httpx.patch(
                url, headers=self._headers(), json=payload, params={"type": "bitable"}, timeout=10
            )
            # 先解析响应体，再判断状态码（飞书 400 也会返回 JSON 错误信息）
            data = response.json()

            if data.get("code") != 0:
                msg = (
                    f"设置权限失败: code={data.get('code')}, "
                    f"msg={data.get('msg')}"
                )
                logger.error(msg)
                raise RuntimeError(msg)

            logger.info(f"权限设置成功: token={token}, 组织内可编辑")
            return True

        except httpx.HTTPError as e:
            logger.error(f"权限设置请求失败: {e}")
            raise
        except ValueError as e:
            # JSON 解析失败
            logger.error(f"权限设置响应解析失败: {e}, status={response.status_code}, body={response.text[:500]}")
            raise RuntimeError(f"飞书返回非 JSON 响应，HTTP {response.status_code}")

    def add_collaborator(
        self, token: str, member_id: str, member_type: str = "email", perm: str = "edit"
    ) -> bool:
        """添加指定用户/部门为文档协作者。

        Args:
            token: 多维表格的 app_token
            member_id: 成员标识（邮箱/user_id/open_id）
            member_type: 成员类型（email/userid/openid）
            perm: 权限（view/edit/full_access）

        Returns:
            True 表示成功
        """
        import httpx

        url = f"{FEISHU_BASE_URL}/drive/v1/permissions/{token}/members"
        payload = {
            "member_type": member_type,
            "member_id": member_id,
            "perm": perm,
            "need_notification": False,
        }

        try:
            response = httpx.post(
                url, headers=self._headers(), json=payload, params={"type": "bitable"}, timeout=10
            )
            # 先解析响应体（飞书错误也会返回 JSON）
            data = response.json()

            if data.get("code") != 0:
                msg = (
                    f"添加协作者失败: code={data.get('code')}, "
                    f"msg={data.get('msg')}"
                )
                logger.error(msg)
                raise RuntimeError(msg)

            logger.info(
                f"协作者添加成功: {member_type}={member_id}, perm={perm}"
            )
            return True

        except httpx.HTTPError as e:
            logger.error(f"添加协作者请求失败: {e}")
            raise
        except ValueError as e:
            logger.error(
                f"添加协作者响应解析失败: {e}, "
                f"status={response.status_code}, body={response.text[:500]}"
            )
            raise RuntimeError(
                f"飞书返回非 JSON 响应，HTTP {response.status_code}"
            )

    def get_user_id_by_mobile(self, mobile: str) -> str:
        """通过手机号查询飞书用户标识。

        飞书 API 不支持直接用手机号添加协作者，需要先查用户标识。
        注意：batch_get_id 接口返回的字段虽叫 user_id，
        但实际值是 open_id（ou_ 开头），添加协作者时 member_type 用 openid。

        Args:
            mobile: 手机号（纯数字，如 15012345678）

        Returns:
            open_id 字符串（ou_ 开头）

        Raises:
            RuntimeError: 查询失败或用户不存在
        """
        import httpx

        url = f"{FEISHU_BASE_URL}/contact/v3/users/batch_get_id"
        payload = {"mobiles": [mobile]}

        try:
            response = httpx.post(
                url, headers=self._headers(), json=payload, timeout=10
            )
            data = response.json()

            if data.get("code") != 0:
                msg = (
                    f"查询用户ID失败: code={data.get('code')}, "
                    f"msg={data.get('msg')}"
                )
                logger.error(msg)
                raise RuntimeError(msg)

            # 响应结构：data.user_list[0].user_id（实际是 open_id）
            user_list = data.get("data", {}).get("user_list", [])
            if not user_list:
                raise RuntimeError(f"手机号 {mobile} 未找到对应用户")

            open_id = user_list[0].get("user_id")
            if not open_id:
                raise RuntimeError(
                    f"手机号 {mobile} 查询到用户但返回的 ID 为空"
                )

            logger.info(f"手机号 {mobile} -> open_id={open_id}")
            return open_id

        except httpx.HTTPError as e:
            logger.error(f"查询用户ID请求失败: {e}")
            raise
        except ValueError as e:
            logger.error(
                f"查询用户ID响应解析失败: {e}, "
                f"status={response.status_code}, body={response.text[:500]}"
            )
            raise RuntimeError(
                f"飞书返回非 JSON 响应，HTTP {response.status_code}"
            )


# 全局单例
permission_manager = PermissionManager()
