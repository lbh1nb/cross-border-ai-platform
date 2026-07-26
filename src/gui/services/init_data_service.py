"""一键初始化数据服务：合并建表 + 视图 + 采集配置 + 权限设置。

业务用户在 GUI 点一个按钮就能完成所有数据初始化，不用跑 4 个脚本。

流程：
1. 创建 4 张业务表（选品池/Listing库/销售日报/库存预警）→ 拿到 table_id
2. 创建采集配置表 + 写入 15 条默认配置
3. 自动把 table_id 写回 .env
4. 创建 3 个业务视图（销售总览/预警看板/选品决策）
5. 设置表格权限为"组织内可编辑"
"""

from __future__ import annotations

from typing import Any

from src.observability.logger import get_logger
from src.gui.services.env_service import write_env_config

logger = get_logger()


def _get_settings():
    """动态获取最新 settings（.env 写入后重新读取）。"""
    from src.config import settings
    return settings


# 视图配置（与 scripts/init_views.py 保持一致）
VIEW_CONFIGS = [
    {
        "table_name": "销售日报",
        "table_id_key": "feishu_table_id_daily_report",
        "view_name": "销售总览",
        "visible_fields": ["日期", "平台", "销售额", "订单数", "ACoS", "异常标记", "AI洞察"],
    },
    {
        "table_name": "库存预警",
        "table_id_key": "feishu_table_id_inventory",
        "view_name": "预警看板",
        "visible_fields": ["ASIN", "商品名称", "SKU", "平台", "可售天数", "预警等级", "建议采购量", "预估采购金额", "审批状态"],
    },
    {
        "table_name": "选品池",
        "table_id_key": "feishu_table_id_selection",
        "view_name": "选品决策",
        "visible_fields": ["商品名称", "ASIN", "品类", "来源平台", "价格区间", "评分", "评论数", "市场容量", "竞争强度", "利润空间", "推荐指数", "状态"],
    },
]


class InitStepResult:
    """单步初始化结果。"""

    def __init__(self, name: str, success: bool, message: str = "", data: Any = None) -> None:
        self.name = name
        self.success = success
        self.message = message
        self.data = data

    def __repr__(self) -> str:
        status = "✅" if self.success else "❌"
        return f"{status} {self.name}: {self.message}"


def _apply_field_visibility(
    table_id: str, view_id: str, visible_fields: list[str]
) -> bool:
    """配置视图字段可见性，隐藏非关键字段。"""
    from src.feishu.bitable import bitable_client

    try:
        all_fields = bitable_client.list_fields(table_id)
        hidden_field_ids: list[str] = []
        for field in all_fields:
            field_id = field.get("field_id")
            field_name = field.get("field_name")
            if field_name not in visible_fields and field_id:
                hidden_field_ids.append(field_id)

        if not hidden_field_ids:
            return True

        settings_payload = {
            "property": {"hidden_fields": hidden_field_ids[:100]}
        }
        bitable_client.patch_view(table_id, view_id, settings_payload)
        return True
    except Exception as e:
        logger.error(f"字段可见性配置失败: {e}")
        return False


def _create_view_for_table(
    table_id: str, view_name: str, visible_fields: list[str]
) -> str | None:
    """为单张表创建视图并配置字段显示。"""
    from src.feishu.bitable import bitable_client

    # 检查视图是否已存在
    view_id: str | None = None
    existing_views = bitable_client.list_views(table_id)
    for v in existing_views:
        if v.get("view_name") == view_name:
            view_id = v.get("view_id")
            break

    # 视图不存在则创建
    if not view_id:
        try:
            view_id = bitable_client.create_view(table_id, view_name, view_type="grid")
        except Exception as e:
            logger.error(f"创建视图失败 [{view_name}]: {e}")
            return None

    # 应用字段可见性
    if view_id:
        _apply_field_visibility(table_id, view_id, visible_fields)

    return view_id


def init_business_tables() -> InitStepResult:
    """第1步：创建 4 张业务表，返回 table_id 并写入 .env。"""
    from src.feishu.bitable import bitable_client

    try:
        result = bitable_client.create_all_tables()
        env_mapping = {
            "选品池": "FEISHU_TABLE_ID_SELECTION",
            "Listing库": "FEISHU_TABLE_ID_LISTING",
            "销售日报": "FEISHU_TABLE_ID_DAILY_REPORT",
            "库存预警": "FEISHU_TABLE_ID_INVENTORY",
        }
        env_updates: dict[str, str] = {}
        for table_name, table_id in result.items():
            env_key = env_mapping.get(table_name, "")
            if env_key:
                env_updates[env_key] = table_id
        if env_updates:
            write_env_config(env_updates)
        return InitStepResult(
            name="创建业务表",
            success=True,
            message=f"已创建 {len(result)} 张表，table_id 已写入 .env",
            data=result,
        )
    except Exception as e:
        logger.error(f"创建业务表失败: {e}", exc_info=True)
        return InitStepResult(name="创建业务表", success=False, message=str(e))


def init_config_table() -> InitStepResult:
    """第2步：创建采集配置表 + 写入 15 条默认配置。"""
    from src.feishu.config_table import (
        DEFAULT_CONFIG_RECORDS,
        create_collection_config_table,
        write_default_config,
    )
    from src.feishu.bitable import bitable_client

    try:
        settings = _get_settings()
        # 检查采集配置表是否已存在
        config_table_id = settings.feishu_table_id_collection_config
        if not config_table_id:
            # 创建采集配置表
            config_table_id = create_collection_config_table()
            if config_table_id:
                write_env_config({"FEISHU_TABLE_ID_COLLECTION_CONFIG": config_table_id})

        if not config_table_id:
            return InitStepResult(
                name="创建采集配置表", success=False, message="未能获取采集配置表 ID"
            )

        # 写入默认配置（先查询是否已有数据，避免重复）
        existing = bitable_client.query_records(config_table_id)
        if existing:
            return InitStepResult(
                name="采集配置表",
                success=True,
                message=f"采集配置表已存在，含 {len(existing)} 条配置（跳过默认写入）",
            )

        # 批量写入 15 条默认配置
        write_default_config(config_table_id)

        return InitStepResult(
            name="采集配置表",
            success=True,
            message=f"已创建采集配置表并写入 {len(DEFAULT_CONFIG_RECORDS)} 条默认配置",
        )
    except Exception as e:
        logger.error(f"创建采集配置表失败: {e}", exc_info=True)
        return InitStepResult(name="采集配置表", success=False, message=str(e))


def init_views() -> InitStepResult:
    """第3步：创建 3 个业务视图。"""
    from src.feishu.bitable import bitable_client

    settings = _get_settings()
    success_count = 0
    fail_count = 0
    details: list[str] = []

    for config in VIEW_CONFIGS:
        table_name = config["table_name"]
        table_id = getattr(settings, config["table_id_key"], "")
        if not table_id:
            details.append(f"{table_name}: 跳过（table_id 未配置）")
            fail_count += 1
            continue

        view_id = _create_view_for_table(
            table_id, config["view_name"], config["visible_fields"]
        )
        if view_id:
            success_count += 1
            details.append(f"{table_name} → {config['view_name']} ✓")
        else:
            fail_count += 1
            details.append(f"{table_name} → {config['view_name']} ✗")

    msg = f"成功 {success_count} / 失败 {fail_count}"
    if details:
        msg += "\n" + "\n".join(details)
    return InitStepResult(
        name="创建业务视图",
        success=fail_count == 0,
        message=msg,
    )


def init_permissions() -> InitStepResult:
    """第4步：设置多维表格为"组织内可编辑"。"""
    from src.feishu.permission import PermissionManager

    try:
        settings = _get_settings()
        pm = PermissionManager()
        app_token = settings.feishu_bitable_app_token
        if not app_token:
            return InitStepResult(
                name="设置表格权限", success=False, message="App Token 未配置"
            )
        success = pm.set_tenant_editable(app_token)
        if success:
            return InitStepResult(
                name="设置表格权限",
                success=True,
                message="已设置为组织内可编辑",
            )
        return InitStepResult(
            name="设置表格权限", success=False, message="API 调用失败"
        )
    except Exception as e:
        logger.error(f"设置权限失败: {e}", exc_info=True)
        return InitStepResult(name="设置表格权限", success=False, message=str(e))


def initialize_all_data() -> list[InitStepResult]:
    """一键初始化所有数据：建表 → 采集配置 → 视图 → 权限。

    Returns:
        4 步初始化结果列表，按顺序排列
    """
    logger.info("=" * 50)
    logger.info("一键数据初始化开始")
    logger.info("=" * 50)

    results: list[InitStepResult] = []

    # 第1步：创建业务表
    results.append(init_business_tables())

    # 第2步：创建采集配置表（依赖第1步的 app_token，不依赖 table_id）
    results.append(init_config_table())

    # 第3步：创建视图（依赖第1步写入的 table_id，需重新加载 settings）
    # pydantic_settings 不会自动热重载，手动重新创建实例替换全局单例
    import src.config as config_module
    config_module.settings = config_module.Settings()
    results.append(init_views())

    # 第4步：设置权限
    results.append(init_permissions())

    logger.info("=" * 50)
    success_count = sum(1 for r in results if r.success)
    logger.info(f"一键数据初始化完成: {success_count}/{len(results)} 步成功")
    logger.info("=" * 50)

    return results
