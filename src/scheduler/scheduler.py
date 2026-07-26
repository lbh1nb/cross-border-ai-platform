"""调度器管理器：基于 APScheduler 的定时任务调度。

特性：
1. SQLite 持久化任务存储，重启不丢任务
2. BlockingScheduler 适合独立进程运行
3. 每个任务独立异常处理，互不影响
4. 支持 max_instances 防止任务重叠

用法：
    python -m src.scheduler.scheduler          # 启动调度器
    python -m src.scheduler.scheduler --status  # 查看任务状态
"""

from __future__ import annotations

import sys

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from src.observability.logger import get_logger
from src.scheduler.approval_task import auto_approval_trigger_task
from src.scheduler.tasks import (
    daily_report_task,
    data_cleanup_task,
    inventory_check_task,
    product_collection_task,
)
from src.scheduler.triggers import ALL_TRIGGERS

logger = get_logger()

# 任务存储 SQLite 文件路径
JOBSTORE_URL = "sqlite:///data/scheduler_jobs.db"

# 任务函数映射：trigger id -> 任务函数
TASK_MAP = {
    "product_collection": product_collection_task,
    "inventory_check": inventory_check_task,
    "daily_report": daily_report_task,
    "data_cleanup": data_cleanup_task,
    "approval_trigger": auto_approval_trigger_task,
}


class SchedulerManager:
    """调度器管理器：注册任务、启动、停止。

    支持 BlockingScheduler（前台运行）和 BackgroundScheduler（后台运行）。
    """

    def __init__(self, blocking: bool = True) -> None:
        jobstore = SQLAlchemyJobStore(url=JOBSTORE_URL)
        scheduler_class = BlockingScheduler if blocking else BackgroundScheduler
        self._scheduler = scheduler_class(jobstores={"default": jobstore})
        self._blocking = blocking

    def register_all_tasks(self) -> None:
        """注册所有定时任务。"""
        for trigger_config in ALL_TRIGGERS:
            task_id = trigger_config["id"]
            task_func = TASK_MAP.get(task_id)

            if task_func is None:
                logger.warning(f"任务 {task_id} 没有对应的函数，跳过")
                continue

            # 提取 APScheduler 参数（去掉自定义的 name 字段）
            aps_config = {
                k: v for k, v in trigger_config.items()
                if k not in ("name",)
            }
            aps_config["replace_existing"] = True

            self._scheduler.add_job(task_func, **aps_config)
            # 构建可读的触发器描述
            trigger_desc = self._describe_trigger(trigger_config)
            logger.info(
                f"注册任务: {trigger_config['name']} ({task_id}) -> {trigger_desc}"
            )

    @staticmethod
    def _describe_trigger(config: dict) -> str:
        """生成可读的触发器描述。"""
        day = config.get("day", "*")
        hour = config.get("hour", "*")
        minute = config.get("minute", "*")
        day_of_week = config.get("day_of_week", "*")

        if day != "*" and day_of_week == "*":
            # 按天数触发（如数据清理）
            return f"每{day.replace('*/', '')}天 {hour}:{minute:02d}"
        if day_of_week == "mon-fri":
            return f"工作日 {hour}:{minute:02d}"
        if minute == "*/30":
            return "每30分钟"
        if day_of_week == "*" and day == "*":
            return f"每天 {hour}:{minute:02d}"
        return f"day={day} dow={day_of_week} {hour}:{minute}"

    def start(self) -> None:
        """启动调度器。"""
        self.register_all_tasks()
        logger.info("=" * 50)
        logger.info("调度器启动，共注册 {} 个任务".format(len(self._scheduler.get_jobs())))
        logger.info("按 Ctrl+C 停止")
        logger.info("=" * 50)

        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.shutdown()

    def shutdown(self) -> None:
        """停止调度器（未启动时安全跳过）。"""
        if not self._scheduler.running:
            return
        logger.info("调度器正在停止...")
        self._scheduler.shutdown(wait=False)
        logger.info("调度器已停止")

    def get_jobs(self) -> list[dict]:
        """获取所有已注册任务信息。"""
        jobs = self._scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": str(next_run) if (next_run := getattr(job, "next_run_time", None)) else None,
                "trigger": str(job.trigger),
            }
            for job in jobs
        ]


def main() -> None:
    """命令行入口：启动调度器或查看状态。"""
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        # 查看任务状态（使用 BackgroundScheduler，不阻塞）
        manager = SchedulerManager(blocking=False)
        manager.register_all_tasks()
        jobs = manager.get_jobs()
        print(f"\n已注册 {len(jobs)} 个定时任务：\n")
        for job in jobs:
            print(f"  任务ID: {job['id']}")
            print(f"  名称: {job['name']}")
            print(f"  触发器: {job['trigger']}")
            print(f"  下次执行: {job['next_run_time']}")
            print()
        manager.shutdown()
    else:
        # 启动调度器（阻塞模式）
        manager = SchedulerManager(blocking=True)
        manager.start()


if __name__ == "__main__":
    main()
