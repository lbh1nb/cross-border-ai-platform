"""多审批流规则服务。

支持业务用户配置多个审批流规则，每个规则绑定：
1. 一个飞书审批定义（approval_code + node_id）
2. 一个触发事件（选品采集完成 / 库存预警触发）
3. 一个触发条件（字段 + 操作符 + 阈值）

当业务事件发生时，调用 match_and_trigger() 检查所有启用的规则，
匹配条件的记录自动创建飞书审批实例。

规则存储：data/approval_rules.json（JSON 文件，不依赖飞书 API）

设计要点：
- 一个审批定义可被多个规则引用（不同条件触发同一审批）
- 一个事件可匹配多个规则（同一记录触发多种审批）
- 规则启用/禁用不影响其他规则
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.observability.logger import get_logger

logger = get_logger()


# ============ 触发事件类型常量 ============
EVENT_PRODUCT_COLLECTED = "product_collected"  # 选品采集完成
EVENT_INVENTORY_ALERT = "inventory_alert"      # 库存预警触发

EVENT_LABELS = {
    EVENT_PRODUCT_COLLECTED: "选品采集完成",
    EVENT_INVENTORY_ALERT: "库存预警触发",
}

# ============ 条件操作符 ============
OPERATOR_GT = ">"
OPERATOR_LT = "<"
OPERATOR_GE = ">="
OPERATOR_LE = "<="
OPERATOR_EQ = "=="

OPERATOR_LABELS = {
    OPERATOR_GT: "大于",
    OPERATOR_LT: "小于",
    OPERATOR_GE: "大于等于",
    OPERATOR_LE: "小于等于",
    OPERATOR_EQ: "等于",
}

# 选品池可用的条件字段
PRODUCT_CONDITION_FIELDS = ["采购金额", "评分", "评论数", "BSR"]
# 库存预警可用的条件字段
INVENTORY_CONDITION_FIELDS = ["可售天数", "当前库存", "建议采购量"]


def _resolve_rules_path() -> Path:
    """获取规则文件路径。

    打包模式：exe 同目录的 data/approval_rules.json
    开发模式：项目根目录的 data/approval_rules.json
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent.parent.parent
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "approval_rules.json"


def _load_rules() -> list[dict[str, Any]]:
    """读取所有审批规则。"""
    path = _resolve_rules_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"读取审批规则失败: {e}", exc_info=True)
        return []


def _save_rules(rules: list[dict[str, Any]]) -> bool:
    """保存审批规则。"""
    path = _resolve_rules_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存审批规则失败: {e}", exc_info=True)
        return False


def list_rules() -> list[dict[str, Any]]:
    """获取所有审批规则（按创建时间排序）。"""
    rules = _load_rules()
    rules.sort(key=lambda r: r.get("created_at", ""))
    return rules


def get_rule(rule_id: str) -> dict[str, Any] | None:
    """获取单个规则。"""
    for rule in _load_rules():
        if rule.get("id") == rule_id:
            return rule
    return None


def add_rule(rule: dict[str, Any]) -> str | None:
    """新增规则。

    Args:
        rule: 规则字典，无需传 id 和 created_at（自动生成）

    Returns:
        新规则的 id，失败返回 None
    """
    rules = _load_rules()
    rule_id = f"rule_{uuid.uuid4().hex[:8]}"
    rule["id"] = rule_id
    rule["created_at"] = datetime.now().isoformat(timespec="seconds")
    rule["enabled"] = rule.get("enabled", True)
    rules.append(rule)
    if _save_rules(rules):
        logger.info(f"新增审批规则: {rule_id} - {rule.get('name', '')}")
        return rule_id
    return None


def update_rule(rule_id: str, updates: dict[str, Any]) -> bool:
    """更新规则（部分字段）。"""
    rules = _load_rules()
    for rule in rules:
        if rule.get("id") == rule_id:
            rule.update(updates)
            rule["updated_at"] = datetime.now().isoformat(timespec="seconds")
            return _save_rules(rules)
    return False


def delete_rule(rule_id: str) -> bool:
    """删除规则。"""
    rules = _load_rules()
    new_rules = [r for r in rules if r.get("id") != rule_id]
    if len(new_rules) == len(rules):
        return False
    return _save_rules(new_rules)


def toggle_rule(rule_id: str, enabled: bool) -> bool:
    """启用/禁用规则。"""
    return update_rule(rule_id, {"enabled": enabled})


# ============ 条件匹配引擎 ============

def _extract_number(field_value: Any) -> float:
    """从飞书字段值中提取数字（兼容数字/文本/列表格式）。"""
    if field_value is None:
        return 0.0
    if isinstance(field_value, (int, float)):
        return float(field_value)
    if isinstance(field_value, str):
        try:
            return float(field_value)
        except ValueError:
            return 0.0
    if isinstance(field_value, list):
        if not field_value:
            return 0.0
        first = field_value[0]
        if isinstance(first, dict):
            text = first.get("text") or first.get("name") or ""
            try:
                return float(text)
            except (ValueError, TypeError):
                return 0.0
        try:
            return float(first)
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def _match_condition(
    record_value: float,
    operator: str,
    condition_value: float,
) -> bool:
    """判断数值是否满足条件。"""
    if operator == OPERATOR_GT:
        return record_value > condition_value
    if operator == OPERATOR_LT:
        return record_value < condition_value
    if operator == OPERATOR_GE:
        return record_value >= condition_value
    if operator == OPERATOR_LE:
        return record_value <= condition_value
    if operator == OPERATOR_EQ:
        return abs(record_value - condition_value) < 0.01
    return False


def match_rules(
    event_type: str,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """匹配审批规则，返回需要触发审批的记录+规则对。

    Args:
        event_type: 事件类型（EVENT_PRODUCT_COLLECTED / EVENT_INVENTORY_ALERT）
        records: 飞书记录列表（每项含 fields）

    Returns:
        匹配结果列表，每项含：
        - rule: 规则字典
        - record: 匹配的飞书记录
        - field_value: 触发字段的实际值
    """
    if not records:
        return []

    rules = _load_rules()
    enabled_rules = [r for r in rules if r.get("enabled") and r.get("trigger_event") == event_type]

    if not enabled_rules:
        return []

    matches: list[dict[str, Any]] = []
    for rule in enabled_rules:
        condition_field = rule.get("condition_field", "")
        operator = rule.get("condition_operator", ">")
        condition_value = float(rule.get("condition_value", 0))

        for record in records:
            fields = record.get("fields", {})
            record_value = _extract_number(fields.get(condition_field))
            if _match_condition(record_value, operator, condition_value):
                matches.append({
                    "rule": rule,
                    "record": record,
                    "field_value": record_value,
                })

    logger.info(
        f"审批规则匹配: 事件={event_type}, 记录数={len(records)}, "
        f"启用规则数={len(enabled_rules)}, 匹配数={len(matches)}"
    )
    return matches


def match_and_trigger(
    event_type: str,
    records: list[dict[str, Any]],
) -> int:
    """匹配规则并自动创建审批实例（业务事件入口）。

    业务任务（选品采集/库存预警）完成后调用本函数，
    自动检查所有启用的审批规则，匹配条件就创建飞书审批实例。

    Args:
        event_type: 事件类型
        records: 触发事件的记录列表

    Returns:
        成功创建的审批实例数量
    """
    from src.feishu.approval import ApprovalClient
    from src.feishu.bitable import bitable_client
    from src.scheduler.tasks import _extract_field_value

    matches = match_rules(event_type, records)
    if not matches:
        return 0

    triggered = 0
    for match in matches:
        rule = match["rule"]
        record = match["record"]
        fields = record.get("fields", {})

        # 提取审批表单需要的字段
        asin = _extract_field_value(fields.get("ASIN"), default="")
        product_name = _extract_field_value(
            fields.get("商品名称"), default="未命名商品"
        )
        amount = _extract_number(fields.get("采购金额"))

        if not asin:
            logger.warning(f"记录缺少 ASIN，跳过审批: rule={rule.get('name')}")
            continue

        # 已触发过审批的跳过（避免重复）
        current_status = _extract_field_value(fields.get("审批状态"))
        if current_status and current_status != "未触发":
            continue

        # 用规则自己的审批定义创建实例（支持多审批流）
        client = ApprovalClient(
            approval_code=rule.get("approval_code", ""),
            approver_open_id=rule.get("approver_open_id", ""),
            node_id=rule.get("node_id", ""),
        )

        description = (
            f"自动触发：{rule.get('name', '')} - "
            f"{rule.get('condition_field', '')} {rule.get('condition_operator', '')} "
            f"{rule.get('condition_value', '')}（实际值: {match['field_value']}）"
        )

        instance_code = client.create_approval_instance(
            asin=asin,
            product_name=product_name,
            amount=amount,
            biz_type=rule.get("name", "自动审批"),
            description=description,
        )

        if instance_code:
            triggered += 1
            # 回写审批状态
            table_id = rule.get("table_id", "")
            if not table_id:
                # 默认回写到库存预警表
                from src.config import settings
                table_id = settings.feishu_table_id_inventory
            if table_id:
                bitable_client.update_record(
                    table_id,
                    record.get("record_id"),
                    {"审批状态": "审批中"},
                )
            logger.info(
                f"审批实例已创建: rule={rule.get('name')}, "
                f"ASIN={asin}, instance_code={instance_code}"
            )

    return triggered
