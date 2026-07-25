"""项目配置中心：统一从环境变量读取配置，避免散落在各模块。"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从 .env 文件读取。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 飞书应用凭证
    feishu_app_id: str = Field(default="", description="飞书应用 App ID")
    feishu_app_secret: str = Field(default="", description="飞书应用 App Secret")

    # 飞书多维表格
    feishu_bitable_app_token: str = Field(default="", description="多维表格 App Token")
    feishu_table_id_selection: str = Field(default="", description="选品池表 ID")
    feishu_table_id_listing: str = Field(default="", description="Listing 库表 ID")
    feishu_table_id_daily_report: str = Field(default="", description="销售日报表 ID")
    feishu_table_id_inventory: str = Field(default="", description="库存预警表 ID")

    # 飞书机器人
    feishu_webhook_url: str = Field(default="", description="Webhook 机器人地址")

    # AI 模型
    openai_api_key: str = Field(default="", description="OpenAI API Key")
    anthropic_api_key: str = Field(default="", description="Anthropic API Key")

    # 业务配置
    inventory_alert_days: int = Field(default=14, description="库存预警阈值（天）")
    purchase_approval_threshold: float = Field(
        default=5000, description="选品金额阈值（美金，超过触发审批）"
    )

    # 日志
    log_level: str = Field(default="INFO", description="日志级别")


# 全局单例，import 即用
settings = Settings()
