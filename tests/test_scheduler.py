"""调度器模块单元测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.scheduler.inventory_alert import (
    ALERT_THRESHOLD_URGENT,
    ALERT_THRESHOLD_WARNING,
    get_alert_level,
)
from src.scheduler.scheduler import SchedulerManager
from src.scheduler.triggers import ALL_TRIGGERS


class TestInventoryAlert:
    """库存预警等级测试。"""

    def test_urgent_level(self) -> None:
        """可售天数 < 7 -> 紧急。"""
        assert get_alert_level(5) == "紧急"
        assert get_alert_level(0) == "紧急"
        assert get_alert_level(6) == "紧急"

    def test_warning_level(self) -> None:
        """可售天数 7-13 -> 预警。"""
        assert get_alert_level(7) == "预警"
        assert get_alert_level(10) == "预警"
        assert get_alert_level(13) == "预警"

    def test_watch_level(self) -> None:
        """可售天数 14-20 -> 关注。"""
        assert get_alert_level(14) == "关注"
        assert get_alert_level(18) == "关注"
        assert get_alert_level(20) == "关注"

    def test_normal_level(self) -> None:
        """可售天数 >= 21 -> 正常。"""
        assert get_alert_level(21) == "正常"
        assert get_alert_level(30) == "正常"
        assert get_alert_level(100) == "正常"

    def test_boundary_values(self) -> None:
        """测试边界值。"""
        assert get_alert_level(ALERT_THRESHOLD_URGENT - 1) == "紧急"
        assert get_alert_level(ALERT_THRESHOLD_URGENT) == "预警"
        assert get_alert_level(ALERT_THRESHOLD_WARNING - 1) == "预警"
        assert get_alert_level(ALERT_THRESHOLD_WARNING) == "关注"


class TestSchedulerManager:
    """调度器管理器测试。"""

    def test_register_all_tasks(self) -> None:
        """注册所有任务后任务列表长度正确。

        共 4 个任务：
        - product_collection（选品采集）
        - inventory_check（库存预警）
        - daily_report（日报生成）
        - data_cleanup（数据清理，每3天）
        """
        manager = SchedulerManager(blocking=False)
        manager.register_all_tasks()
        jobs = manager.get_jobs()
        assert len(jobs) == 4
        manager.shutdown()

    def test_start_and_shutdown_background(self) -> None:
        """后台调度器启动后能正常停止。"""
        manager = SchedulerManager(blocking=False)
        manager.register_all_tasks()

        from apscheduler.schedulers.background import BackgroundScheduler
        assert isinstance(manager._scheduler, BackgroundScheduler)

        manager._scheduler.start()
        assert manager._scheduler.running

        manager.shutdown()
        assert not manager._scheduler.running

    def test_task_ids_match_triggers(self) -> None:
        """注册的任务 ID 与触发器配置一致。"""
        manager = SchedulerManager(blocking=False)
        manager.register_all_tasks()
        jobs = manager.get_jobs()

        job_ids = {j["id"] for j in jobs}
        trigger_ids = {t["id"] for t in ALL_TRIGGERS}
        assert job_ids == trigger_ids

        manager.shutdown()
