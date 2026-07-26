"""多维表格表结构定义。

四张核心业务表的字段配置，用于自动创建多维表格数据表。
字段类型参考飞书 Bitable API 文档：
https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-field/create

飞书字段类型（field_type）枚举值：
  1 = 多行文本       2 = 数字（含小数）
  3 = 单选           4 = 多选
  5 = 日期时间       7 = 复选框
  11 = 人员         13 = 电话号码
  15 = 超链接        17 = 附件
  18 = 关联记录       19 = 查找引用
  20 = 公式          21 = 双向关联
  22 = 地理位置       23 = 群组
  1001 = 创建时间    1002 = 最后更新时间
  1003 = 创建人      1004 = 修改人
  1005 = 自动编号
"""

from __future__ import annotations

# 字段类型常量，避免魔法数字
class FieldType:
    TEXT = 1          # 多行文本
    NUMBER = 2        # 数字
    SINGLE_SELECT = 3 # 单选
    MULTI_SELECT = 4  # 多选
    DATETIME = 5      # 日期时间
    CHECKBOX = 7      # 复选框
    URL = 15          # 超链接
    FORMULA = 20      # 公式
    AUTO_NUMBER = 1005  # 自动编号


# ============================================================
# 表1：选品池表 —— AI 选品分析结果存储
# ============================================================
SELECTION_TABLE_FIELDS = [
    {"field_name": "商品名称", "type": FieldType.TEXT},
    {"field_name": "ASIN", "type": FieldType.TEXT},
    {"field_name": "品类", "type": FieldType.TEXT},
    {"field_name": "来源平台", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "亚马逊"}, {"name": "沃尔玛"}, {"name": "Wayfair"},
        {"name": "TikTok Shop"}, {"name": "独立站"},
    ]}},
    {"field_name": "价格区间", "type": FieldType.TEXT},
    {"field_name": "评分", "type": FieldType.NUMBER, "property": {"formatter": "0.0"}},
    {"field_name": "评论数", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "BSR排名", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "市场容量", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "高"}, {"name": "中"}, {"name": "低"},
    ]}},
    {"field_name": "竞争强度", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "激烈"}, {"name": "中等"}, {"name": "蓝海"},
    ]}},
    {"field_name": "利润空间", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "高"}, {"name": "中"}, {"name": "低"},
    ]}},
    {"field_name": "AI分析结论", "type": FieldType.TEXT},
    {"field_name": "推荐指数", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "商品链接", "type": FieldType.URL},
    {"field_name": "分析时间", "type": FieldType.DATETIME, "property": {"date_formatter": "yyyy-MM-dd HH:mm"}},
    {"field_name": "状态", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "待审核"}, {"name": "已通过"}, {"name": "已驳回"}, {"name": "已采购"},
    ]}},
]

# ============================================================
# 表2：Listing 库表 —— 商品 Listing 优化记录
# ============================================================
LISTING_TABLE_FIELDS = [
    {"field_name": "ASIN", "type": FieldType.TEXT},
    {"field_name": "商品名称", "type": FieldType.TEXT},
    {"field_name": "原始标题", "type": FieldType.TEXT},
    {"field_name": "优化标题", "type": FieldType.TEXT},
    {"field_name": "原始五点描述", "type": FieldType.TEXT},
    {"field_name": "优化五点描述", "type": FieldType.TEXT},
    {"field_name": "后台关键词", "type": FieldType.TEXT},
    {"field_name": "A+文案", "type": FieldType.TEXT},
    {"field_name": "优化建议", "type": FieldType.TEXT},
    {"field_name": "点击率预估", "type": FieldType.NUMBER, "property": {"formatter": "0.00%"}},
    {"field_name": "优化时间", "type": FieldType.DATETIME, "property": {"date_formatter": "yyyy-MM-dd HH:mm"}},
    {"field_name": "状态", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "待优化"}, {"name": "已优化"}, {"name": "已上线"}, {"name": "已废弃"},
    ]}},
]

# ============================================================
# 表3：销售日报表 —— 每日销售数据汇总 + AI 洞察
# ============================================================
DAILY_REPORT_TABLE_FIELDS = [
    {"field_name": "日期", "type": FieldType.DATETIME, "property": {"date_formatter": "yyyy-MM-dd"}},
    {"field_name": "平台", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "亚马逊"}, {"name": "沃尔玛"}, {"name": "Wayfair"},
        {"name": "TikTok Shop"}, {"name": "独立站"},
    ]}},
    {"field_name": "销售额", "type": FieldType.NUMBER, "property": {"formatter": "0.00"}},
    {"field_name": "订单数", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "广告花费", "type": FieldType.NUMBER, "property": {"formatter": "0.00"}},
    {"field_name": "ACoS", "type": FieldType.NUMBER, "property": {"formatter": "0.00%"}},
    {"field_name": "退货数", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "库存天数", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "AI洞察", "type": FieldType.TEXT},
    {"field_name": "异常标记", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "正常"}, {"name": "销量下跌"}, {"name": "库存告急"}, {"name": "ACoS过高"},
    ]}},
]

# ============================================================
# 表4：库存预警表 —— 库存监控与自动审批
# ============================================================
INVENTORY_TABLE_FIELDS = [
    {"field_name": "ASIN", "type": FieldType.TEXT},
    {"field_name": "商品名称", "type": FieldType.TEXT},
    {"field_name": "SKU", "type": FieldType.TEXT},
    {"field_name": "平台", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "亚马逊"}, {"name": "沃尔玛"}, {"name": "Wayfair"},
        {"name": "TikTok Shop"}, {"name": "独立站"},
    ]}},
    {"field_name": "当前库存", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "日均销量", "type": FieldType.NUMBER, "property": {"formatter": "0.0"}},
    {"field_name": "可售天数", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "预警等级", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "正常"}, {"name": "关注"}, {"name": "预警"}, {"name": "紧急"},
    ]}},
    {"field_name": "建议采购量", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "预估采购金额", "type": FieldType.NUMBER, "property": {"formatter": "0.00"}},
    {"field_name": "审批状态", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "未触发"}, {"name": "待审批"}, {"name": "已通过"}, {"name": "已驳回"},
    ]}},
    {"field_name": "更新时间", "type": FieldType.DATETIME, "property": {"date_formatter": "yyyy-MM-dd HH:mm"}},
]

# ============================================================
# 表5：采集配置表 —— 定义企业经营品类与采集平台（可自定义）
# ============================================================
# 设计理念：
# - 品类字段使用文本而非单选，企业可自由填写经营范围
#   （家具企业填"户外家具"，3C企业填"蓝牙耳机"，无需改代码）
# - 平台字段使用单选，限定支持的跨境电商平台
# - 启用状态控制单条配置是否参与采集
COLLECTION_CONFIG_TABLE_FIELDS = [
    {"field_name": "品类", "type": FieldType.TEXT},
    {"field_name": "平台", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "亚马逊"}, {"name": "沃尔玛"}, {"name": "Wayfair"},
        {"name": "TikTok Shop"}, {"name": "独立站"},
    ]}},
    {"field_name": "采集数量", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "优先级", "type": FieldType.NUMBER, "property": {"formatter": "0"}},
    {"field_name": "启用状态", "type": FieldType.SINGLE_SELECT, "property": {"options": [
        {"name": "启用"}, {"name": "停用"},
    ]}},
    {"field_name": "备注", "type": FieldType.TEXT},
    {"field_name": "更新时间", "type": FieldType.DATETIME, "property": {"date_formatter": "yyyy-MM-dd HH:mm"}},
]

# 所有表的配置汇总，供批量创建使用
ALL_TABLES = {
    "选品池": SELECTION_TABLE_FIELDS,
    "Listing库": LISTING_TABLE_FIELDS,
    "销售日报": DAILY_REPORT_TABLE_FIELDS,
    "库存预警": INVENTORY_TABLE_FIELDS,
    "采集配置": COLLECTION_CONFIG_TABLE_FIELDS,
}
