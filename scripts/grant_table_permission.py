"""一键脚本：把指定用户添加为多维表格的协作者。

背景：
飞书多维表格由应用（机器人）创建后，应用是表的所有者。
用户本人在飞书网页端打开表格时默认只有"可查看"权限，无法编辑。

本脚本通过飞书云文档 API，把指定用户添加为表的"可编辑"协作者。
支持手机号或邮箱两种方式：
- 邮箱：直接添加为协作者
- 手机号：先查询 user_id，再用 user_id 添加为协作者

用法：
    交互模式（会提示输入）：
    python -m scripts.grant_table_permission

    直接传参：
    python -m scripts.grant_table_permission 15012345678
    python -m scripts.grant_table_permission your_email@example.com

前置条件：
飞书应用需要在开发者后台开通以下权限：
- base:collaborator:create  （新增协作者）
- contact:user.id:readonly  （通过手机号或邮箱获取用户 ID，仅手机号登录需要）
"""

from __future__ import annotations

import re
import sys

from src.config import settings
from src.feishu.permission import permission_manager
from src.observability.logger import get_logger

logger = get_logger()


def _is_email(text: str) -> bool:
    """判断字符串是否为邮箱格式。"""
    return bool(re.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", text))


def _is_mobile(text: str) -> bool:
    """判断字符串是否为手机号格式（11位数字，可带+86前缀）。"""
    cleaned = text.replace("+86", "").replace(" ", "").replace("-", "")
    return bool(re.match(r"^1[3-9]\d{9}$", cleaned))


def _normalize_mobile(text: str) -> str:
    """规范化手机号，去除+86和分隔符。"""
    return text.replace("+86", "").replace(" ", "").replace("-", "")


def grant_by_email(email: str, app_token: str) -> bool:
    """通过邮箱添加协作者。"""
    return permission_manager.add_collaborator(
        token=app_token,
        member_id=email,
        member_type="email",
        perm="edit",
    )


def grant_by_mobile(mobile: str, app_token: str) -> bool:
    """通过手机号添加协作者（先查 open_id 再添加）。

    注意：飞书 batch_get_id 接口返回的字段虽然叫 user_id，
    但实际值是 open_id（ou_ 开头），添加协作者时 member_type 必须用 openid。
    """
    # 第1步：手机号 -> open_id
    print(f"  [1/2] 正在通过手机号查询飞书用户 ID...")
    open_id = permission_manager.get_user_id_by_mobile(mobile)
    print(f"  [1/2] 查询成功: open_id={open_id}")

    # 第2步：用 open_id 添加为协作者
    print(f"  [2/2] 正在添加为协作者...")
    return permission_manager.add_collaborator(
        token=app_token,
        member_id=open_id,
        member_type="openid",
        perm="edit",
    )


def main() -> None:
    """把指定用户添加为多维表格的协作者。"""
    app_token = settings.feishu_bitable_app_token

    # 从命令行参数或用户输入获取账号
    if len(sys.argv) > 1:
        account = sys.argv[1].strip()
    else:
        print("=" * 60)
        print("把你自己添加为多维表格的协作者（可编辑权限）")
        print("=" * 60)
        print()
        print("支持手机号或邮箱两种方式：")
        print("  - 手机号：15012345678（飞书手机号登录用户）")
        print("  - 邮箱：your_email@example.com（飞书邮箱登录用户）")
        print()
        account = input("请输入你的飞书登录手机号或邮箱: ").strip()

    if not account:
        print("\n❌ 输入为空，请重新运行")
        return

    # 自动识别账号类型
    if _is_email(account):
        account_type = "email"
        normalized = account
    elif _is_mobile(account):
        account_type = "mobile"
        normalized = _normalize_mobile(account)
    else:
        print(f"\n❌ 无法识别输入格式: {account}")
        print("请输入有效的手机号（11位数字）或邮箱（xxx@xxx.com）")
        return

    print()
    print(f"多维表格 app_token: {app_token}")
    print(f"账号类型: {account_type}")
    print(f"账号: {normalized}")
    print(f"授权权限: 可编辑（edit）")
    print()
    print("正在调用飞书 API...")

    try:
        if account_type == "email":
            success = grant_by_email(normalized, app_token)
        else:
            success = grant_by_mobile(normalized, app_token)

        if success:
            print("\n✅ 授权成功！")
            print("\n现在你可以：")
            print("  1. 打开飞书多维表格网页端")
            print("  2. 直接双击单元格编辑数据")
            print("  3. 添加/修改/删除采集配置表中的记录")
            print("\n影响范围：")
            print("  - 选品池表、Listing库、销售日报、库存预警、采集配置")
            print("  - 以上所有表你都有可编辑权限")

    except RuntimeError as e:
        error_msg = str(e)
        print(f"\n❌ 授权失败: {error_msg}")

        if "99991672" in error_msg or "scope" in error_msg.lower():
            print("\n原因：飞书应用缺少权限")
            print("\n解决步骤（约2分钟）：")
            print("  1. 打开飞书开发者后台：https://open.feishu.cn/app")
            print("  2. 选择你的应用 → 左侧菜单'权限管理'")
            print("  3. 点击'开通权限'，搜索并开通以下权限：")
            print("     - 新增协作者 (base:collaborator:create)")
            if account_type == "mobile":
                print("     - 通过手机号或邮箱获取用户 ID (contact:user.id:readonly)")
            print("  4. 如需审批，联系飞书管理员审批通过")
            print("  5. 重新运行本脚本")

        elif "not found" in error_msg.lower() or "未找到" in error_msg:
            print("\n原因：账号不存在或不在企业飞书通讯录中")
            print("解决：")
            print("  - 确认手机号/邮箱是登录飞书的账号")
            print("  - 确认该账号在企业飞书通讯录中")

        else:
            print("\n其他错误，请查看日志：logs/app_*.log")

    except Exception as e:
        print(f"\n❌ 未知错误: {e}")
        logger.error(f"授权失败: {e}", exc_info=True)


if __name__ == "__main__":
    main()
